from __future__ import annotations

import os
import posixpath
from pathlib import Path

try:
    import paramiko
except ImportError:  # pragma: no cover - handled by runtime error
    paramiko = None

from .config_manager import DeploymentBinding, ServerConfig


class SSHManager:
    def __init__(self, connect_timeout: float = 20.0, banner_timeout: float = 30.0,
                 auth_timeout: float = 30.0, channel_timeout: float = 30.0):
        self.connect_timeout = connect_timeout
        self.banner_timeout = banner_timeout
        self.auth_timeout = auth_timeout
        self.channel_timeout = channel_timeout

    def deploy(self, server: ServerConfig, fullchain: Path, private_key: Path, binding: DeploymentBinding | None = None) -> None:
        if paramiko is None:
            raise RuntimeError("未安装 Paramiko，无法执行 SSH 部署")
        key_path = Path(os.path.expandvars(os.path.expanduser(server.private_key.strip().strip('"').strip("'"))))
        if not key_path.exists():
            raise FileNotFoundError(f"SSH 私钥不存在：{key_path}")
        binding = binding or DeploymentBinding(server.certificate_path, server.private_key_path, server.reload_nginx, server.reload_command)
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(server.host, port=server.port, username=server.username, key_filename=str(key_path), timeout=self.connect_timeout, banner_timeout=self.banner_timeout, auth_timeout=self.auth_timeout, channel_timeout=self.channel_timeout)
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
                    raise RuntimeError(f"Nginx 配置测试失败，未执行 reload：{stderr.read().decode(errors='replace').strip()}")
        except paramiko.SSHException as exc:
            message = str(exc)
            if "banner" in message.lower():
                raise RuntimeError(f"SSH 协议 Banner 读取失败：{server.host}:{server.port}。请确认该端口确实是 SSH 端口，且服务器未被代理/面板端口替代。") from exc
            raise RuntimeError(f"SSH 连接或上传失败：{message}") from exc
        finally:
            client.close()

    @staticmethod
    def _upload_atomic(sftp, local: Path, remote: str) -> None:
        temporary = f"{remote}.zhangcertbot-{os.getpid()}.tmp"
        sftp.put(str(local), temporary)
        if sftp.stat(temporary).st_size != local.stat().st_size:
            raise RuntimeError(f"SFTP 上传校验失败：{remote}")
        sftp.rename(temporary, remote)