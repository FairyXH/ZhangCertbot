from pathlib import Path
from types import SimpleNamespace

from src.zhangcertbot.certbot_runner import CertbotRunner, DIRECTORIES
from src.zhangcertbot.config_manager import ConfigManager, DomainConfig


def make_domain(tmp_path: Path, environment: str = "production", email: str = "admin@example.com") -> DomainConfig:
    return DomainConfig(tmp_path / "example.ini", "example.com", ["example.com", "*.example.com"], True,
                        environment, email, "example.com", "token", "example.com",
                        tmp_path / "output", False, "")


def test_account_for_reads_certbot_flat_renewal_file(tmp_path: Path):
    runner = CertbotRunner(tmp_path, executable="certbot")
    runner.certbot_dir.joinpath("renewal").mkdir(parents=True)
    runner.certbot_dir.joinpath("renewal", "example.com.conf").write_text(
        "version = 5.7.0\narchive_dir = old\n[renewalparams]\naccount = account-id\n", encoding="utf-8"
    )
    assert runner.account_for(make_domain(tmp_path)) == "account-id"


def test_issue_command_uses_verbose_and_insecure_ssl_flags(tmp_path: Path, monkeypatch):
    runner = CertbotRunner(tmp_path, executable="certbot")
    captured = {}
    monkeypatch.setattr(runner, "run", lambda arguments, **kwargs: captured.setdefault("args", arguments))
    runner.issue(make_domain(tmp_path, "staging"))
    args = captured["args"]
    assert "-v" in args
    assert "--no-verify-ssl" in args
    assert "--dns-cloudflare" in args
    assert "--dns-cloudflare-credentials" in args
    assert DIRECTORIES["staging"] in args
    assert "--agree-tos" in args
    assert "token" not in args
    assert args.count("-d") == 2


def test_issue_without_email_still_agrees_to_terms(tmp_path: Path, monkeypatch):
    runner = CertbotRunner(tmp_path, executable="certbot")
    captured = {}
    monkeypatch.setattr(runner, "run", lambda arguments, **kwargs: captured.setdefault("args", arguments))
    runner.issue(make_domain(tmp_path, email=""))
    args = captured["args"]
    assert "--register-unsafely-without-email" in args
    assert "--agree-tos" in args


def test_renew_does_not_force_by_default(tmp_path: Path, monkeypatch):
    runner = CertbotRunner(tmp_path, executable="certbot")
    captured = {}
    monkeypatch.setattr(runner, "run", lambda arguments, **kwargs: captured.setdefault("args", arguments))
    runner.renew()
    assert captured["args"][0] == "renew"
    assert "-v" in captured["args"]
    assert "--no-verify-ssl" in captured["args"]
    assert "--force-renewal" not in captured["args"]


def test_wildcard_domain_name_round_trips(tmp_path: Path):
    manager = ConfigManager(tmp_path)
    path = manager.write_domain({
        "name": "*.zhangfairy.ccwu.cc",
        "domain": {"name": "*.zhangfairy.ccwu.cc", "wildcard": "true", "domains": "zhangfairy.ccwu.cc, *.zhangfairy.ccwu.cc"},
        "letsencrypt": {"environment": "production", "email": "", "cert_name": "zhangfairy.ccwu.cc"},
        "cloudflare": {"api_token": "token", "zone": "zhangfairy.ccwu.cc"},
        "certificate": {"output_dir": "data/certificates/zhangfairy.ccwu.cc", "certbot_extra": ""},
        "server": {"deploy": "false", "server": ""},
    })
    loaded = manager.load_domain(path)
    assert loaded.name == "*.zhangfairy.ccwu.cc"
    assert loaded.domains == ["zhangfairy.ccwu.cc", "*.zhangfairy.ccwu.cc"]


def test_config_manager_deletes_server_and_domain(tmp_path: Path):
    manager = ConfigManager(tmp_path)
    server = manager.write_server({
        "server": {"name": "server", "host": "192.0.2.1", "port": "22", "username": "root"},
        "ssh": {"enabled": "true", "private_key": "key"},
        "deploy": {"certificate_path": "/fullchain.pem", "private_key_path": "/privkey.pem", "reload_nginx": "true", "reload_command": "reload"},
        "certificates": {"domains": ""},
    })
    domain = manager.write_domain({
        "name": "example.com", "domain": {"name": "example.com", "wildcard": "false", "domains": "example.com"},
        "letsencrypt": {"environment": "production", "email": "", "cert_name": "example.com"},
        "cloudflare": {"api_token": "token", "zone": "example.com"},
        "certificate": {"output_dir": "data/certificates/example.com", "certbot_extra": ""},
        "server": {"deploy": "false", "server": ""},
    })
    manager.delete_server(server)
    manager.delete_domain(domain)
    assert not server.exists()
    assert not domain.exists()
