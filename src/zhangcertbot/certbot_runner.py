from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config_manager import ConfigManager, DomainConfig

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

    def _find_executable(self) -> str:
        found = shutil.which("certbot") or shutil.which("certbot.exe")
        if found:
            return found
        return "python -m certbot"

    def version(self) -> CertbotResult:
        return self.run(["--version"])

    def run(self, arguments: list[str]) -> CertbotResult:
        command = self.executable.split() + arguments if self.executable.startswith("python -m certbot") else [self.executable, *arguments]
        try:
            completed = subprocess.run(command, cwd=self.root, text=True, capture_output=True, check=False)
        except FileNotFoundError as exc:
            return CertbotResult(127, "", f"未找到 Certbot，请先安装 Certbot：{exc}")
        return CertbotResult(completed.returncode, completed.stdout, completed.stderr)

    def _common(self) -> list[str]:
        self.certbot_dir.mkdir(parents=True, exist_ok=True)
        return ["--config-dir", str(self.certbot_dir), "--work-dir", str(self.certbot_dir / "work"),
                "--logs-dir", str(self.root / "logs" / "certbot"), "--non-interactive"]

    def issue(self, domain: DomainConfig) -> CertbotResult:
        credentials = self.manager.credentials_path(domain)
        args = ["certonly", *self._common(), "--dns-cloudflare", "--dns-cloudflare-credentials", str(credentials),
                "--email", domain.email, "--agree-tos", "--server", DIRECTORIES[domain.environment],
                "--cert-name", domain.cert_name]
        for name in domain.domains:
            args.extend(["-d", name])
        args.extend(domain.certbot_extra)
        return self.run(args)

    def renew(self, dry_run: bool = False, force: bool = False) -> CertbotResult:
        args = ["renew", *self._common()]
        if dry_run:
            args.append("--dry-run")
        if force:
            args.append("--force-renewal")
        return self.run(args)

    def certificates(self) -> CertbotResult:
        return self.run(["certificates", *self._common()])

    def live_paths(self, domain: DomainConfig) -> tuple[Path, Path]:
        live = self.certbot_dir / "live" / domain.cert_name
        return live / "fullchain.pem", live / "privkey.pem"