from pathlib import Path

from src.zhangcertbot.config_manager import ConfigManager, mask_secret, resolve_path, validate_domains


def test_validate_domains_normalizes_wildcard_and_rejects_url():
    assert validate_domains(["Example.COM.", "*.example.com"]) == ["example.com", "*.example.com"]
    try:
        validate_domains(["https://example.com"])
    except ValueError as exc:
        assert "域名格式错误" in str(exc)
    else:
        raise AssertionError("URL 应被拒绝")


def test_quoted_windows_path_is_normalized(tmp_path: Path):
    assert resolve_path(r'"D:\\Important\\SSH私钥\\襄阳一区"', tmp_path) == Path(r"D:\Important\SSH私钥\襄阳一区")


def test_write_server_accepts_nested_server_name(tmp_path: Path):
    manager = ConfigManager(tmp_path)
    path = manager.write_server({
        "server": {"name": "Zhang服务器", "host": "111.170.173.22", "port": "10140", "username": "root"},
        "ssh": {"enabled": "true", "private_key": r'"D:\Important\SSH私钥\襄阳一区"'},
        "deploy": {"certificate_path": "/remote/fullchain.pem", "private_key_path": "/remote/privkey.pem", "reload_nginx": "true", "reload_command": "systemctl reload nginx"},
        "certificates": {"domains": ""},
    })
    loaded = manager.load_server(path)
    assert loaded.name == "Zhang服务器"
    assert loaded.port == 10140
    assert loaded.ssh_enabled is True
    assert "Zhang服务器" in path.read_text(encoding="utf-8")


def test_load_multiple_servers_and_domains(tmp_path: Path):
    manager = ConfigManager(tmp_path)
    manager.ensure_dirs()
    (manager.servers_dir / "server1-config.ini").write_text(
        """[server]\nname = server1\nhost = 192.0.2.1\nport = 22\nusername = root\n\n[ssh]\nenabled = true\nprivate_key = ~/.ssh/id_ed25519\n\n[deploy]\ncertificate_path = /etc/nginx/fullchain.pem\nprivate_key_path = /etc/nginx/privkey.pem\nreload_nginx = true\nreload_command = systemctl reload nginx\n\n[certificates]\ndomains = example.com.ini\n""", encoding="utf-8")
    (manager.domains_dir / "example.ini").write_text(
        """[domain]\nname = example.com\nwildcard = true\ndomains = example.com, *.example.com\n[letsencrypt]\nenvironment = staging\nemail = admin@example.com\ncert_name = example.com\n[cloudflare]\napi_token = secret-token\nzone = example.com\n[certificate]\noutput_dir = data/certificates/example.com\n[server]\ndeploy = true\nserver = server1-config.ini\n""", encoding="utf-8")
    server = manager.list_servers()[0]
    domain = manager.list_domains()[0]
    assert server.host == "192.0.2.1"
    assert server.ssh_enabled is True
    assert domain.environment == "staging"
    assert domain.domains == ["example.com", "*.example.com"]
    assert domain.output_dir == tmp_path / "data/certificates/example.com"


def test_credentials_are_written_separately_and_token_is_masked(tmp_path: Path):
    manager = ConfigManager(tmp_path)
    manager.ensure_dirs()
    path = manager.domains_dir / "example.ini"
    path.write_text(
        """[domain]\nname = example.com\ndomains = example.com\n[letsencrypt]\nenvironment = production\nemail = a@b.com\n[cloudflare]\napi_token = secret-token\n[certificate]\noutput_dir = data/certificates/example.com\n[server]\ndeploy = false\n""", encoding="utf-8")
    domain = manager.list_domains()[0]
    credentials = manager.credentials_path(domain)
    assert credentials.read_text(encoding="utf-8") == "dns_cloudflare_api_token = secret-token\n"
    assert mask_secret(domain.api_token) == "已配置"
