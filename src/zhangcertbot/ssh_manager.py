from __future__ import annotations

import os
import posixpath
import time
from pathlib import Path

try:
    import paramiko
except ImportError:  # pragma: no cover - handled by runtime error
    paramiko = None

from .config_manager import DeploymentBinding, ServerConfig


class SSHManager:
    def __init__(self, connect_timeout: float = 20.0, banner_timeout: float = 60.0,
                 auth_timeout: float = 30.0, channel_timeout: float = 30.0,
                 connect_attempts: int = 3, retry_delay: float = 1.0):
        self.connect_timeout = connect_timeout
        self.banner_timeout = banner_timeout
        self.auth_timeout = auth_timeout
        self.channel_timeout = channel_timeout
        self.connect_attempts = max(1, int(connect_attempts))
        self.retry_delay = max(0.0, float(retry_delay))

    @staticmethod
    def _key_path(server: ServerConfig) -> Path:
        value = server.private_key.strip().strip('"').strip("'")
        return Path(os.path.expandvars(os.path.expanduser(value)))

    def connect(self, server: ServerConfig):
        if paramiko is None:
            raise RuntimeError("未安装 Paramiko，无法执行 SSH 操作")
        key_path = self._key_path(server)
        if not key_path.is_file() and not server.password:
            raise ValueError("SSH 私钥或密码至少需要配置一个")
        last_error = None
        for attempt in range(1, self.connect_attempts + 1):
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                client.connect(
                    hostname=server.host,
                    port=server.port,
                    username=server.username or "root",
                    key_filename=str(key_path) if key_path.is_file() else None,
                    password=server.password or None,
                    timeout=self.connect_timeout,
                    banner_timeout=self.banner_timeout,
                    auth_timeout=self.auth_timeout,
                    channel_timeout=self.channel_timeout,
                    allow_agent=False,
                    look_for_keys=False,
                )
                return client
            except paramiko.SSHException as exc:
                last_error = exc
                client.close()
                if "banner" not in str(exc).lower() or attempt >= self.connect_attempts:
                    break
                if self.retry_delay:
                    time.sleep(self.retry_delay)
        message = str(last_error) if last_error else f"{server.host}:{server.port}"
        if last_error and "banner" in message.lower():
            raise RuntimeError(f"SSH 协议 Banner 读取失败：{server.host}:{server.port}。XShell 可连接时，请检查是否使用了跳板机、代理或不同 SSH 算法配置。") from last_error
        raise RuntimeError(f"SSH 连接失败：{message}") from last_error

    def open_shell(self, server: ServerConfig):
        client = self.connect(server)
        try:
            channel = client.invoke_shell()
            channel.settimeout(0.2)
            return client, channel
        except Exception:
            client.close()
            raise

    def deploy(self, server: ServerConfig, fullchain: Path, private_key: Path,
               binding: DeploymentBinding | None = None) -> None:
        binding = binding or DeploymentBinding(
            server.certificate_path,
            server.private_key_path,
            server.reload_nginx,
            server.reload_command,
        )
        client = self.connect(server)
        try:
            sftp = client.open_sftp()
            try:
                self._upload_atomic(sftp, fullchain, binding.certificate_path)
                self._upload_atomic(sftp, private_key, binding.private_key_path)
            finally:
                sftp.close()
            if binding.reload_nginx:
                command = f"nginx -t && {binding.reload_command}"
                _, stdout, stderr = client.exec_command(command)
                code = stdout.channel.recv_exit_status()
                if code:
                    error = stderr.read().decode(errors="replace").strip()
                    raise RuntimeError(f"Nginx 配置测试失败，未执行 reload：{error}")
        finally:
            client.close()

    @staticmethod
    def _upload_atomic(sftp, local: Path, remote: str) -> None:
        temporary = f"{remote}.zhangcertbot-{os.getpid()}.tmp"
        sftp.put(str(local), temporary)
        if sftp.stat(temporary).st_size != local.stat().st_size:
            raise RuntimeError(f"SFTP 上传校验失败：{remote}")
        sftp.rename(temporary, remote)
