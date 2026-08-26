from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config_manager import ConfigManager, DomainConfig
from .proxy_manager import ProxyManager

DIRECTORIES = {
    "production": "https://acme-v02.api.letsencrypt.org/directory",
    "staging": "https://acme-staging-v02.api.letsencrypt.org/directory",
}


@dataclass
class CertbotResult:
    code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.code == 0


class CertbotRunner:
    def __init__(self, root: Path, executable: str = ""):
        self.root = root.resolve()
        self.manager = ConfigManager(self.root)
        self.executable = executable or self._find_executable()
        self.certbot_dir = self.root / "data" / "certbot"
        self.proxy_manager = ProxyManager(self.root)
        self.proxy = self.proxy_manager.load()

    def _find_executable(self) -> str:
        found = shutil.which("certbot") or shutil.which("certbot.exe")
        if found:
            return found
        return "python -m certbot"

    def version(self) -> CertbotResult:
        return self.run(["--version"])

    def run(self, arguments: list[str], on_output: Callable[[str], None] | None = None) -> CertbotResult:
        command = self.executable.split() + arguments if self.executable.startswith("python -m certbot") else [self.executable, *arguments]
        try:
            proxy_ok, proxy_message = self.proxy.check()
            if not proxy_ok:
                if on_output:
                    on_output(proxy_message)
                return CertbotResult(2, "", proxy_message)
        except Exception as exc:
            if on_output:
                on_output(f"代理检查失败：{exc}")
            return CertbotResult(2, "", str(exc))
        try:
            if on_output is None:
                completed = subprocess.run(command, cwd=self.root, env=self.proxy.environment(), text=True, capture_output=True, check=False)
                return CertbotResult(completed.returncode, completed.stdout, completed.stderr)
            process = subprocess.Popen(command, cwd=self.root, env=self.proxy.environment(), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1)
            output: list[str] = []
            assert process.stdout is not None
            for line in process.stdout:
                output.append(line)
                on_output(line.rstrip())
            return CertbotResult(process.wait(), "\n".join(output), "")
        except FileNotFoundError as exc:
            return CertbotResult(127, "", f"未找到 Certbot，请先安装 Certbot：{exc}")

    def _common(self) -> list[str]:
        self.certbot_dir.mkdir(parents=True, exist_ok=True)
        return ["--config-dir", str(self.certbot_dir), "--work-dir", str(self.certbot_dir / "work"),
                "--logs-dir", str(self.root / "logs" / "certbot"), "--non-interactive"]

    def issue(self, domain: DomainConfig, on_output: Callable[[str], None] | None = None) -> CertbotResult:
        credentials = self.manager.credentials_path(domain)
        args = ["certonly", "-v", "--no-verify-ssl", *self._common(), "--dns-cloudflare", "--dns-cloudflare-credentials", str(credentials)]
        if domain.email:
            args.extend(["--email", domain.email])
        else:
            args.append("--register-unsafely-without-email")
        args.extend(["--agree-tos", "--server", DIRECTORIES[domain.environment], "--cert-name", domain.cert_name])
        for name in domain.domains:
            args.extend(["-d", name])
        args.extend(domain.certbot_extra)
        return self.run(args, on_output=on_output)

    def renew(self, dry_run: bool = False, force: bool = False, cert_name: str = "", on_output: Callable[[str], None] | None = None) -> CertbotResult:
        args = ["renew", "-v", "--no-verify-ssl", *self._common()]
        if cert_name:
            args.extend(["--cert-name", cert_name])
        if dry_run:
            args.append("--dry-run")
        if force:
            args.append("--force-renewal")
        if on_output:
            on_output("Certbot：开始执行证书续期")
        return self.run(args, on_output=on_output)

    def certificates(self) -> CertbotResult:
        return self.run(["certificates", "-v", "--no-verify-ssl", *self._common()])

    def live_paths(self, domain: DomainConfig) -> tuple[Path, Path]:
        live = self.certbot_dir / "live" / domain.cert_name
        return live / "fullchain.pem", live / "privkey.pem"