from __future__ import annotations

import configparser
import os
import re
import shutil
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization


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
            try:
                os.fsync(handle.fileno())
            except OSError as exc:
                if getattr(exc, "errno", None) != 9:
                    raise
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


class CertificateManager:
    def __init__(self, runner: CertbotRunner):
        self.runner = runner

    def _archive_pair(self, domain: DomainConfig):
        archive = self.runner.certbot_dir / "archive" / domain.cert_name
        candidates = []
        for cert_path in archive.glob("cert*.pem"):
            match = re.fullmatch(r"cert([0-9]+)\.pem", cert_path.name, flags=re.IGNORECASE)
            if not match:
                continue
            number = int(match.group(1))
            files = {name: archive / f"{name}{number}.pem" for name in ("cert", "chain", "fullchain", "privkey")}
            if files["fullchain"].exists() and files["privkey"].exists():
                if not files["chain"].exists():
                    files["chain"] = files["cert"]
                candidates.append((number, files))
        return archive, (max(candidates, key=lambda item: item[0]) if candidates else None)

    def adopt_existing(self, domain: DomainConfig) -> bool:
        archive, candidate = self._archive_pair(domain)
        if candidate is None:
            return False
        number, files = candidate
        try:
            certificate = x509.load_pem_x509_certificate(files["fullchain"].read_bytes())
            key = serialization.load_pem_private_key(files["privkey"].read_bytes(), password=None)
            if certificate.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo) != key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo):
                return False
        except (OSError, ValueError, TypeError):
            return False
        live = self.runner.certbot_dir / "live" / domain.cert_name
        live.mkdir(parents=True, exist_ok=True)
        for name in ("cert", "chain", "fullchain", "privkey"):
            link = live / f"{name}.pem"
            if link.exists() or link.is_symlink():
                if link.is_symlink():
                    link.unlink()
                else:
                    backup = link.with_name(f"{link.name}.bak")
                    if not backup.exists():
                        link.replace(backup)
                    else:
                        link.unlink()
            relative_target = os.path.relpath(files[name], live)
            os.symlink(relative_target, link)
        renewal = self.runner.certbot_dir / "renewal" / f"{domain.cert_name}.conf"
        renewal.parent.mkdir(parents=True, exist_ok=True)
        account = self.runner.account_for(domain) or ""
        credentials = self.runner.manager.credentials_path(domain)
        lines = [
            "version = 5.7.0",
            f"archive_dir = {archive}",
            f"cert = {live / 'cert.pem'}",
            f"privkey = {live / 'privkey.pem'}",
            f"chain = {live / 'chain.pem'}",
            f"fullchain = {live / 'fullchain.pem'}",
            "[renewalparams]",
            f"account = {account}",
            f"config_dir = {self.runner.certbot_dir}",
            f"work_dir = {self.runner.certbot_dir / 'work'}",
            f"logs_dir = {self.runner.root / 'logs' / 'certbot'}",
            f"server = {self.runner.server_url(domain)}",
            "authenticator = dns-cloudflare",
            f"dns_cloudflare_credentials = {credentials}",
            "key_type = ecdsa",
            "",
        ]
        renewal.write_text("\n".join(lines), encoding="utf-8")
        return True

    def export(self, domain: DomainConfig) -> bool:
        fullchain, private_key = self.runner.live_paths(domain)
        if not fullchain.exists() or not private_key.exists():
            self.adopt_existing(domain)
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

    def restore_from_archive(self, domain: DomainConfig) -> bool:
        try:
            adopted = self.adopt_existing(domain)
            if adopted:
                self.export(domain)
            return adopted
        except (OSError, ValueError, TypeError):
            return False

    def status(self, domain: DomainConfig) -> str:
        fullchain, _ = self.runner.live_paths(domain)
        if not fullchain.exists():
            self.adopt_existing(domain)
        if not fullchain.exists():
            return "未找到证书"
        return f"Certbot 证书：{fullchain}"
