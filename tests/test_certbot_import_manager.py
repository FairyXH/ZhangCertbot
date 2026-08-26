from pathlib import Path

from src.zhangcertbot.certbot_import_manager import CertbotImportManager


def test_parse_renewal_file_reads_flat_certbot_fields(tmp_path: Path):
    path = tmp_path / "example.com.conf"
    path.write_text(
        "version = 5.7.0\narchive_dir = C:/old/archive/example.com\n"
        "[renewalparams]\naccount = account-id\nemail = admin@example.com\n",
        encoding="utf-8",
    )
    result = CertbotImportManager.parse_renewal(path)
    assert result["archive_dir"] == "C:/old/archive/example.com"
    assert result["account"] == "account-id"
    assert result["email"] == "admin@example.com"


def test_sync_imports_unclaimed_archive_without_overwriting_existing_domain(tmp_path: Path):
    source = tmp_path / "old-certbot"
    archive = source / "archive" / "new.example.com"
    archive.mkdir(parents=True)
    (archive / "cert1.pem").write_text("cert", encoding="utf-8")
    (archive / "fullchain1.pem").write_text("fullchain", encoding="utf-8")
    (archive / "privkey1.pem").write_text("private", encoding="utf-8")
    (archive / "chain1.pem").write_text("chain", encoding="utf-8")
    renewal = source / "renewal"
    renewal.mkdir()
    (renewal / "new.example.com.conf").write_text(
        f"archive_dir = {archive}\n[renewalparams]\naccount = account-id\nemail = admin@example.com\n",
        encoding="utf-8",
    )
    manager = CertbotImportManager(tmp_path / "project")
    manager.add_path(source)
    imported = manager.sync()
    assert imported == ["new.example.com"]
    assert (tmp_path / "project" / "data" / "domains" / "new.example.com.ini").exists()
    assert (tmp_path / "project" / "data" / "certificates" / "new.example.com" / "fullchain.pem").read_text(encoding="utf-8") == "fullchain"
    assert manager.sync() == []
