from pathlib import Path
from types import SimpleNamespace

from src.zhangcertbot.certificate_manager import certificate_files


def test_certificate_files_lists_pem_and_metadata_only(tmp_path: Path):
    (tmp_path / "fullchain.pem").write_text("fullchain", encoding="utf-8")
    (tmp_path / "privkey.pem").write_text("private", encoding="utf-8")
    (tmp_path / "metadata.json").write_text("{}", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")
    assert [item.name for item in certificate_files(tmp_path)] == ["fullchain.pem", "metadata.json", "privkey.pem"]


def test_certificate_files_returns_empty_for_missing_directory(tmp_path: Path):
    assert certificate_files(tmp_path / "missing") == []
