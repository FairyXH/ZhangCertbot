from __future__ import annotations

import os
import posixpath
from pathlib import Path

try:
    import paramiko
except ImportError:  # pragma: no cover - handled by runtime error
    paramiko = None

from .config_manager import ServerConfig


class SSHManager:
    def deploy(self, server: ServerConfig, fullchain: Path, private_key: Path) -> None:
        if paramiko is None:
            raise RuntimeError("未安装 Paramiko，无法执行 SSH 部署")
        key_path = Path(os.path.expandvars(os.path.expanduser(server.private_key.strip().strip('"').strip("'"))))
        if not key_path.exists():
            raise FileNotFoundError(f"SSH 私钥不存在：{key_path}")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(server.host, port=server.port, username=server.username, key_filename=str(key_path), timeout=20)
            sftp = client.open_sftp()
            try:
                self._upload_atomic(sftp, fullchain, server.certificate_path)
                self._upload_atomic(sftp, private_key, server.private_key_path)
            finally:
                sftp.close()
            if server.reload_nginx:
                command = f"nginx -t && {server.reload_command}"
                _, stdout, stderr = client.exec_command(command)
                code = stdout.channel.recv_exit_status()
                if code:
                    raise RuntimeError(f"Nginx 配置测试失败，未执行 reload：{stderr.read().decode(errors='replace').strip()}")
        except paramiko.SSHException as exc:
            raise RuntimeError(f"SSH 连接或上传失败：{exc}") from exc
        finally:
            client.close()

    @staticmethod
    def _upload_atomic(sftp, local: Path, remote: str) -> None:
        temporary = f"{remote}.zhangcertbot-{os.getpid()}.tmp"
        sftp.put(str(local), temporary)
        if sftp.stat(temporary).st_size != local.stat().st_size:
            raise RuntimeError(f"SFTP 上传校验失败：{remote}")
        sftp.rename(temporary, remote)