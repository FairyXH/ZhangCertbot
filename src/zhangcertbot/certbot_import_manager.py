from __future__ import annotations

import json
import shutil
from pathlib import Path

from .config_manager import ConfigManager


class CertbotImportManager:
    def __init__(self, project_root: Path):
        self.root = project_root.resolve()
        self.config = ConfigManager(self.root)
        self.config.ensure_dirs()
        self.settings_path = self.root / "data" / "runtime" / "certbot-imports.json"
        self.certbot_dir = self.root / "data" / "certbot"

    @staticmethod
    def parse_renewal(path: Path) -> dict[str, str]:
        values: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("[") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
        return values

    def paths(self) -> list[Path]:
        if not self.settings_path.exists():
            return []
        try:
            return [Path(item) for item in json.loads(self.settings_path.read_text(encoding="utf-8"))]
        except (OSError, ValueError, TypeError):
            return []

    def save_paths(self, paths: list[Path]) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(
            json.dumps([str(path.resolve()) for path in paths], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add_path(self, path: Path) -> bool:
        path = path.resolve()
        if not path.is_dir():
            raise ValueError(f"Certbot 目录不存在：{path}")
        paths = self.paths()
        if path in paths:
            return False
        paths.append(path)
        self.save_paths(paths)
        return True

    def remove_path(self, index: int) -> None:
        paths = self.paths()
        if 0 <= index < len(paths):
            paths.pop(index)
            self.save_paths(paths)

    def sync(self) -> list[str]:
        imported: list[str] = []
        existing = {domain.cert_name for domain in self.config.list_domains()}
        for source_root in self.paths():
            renewal_dir = source_root / "renewal"
            for renewal in sorted(renewal_dir.glob("*.conf")) if renewal_dir.is_dir() else []:
                cert_name = renewal.stem
                if cert_name in existing:
                    continue
                values = self.parse_renewal(renewal)
                source_archive = Path(values.get("archive_dir", ""))
                if not source_archive.is_absolute():
                    source_archive = source_root / source_archive
                pair = self._latest_pair(source_archive)
                if pair is None:
                    continue
                target_archive = self.certbot_dir / "archive" / cert_name
                target_archive.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(source_archive, target_archive, dirs_exist_ok=True)
                self._copy_accounts(source_root)
                output = self.config.certificates_dir / cert_name
                output.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(pair[0], output / "fullchain.pem")
                shutil.copyfile(pair[1], output / "privkey.pem")
                token = self._read_token(source_root, values.get("dns_cloudflare_credentials", ""))
                names = self._certificate_names(pair[0], cert_name)
                base = next((name.removeprefix("*.") for name in names if name.startswith("*.")), cert_name)
                domain_values = {
                    "name": next((name for name in names if name.startswith("*.")), names[0]),
                    "domain": {"name": next((name for name in names if name.startswith("*.")), names[0]), "wildcard": str(any(name.startswith("*.") for name in names)).lower(), "domains": ", ".join(names)},
                    "letsencrypt": {"environment": "staging" if "staging" in values.get("server", "") else "production", "email": values.get("email", ""), "cert_name": cert_name},
                    "cloudflare": {"api_token": token, "zone": base},
                    "certificate": {"output_dir": str(output), "certbot_extra": ""},
                    "server": {"deploy": "false", "server": ""},
                }
                self.config.write_domain(domain_values)
                self._copy_renewal(renewal, cert_name, values)
                existing.add(cert_name)
                imported.append(cert_name)
        return imported

    def _copy_accounts(self, source_root: Path) -> None:
        source = source_root / "accounts"
        target = self.certbot_dir / "accounts"
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)

    def _copy_renewal(self, source: Path, cert_name: str, values: dict[str, str]) -> None:
        target = self.certbot_dir / "renewal" / f"{cert_name}.conf"
        target.parent.mkdir(parents=True, exist_ok=True)
        archive = self.certbot_dir / "archive" / cert_name
        live = self.certbot_dir / "live" / cert_name
        credentials = self.config.cloudflare_dir / f"imported-{cert_name}.ini"
        token = self._read_token(source.parent.parent, values.get("dns_cloudflare_credentials", ""))
        if token:
            credentials.write_text(f"dns_cloudflare_api_token = {token}\n", encoding="utf-8")
        lines = [
            "version = 5.7.0",
            f"archive_dir = {archive}",
            f"cert = {live / 'cert.pem'}",
            f"privkey = {live / 'privkey.pem'}",
            f"chain = {live / 'chain.pem'}",
            f"fullchain = {live / 'fullchain.pem'}",
            "[renewalparams]",
            f"account = {values.get('account', '')}",
            f"config_dir = {self.certbot_dir}",
            f"work_dir = {self.certbot_dir / 'work'}",
            f"logs_dir = {self.root / 'logs' / 'certbot'}",
            f"server = {values.get('server', 'https://acme-v02.api.letsencrypt.org/directory')}",
            "authenticator = dns-cloudflare",
            f"dns_cloudflare_credentials = {credentials}",
            "key_type = ecdsa",
            "",
        ]
        target.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _read_token(source_root: Path, configured: str) -> str:
        path = Path(configured)
        if not path.is_absolute():
            path = source_root / path
        if not path.is_file():
            return ""
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip().startswith("dns_cloudflare_api_token") and "=" in line:
                return line.split("=", 1)[1].strip()
        return ""

    @staticmethod
    def _certificate_names(certificate: Path, fallback: str) -> list[str]:
        try:
            from cryptography import x509
            cert = x509.load_pem_x509_certificate(certificate.read_bytes())
            extension = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            names = extension.value.get_values_for_type(x509.DNSName)
            if names:
                return names
        except Exception:
            pass
        return [fallback]

    @staticmethod
    def _latest_pair(archive: Path) -> tuple[Path, Path] | None:
        candidates = []
        for fullchain in archive.glob("fullchain*.pem"):
            suffix = fullchain.stem.removeprefix("fullchain")
            if not suffix.isdigit():
                continue
            private_key = archive / f"privkey{suffix}.pem"
            if private_key.exists():
                candidates.append((int(suffix), fullchain, private_key))
        if not candidates:
            return None
        _, fullchain, private_key = max(candidates, key=lambda item: item[0])
        return fullchain, private_key
