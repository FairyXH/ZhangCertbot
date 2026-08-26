from pathlib import Path

from src.zhangcertbot.proxy_manager import ProxyConfig, ProxyManager


def test_proxy_config_builds_socks5h_environment():
    config = ProxyConfig(enabled=True, host="127.0.0.1", port=7891)
    environment = config.environment({"PATH": "test"})
    assert environment["HTTPS_PROXY"] == "socks5h://127.0.0.1:7891"
    assert environment["HTTP_PROXY"] == "socks5h://127.0.0.1:7891"
    assert environment["ALL_PROXY"] == "socks5h://127.0.0.1:7891"
    assert environment["NO_PROXY"] == "127.0.0.1,localhost"


def test_proxy_check_reports_refused_port(monkeypatch):
    from src.zhangcertbot.proxy_manager import ProxyConfig
    monkeypatch.setattr("socket.create_connection", lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionRefusedError(10061, "refused")))
    ok, message = ProxyConfig(True, "127.0.0.1", 7890).check()
    assert ok is False
    assert "无法连接" in message

def test_disabled_proxy_removes_proxy_environment():
    config = ProxyConfig(enabled=False, host="127.0.0.1", port=7891)
    environment = config.environment({"HTTPS_PROXY": "old", "HTTP_PROXY": "old", "ALL_PROXY": "old"})
    assert "HTTPS_PROXY" not in environment
    assert "HTTP_PROXY" not in environment
    assert "ALL_PROXY" not in environment


def test_proxy_settings_round_trip(tmp_path: Path):
    manager = ProxyManager(tmp_path)
    manager.save(ProxyConfig(enabled=True, host="127.0.0.1", port=1080))
    loaded = manager.load()
    assert loaded == ProxyConfig(enabled=True, host="127.0.0.1", port=1080)
