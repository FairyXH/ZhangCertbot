from __future__ import annotations

from .certificate_manager import CertificateManager
from .config_manager import ConfigManager, DomainConfig
from .ssh_manager import SSHManager


class DeployManager:
    def __init__(self, config: ConfigManager, certificates: CertificateManager, ssh: SSHManager | None = None):
        self.config = config
        self.certificates = certificates
        self.ssh = ssh or SSHManager()

    def deploy(self, domain: DomainConfig) -> str:
        if not domain.deploy:
            return "本地保存"
        servers = {server.file.name: server for server in self.config.list_servers()}
        server = servers.get(domain.server_file)
        if server is None:
            raise ValueError(f"服务器配置不存在：{domain.server_file}")
        if not server.ssh_enabled:
            raise ValueError(f"服务器未启用 SSH 上传：{server.name}")
        fullchain = domain.output_dir / "fullchain.pem"
        private_key = domain.output_dir / "privkey.pem"
        self.ssh.deploy(server, fullchain, private_key)
        return server.name