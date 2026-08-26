from pathlib import Path

from src.zhangcertbot.certbot_runner import CertbotRunner, DIRECTORIES
from src.zhangcertbot.config_manager import DomainConfig


def make_domain(tmp_path: Path, environment: str = "production") -> DomainConfig:
    return DomainConfig(tmp_path / "example.ini", "example.com", ["example.com", "*.example.com"], True,
                        environment, "admin@example.com", "example.com", "token", "example.com",
                        tmp_path / "output", False, "")


def test_issue_command_uses_credentials_and_environment(tmp_path: Path, monkeypatch):
    runner = CertbotRunner(tmp_path, executable="certbot")
    captured = {}
    monkeypatch.setattr(runner, "run", lambda arguments: captured.setdefault("args", arguments))
    runner.issue(make_domain(tmp_path, "staging"))
    args = captured["args"]
    assert "--dns-cloudflare" in args
    assert "--dns-cloudflare-credentials" in args
    assert DIRECTORIES["staging"] in args
    assert "token" not in args
    assert args.count("-d") == 2


def test_renew_does_not_force_by_default(tmp_path: Path, monkeypatch):
    runner = CertbotRunner(tmp_path, executable="certbot")
    captured = {}
    monkeypatch.setattr(runner, "run", lambda arguments: captured.setdefault("args", arguments))
    runner.renew()
    assert captured["args"][0] == "renew"
    assert "--force-renewal" not in captured["args"]
