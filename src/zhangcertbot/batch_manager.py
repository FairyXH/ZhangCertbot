from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Callable, Iterable

from .certbot_runner import CertbotRunner
from .certificate_manager import CertificateManager
from .config_manager import ConfigManager, DomainConfig
from .deploy_manager import DeployManager


@dataclass(frozen=True)
class BatchSettings:
    parallel: bool = False
    max_workers: int = 4
    max_retries: int = 2
    retry_delay: float = 1.0

    @property
    def attempts(self) -> int:
        return max(1, int(self.max_retries) + 1)

    def workers(self, count: int) -> int:
        if not self.parallel:
            return 1
        return max(1, min(int(self.max_workers), max(1, count)))


@dataclass
class BatchItemResult:
    domain: str
    ok: bool
    message: str
    deployed: bool = False


class BatchProcessor:
    def __init__(self, manager: ConfigManager, runner: CertbotRunner | None = None,
                 deployer: DeployManager | None = None):
        self.manager = manager
        self.runner = runner or CertbotRunner(manager.root)
        certificates = CertificateManager(self.runner)
        self.deployer = deployer or DeployManager(manager, certificates)

    def issue(self, domains: Iterable[DomainConfig], settings: BatchSettings,
              callback: Callable[[BatchItemResult], None] | None = None) -> list[BatchItemResult]:
        domain_list = list(domains)

        def one(domain: DomainConfig) -> BatchItemResult:
            last_message = "Certbot 申请失败"
            for attempt in range(1, settings.attempts + 1):
                result = self.runner.issue(domain)
                if result.ok:
                    try:
                        self.deployer.certificates.export(domain)
                        deployed = False
                        if domain.deploy:
                            self.deployer.deploy(domain)
                            deployed = True
                        return BatchItemResult(domain.name, True, "申请成功", deployed)
                    except Exception as exc:
                        return BatchItemResult(domain.name, False, str(exc))
                last_message = result.stderr.strip() or "Certbot 申请失败"
                if attempt < settings.attempts:
                    self._emit(callback, BatchItemResult(domain.name, False, f"申请失败，第 {attempt} 次重试：{last_message}"))
                    if settings.retry_delay > 0:
                        time.sleep(settings.retry_delay)
            return BatchItemResult(domain.name, False, f"申请失败，重试次数已用尽：{last_message}")

        return self._map(domain_list, settings, one, callback)

    def renew(self, domains: Iterable[DomainConfig], settings: BatchSettings,
              force: bool = False, callback: Callable[[BatchItemResult], None] | None = None) -> list[BatchItemResult]:
        domain_list = list(domains)
        if len(domain_list) == 1:
            result = self.runner.renew(force=force, cert_name=domain_list[0].cert_name)
        else:
            result = self.runner.renew(force=force)
        certificates = self.deployer.certificates

        def one(domain: DomainConfig) -> BatchItemResult:
            try:
                changed = certificates.export(domain)
                if not changed:
                    return BatchItemResult(domain.name, True, "未续期，不执行部署")
                deployed = False
                if domain.deploy:
                    self.deployer.deploy(domain)
                    deployed = True
                return BatchItemResult(domain.name, True, "已更新", deployed)
            except Exception as exc:
                return BatchItemResult(domain.name, False, str(exc))

        if result.ok:
            return self._map(domain_list, settings, one, callback)
        message = result.stderr.strip() or "Certbot 续期失败"
        failures = [BatchItemResult(domain.name, False, message) for domain in domain_list]
        for item in failures:
            self._emit(callback, item)
        return failures

    def deploy(self, domains: Iterable[DomainConfig], settings: BatchSettings,
               callback: Callable[[BatchItemResult], None] | None = None) -> list[BatchItemResult]:
        def one(domain: DomainConfig) -> BatchItemResult:
            try:
                self.deployer.deploy(domain)
                return BatchItemResult(domain.name, True, "上传成功", True)
            except Exception as exc:
                return BatchItemResult(domain.name, False, str(exc))

        return self._map(list(domains), settings, one, callback)

    @staticmethod
    def _emit(callback, item):
        if callback:
            callback(item)

    @staticmethod
    def _map(domains, settings, operation, callback):
        results: list[BatchItemResult] = []
        with ThreadPoolExecutor(max_workers=settings.workers(len(domains))) as pool:
            futures = [pool.submit(operation, domain) for domain in domains]
            for future in as_completed(futures):
                item = future.result()
                results.append(item)
                if callback:
                    callback(item)
        return results
