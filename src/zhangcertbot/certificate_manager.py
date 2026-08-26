from __future__ import annotations

import os
import shutil
from pathlib import Path


CERTIFICATE_FILE_NAMES = {"cert.pem", "chain.pem", "fullchain.pem", "privkey.pem", "metadata.json"}


def certificate_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted((path for path in directory.iterdir() if path.is_file() and path.name in CERTIFICATE_FILE_NAMES), key=lambda path: path.name)

from .certbot_runner import CertbotRunner
from .config_manager import DomainConfig


def atomic_copy(source: Path, target: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Certbot 证书文件不存在：{source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp-{os.getpid()}")
    try:
        shutil.copyfile(source, temporary)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


class CertificateManager:
    def __init__(self, runner: CertbotRunner):
        self.runner = runner

    def export(self, domain: DomainConfig) -> bool:
        fullchain, private_key = self.runner.live_paths(domain)
        if not fullchain.exists() or not private_key.exists():
            raise FileNotFoundError(f"Certbot 证书不存在：{domain.cert_name}")
        changed = False
        for source, name in ((fullchain, "fullchain.pem"), (private_key, "privkey.pem")):
            target = domain.output_dir / name
            old = target.read_bytes() if target.exists() else None
            data = source.read_bytes()
            if old != data:
                atomic_copy(source, target)
                changed = True
        return changed

    def status(self, domain: DomainConfig) -> str:
        fullchain, _ = self.runner.live_paths(domain)
        if not fullchain.exists():
            return "未找到证书"
        return f"Certbot 证书：{fullchain}"