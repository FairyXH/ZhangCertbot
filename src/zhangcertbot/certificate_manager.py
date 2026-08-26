from __future__ import annotations

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

    def restore_from_archive(self, domain: DomainConfig) -> bool:
        archive = self.runner.certbot_dir / "archive" / domain.cert_name
        candidates: list[tuple[int, Path, Path]] = []
        for cert_path in archive.glob("cert*.pem"):
            match = re.fullmatch(r"cert([0-9]+)\.pem", cert_path.name, flags=re.IGNORECASE)
            if not match:
                continue
            number = int(match.group(1))
            fullchain = archive / f"fullchain{number}.pem"
            private_key = archive / f"privkey{number}.pem"
            if fullchain.exists() and private_key.exists():
                candidates.append((number, fullchain, private_key))
        for _number, fullchain, private_key in sorted(candidates, reverse=True):
            try:
                certificate = x509.load_pem_x509_certificate(fullchain.read_bytes())
                key = serialization.load_pem_private_key(private_key.read_bytes(), password=None)
                if certificate.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo) != key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo):
                    continue
                changed = False
                for source, name in ((fullchain, "fullchain.pem"), (private_key, "privkey.pem")):
                    target = domain.output_dir / name
                    if not target.exists() or target.read_bytes() != source.read_bytes():
                        atomic_copy(source, target)
                        changed = True
                return changed
            except (OSError, ValueError, TypeError):
                continue
        return False
    def status(self, domain: DomainConfig) -> str:
        fullchain, _ = self.runner.live_paths(domain)
        if not fullchain.exists():
            return "未找到证书"
        return f"Certbot 证书：{fullchain}"