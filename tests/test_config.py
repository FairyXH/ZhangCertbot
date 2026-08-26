from pathlib import Path
from types import SimpleNamespace

import pytest

from src.zhangcertbot.config_manager import ConfigManager, DeploymentBinding, ServerConfig
from src.zhangcertbot.ssh_manager import SSHManager


def server(key_path: str = "key", password: str = ""):
    return ServerConfig(Path("server.ini"), "server", "192.0.2.1", 10140, "root", True, key_path, "/fullchain.pem", "/privkey.pem", True, "systemctl reload nginx", [], password)


def test_server_password_round_trips_and_auth_material_is_required(tmp_path: Path):
    manager = ConfigManager(tmp_path)
    path = manager.write_server({
        "server": {"name": "server", "host": "192.0.2.1", "port": "10140", "username": "admin"},
        "ssh": {"enabled": "true", "private_key": "", "password": "secret"},
        "deploy": {"certificate_path": "/fullchain.pem", "private_key_path": "/privkey.pem", "reload_nginx": "true", "reload_command": "reload"},
        "certificates": {"domains": ""},
    })
    loaded = manager.load_server(path)
    assert loaded.username == "admin"
    assert loaded.password == "secret"
    with pytest.raises(ValueError, match="私钥或密码"):
        manager.write_server({
            "server": {"name": "bad", "host": "192.0.2.1", "port": "22", "username": "root"},
            "ssh": {"enabled": "true", "private_key": "", "password": ""},
            "deploy": {}, "certificates": {},
        })


def test_domain_email_round_trips(tmp_path: Path):
    manager = ConfigManager(tmp_path)
    path = manager.write_domain({
        "name": "example.com",
        "domain": {"name": "example.com", "wildcard": "false", "domains": "example.com"},
        "letsencrypt": {"environment": "production", "email": "admin@example.com", "cert_name": "example.com"},
        "cloudflare": {"api_token": "token", "zone": "example.com"},
        "certificate": {"output_dir": "data/certificates/example.com", "certbot_extra": ""},
        "server": {"deploy": "false", "server": ""},
    })
    assert manager.load_domain(path).email == "admin@example.com"
