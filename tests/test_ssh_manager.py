from pathlib import Path
from types import SimpleNamespace

import pytest

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
    with pytest.raises(RuntimeError, match="SSH 协议 Banner 读取失败"):
        SSHManager().deploy(server(str(key)), tmp_path / "fullchain.pem", tmp_path / "privkey.pem")


def test_ssh_connect_disables_agent_and_retries_banner(monkeypatch, tmp_path: Path):
    calls = []
    class ParamikoError(Exception): pass
    monkeypatch.setattr("src.zhangcertbot.ssh_manager.paramiko.SSHException", ParamikoError)
    class Client:
        def set_missing_host_key_policy(self, policy): pass
        def connect(self, **kwargs):
            calls.append(kwargs)
            if len(calls) < 2:
                raise ParamikoError("Error reading SSH protocol banner")
        def open_sftp(self):
            raise AssertionError("connection test should fail before SFTP in this test")
        def close(self): pass
    monkeypatch.setattr("src.zhangcertbot.ssh_manager.paramiko.SSHClient", lambda: Client())
    key = tmp_path / "key"
    key.write_text("key", encoding="utf-8")
    manager = SSHManager(connect_attempts=2, retry_delay=0)
    with pytest.raises(AssertionError):
        manager.deploy(server(str(key)), tmp_path / "fullchain.pem", tmp_path / "privkey.pem")
    assert len(calls) == 2
    assert calls[-1]["allow_agent"] is False
    assert calls[-1]["look_for_keys"] is False
    assert calls[-1]["banner_timeout"] == 60.0
