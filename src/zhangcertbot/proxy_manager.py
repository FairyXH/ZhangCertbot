from __future__ import annotations

import configparser
import importlib.util
import os
import socket
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProxyConfig:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 7890

    @property
    def url(self) -> str:
        return f"socks5h://{self.host}:{self.port}"

    def check(self, timeout: float = 1.5) -> tuple[bool, str]:
        if not self.enabled:
            return True, "代理未启用"
        if importlib.util.find_spec("socksio") is None:
            return False, "SOCKS5 代理需要 socksio，请执行：python -m pip install \"httpx[socks]\""
        try:
            with socket.create_connection((self.host, self.port), timeout=timeout):
                return True, f"SOCKS5 代理可连接：{self.host}:{self.port}"
        except OSError as exc:
            return False, f"SOCKS5 代理无法连接：{self.host}:{self.port}：{exc}"
    def environment(self, base: dict[str, str] | None = None) -> dict[str, str]:
        environment = dict(base or os.environ)
        keys = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
        if self.enabled:
            for key in keys:
                environment[key] = self.url
            environment["NO_PROXY"] = "127.0.0.1,localhost"
        else:
            for key in keys:
                environment.pop(key, None)
        return environment


class ProxyManager:
    def __init__(self, root: Path):
        self.path = root / "data" / "runtime" / "proxy.ini"

    def load(self) -> ProxyConfig:
        if not self.path.exists():
            return ProxyConfig()
        parser = configparser.ConfigParser()
        with self.path.open(encoding="utf-8") as handle:
            parser.read_file(handle)
        section = parser["proxy"]
        return ProxyConfig(section.getboolean("enabled", False), section.get("host", "127.0.0.1"), section.getint("port", 7890))

    def save(self, config: ProxyConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        parser = configparser.ConfigParser()
        parser["proxy"] = {"enabled": str(config.enabled).lower(), "host": config.host, "port": str(config.port)}
        with self.path.open("w", encoding="utf-8") as handle:
            parser.write(handle)
