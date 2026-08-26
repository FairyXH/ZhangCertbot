from datetime import datetime, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from src.zhangcertbot.certificate_manager import CertificateManager, certificate_files
from src.zhangcertbot.config_manager import DomainConfig


def make_domain(tmp_path: Path, name="example.com"):
    return DomainConfig(tmp_path / f"{name}.ini", name, [name], False, "production", "", name, "token", name, tmp_path / "output", False, "")


def test_certificate_files_lists_pem_and_metadata_only(tmp_path: Path):
    (tmp_path / "fullchain.pem").write_text("fullchain", encoding="utf-8")
    (tmp_path / "privkey.pem").write_text("private", encoding="utf-8")
    (tmp_path / "metadata.json").write_text("{}", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")
    assert [item.name for item in certificate_files(tmp_path)] == ["fullchain.pem", "metadata.json", "privkey.pem"]


def test_certificate_files_returns_empty_for_missing_directory(tmp_path: Path):
    assert certificate_files(tmp_path / "missing") == []


def test_restore_from_archive_copies_latest_valid_pair(tmp_path: Path):
    from src.zhangcertbot.certbot_runner import CertbotRunner
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(x509.Name([])).issuer_name(x509.Name([])).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now).not_valid_after(now.replace(year=2030)).add_extension(x509.SubjectAlternativeName([x509.DNSName("example.com")]), critical=False).sign(key, hashes.SHA256()))
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    archive = tmp_path / "data" / "certbot" / "archive" / "example.com"
    archive.mkdir(parents=True)
    (archive / "cert2.pem").write_bytes(cert_pem)
    (archive / "fullchain2.pem").write_bytes(cert_pem)
    (archive / "privkey2.pem").write_bytes(key_pem)
    domain = make_domain(tmp_path)
    manager = CertificateManager(CertbotRunner(tmp_path, executable="certbot"))
    assert manager.restore_from_archive(domain) is True
    assert (domain.output_dir / "fullchain.pem").read_bytes() == cert_pem
    assert (domain.output_dir / "privkey.pem").read_bytes() == key_pem
