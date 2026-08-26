from pathlib import Path
from types import SimpleNamespace

from src.zhangcertbot.config_manager import DeploymentBinding, ServerConfig
from src.zhangcertbot.ssh_manager import SSHManager


def server(key_path: str = "key"):
    return ServerConfig(Path("server.ini"), "server", "192.0.2.1", 10140, "root", True, key_path, "/fullchain.pem", "/privkey.pem", True, "systemctl reload nginx")


def test_ssh_banner_failure_is_reported_as_port_problem(monkeypatch, tmp_path: Path):
    class Client:
        def set_missing_host_key_policy(self, policy): pass
        def connect(self, **kwargs): raise RuntimeError("not used")
        def close(self): pass
    class ParamikoError(Exception): pass
    monkeypatch.setattr("src.zhangcertbot.ssh_manager.paramiko.SSHException", ParamikoError)
    def fail_connect(*args, **kwargs): raise ParamikoError("Error reading SSH protocol banner")
    client = Client()
    client.connect = fail_connect
    monkeypatch.setattr("src.zhangcertbot.ssh_manager.paramiko.SSHClient", lambda: client)
    key = tmp_path / "key"
    key.write_text("key", encoding="utf-8")
    with __import__("pytest").raises(RuntimeError, match="SSH 协议 Banner 读取失败"):
        SSHManager().deploy(server(str(key)), tmp_path / "fullchain.pem", tmp_path / "privkey.pem")
