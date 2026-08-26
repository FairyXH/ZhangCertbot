from __future__ import annotations

import configparser
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path


def resolve_path(value: str, root: Path) -> Path:
    value = value.strip().strip('"').strip("'")
    path = Path(os.path.expandvars(os.path.expanduser(value)))
    return path if path.is_absolute() else root / path


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def validate_domains(domains: list[str]) -> list[str]:
    if not domains:
        raise ValueError("至少需要配置一个域名")
    result: list[str] = []
    for raw in domains:
        domain = raw.strip().lower().rstrip(".")
        base = domain[2:] if domain.startswith("*.") else domain
        if not base or "://" in domain or "/" in domain or " " in domain:
            raise ValueError(f"域名格式错误：{raw}")
        if domain.startswith("*.") and (domain.count("*") != 1 or base.count(".") < 1):
            raise ValueError(f"泛域名格式错误：{raw}")
        if "*" in base or base.count(".") < 1:
            raise ValueError(f"域名格式错误：{raw}")
        labels = base.split(".")
        if any(not label or len(label) > 63 or label[0] == "-" or label[-1] == "-" for label in labels):
            raise ValueError(f"域名格式错误：{raw}")
        if any(not all(char.isalnum() or char == "-" for char in label) for label in labels):
            raise ValueError(f"域名格式错误：{raw}")
        if domain not in result:
            result.append(domain)
    return result


@dataclass
class ServerConfig:
    file: Path
    name: str
    host: str
    port: int
    username: str
    ssh_enabled: bool
    private_key: str
    certificate_path: str
    private_key_path: str
    reload_nginx: bool
    reload_command: str
    domains: list[str] = field(default_factory=list)


@dataclass
class DomainConfig:
    file: Path
    name: str
    domains: list[str]
    wildcard: bool
    environment: str
    email: str
    cert_name: str
    api_token: str
    zone: str
    output_dir: Path
    deploy: bool
    server_file: str
    certbot_extra: list[str] = field(default_factory=list)
    bindings: dict[str, "DeploymentBinding"] = field(default_factory=dict)

    @property
    def base_name(self) -> str:
        return self.name.removeprefix("*.")

    def binding_for(self, server_file: str) -> "DeploymentBinding":
        return self.bindings.get(server_file, DeploymentBinding())


@dataclass
class DeploymentBinding:
    certificate_path: str = ""
    private_key_path: str = ""
    reload_nginx: bool = True
    reload_command: str = "systemctl reload nginx"


class ConfigManager:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.data = self.root / "data"
        self.servers_dir = self.data / "servers"
        self.domains_dir = self.data / "domains"
        self.certificates_dir = self.data / "certificates"
        self.runtime_dir = self.data / "runtime"
        self.cloudflare_dir = self.runtime_dir / "cloudflare"

    def ensure_dirs(self) -> None:
        for path in (self.servers_dir, self.domains_dir, self.certificates_dir, self.cloudflare_dir, self.root / "logs"):
            path.mkdir(parents=True, exist_ok=True)

    def list_servers(self) -> list[ServerConfig]:
        self.ensure_dirs()
        return [self.load_server(path) for path in sorted(self.servers_dir.glob("*.ini"))]

    def list_domains(self) -> list[DomainConfig]:
        self.ensure_dirs()
        return [self.load_domain(path) for path in sorted(self.domains_dir.glob("*.ini"))]

    def load_server(self, path: Path) -> ServerConfig:
        parser = self._read(path)
        section = parser["server"]
        ssh = parser["ssh"]
        deploy = parser["deploy"]
        certificates = parser["certificates"]
        return ServerConfig(path, section.get("name", path.stem), section["host"], section.getint("port", 22),
                            section["username"], ssh.getboolean("enabled", False), ssh.get("private_key", ""),
                            deploy.get("certificate_path", ""), deploy.get("private_key_path", ""),
                            deploy.getboolean("reload_nginx", True), deploy.get("reload_command", "systemctl reload nginx"),
                            split_csv(certificates.get("domains", "")))

    def load_domain(self, path: Path) -> DomainConfig:
        parser = self._read(path)
        domain = parser["domain"]
        letsencrypt = parser["letsencrypt"]
        cloudflare = parser["cloudflare"]
        certificate = parser["certificate"]
        server = parser["server"]
        environment = letsencrypt.get("environment", "production").lower()
        if environment not in {"production", "staging"}:
            raise ValueError(f"{path.name}：environment 必须是 production 或 staging")
        names = validate_domains(split_csv(domain.get("domains", domain.get("name", ""))))
        return DomainConfig(path, domain.get("name", names[0]), names, domain.getboolean("wildcard", False),
                            environment, letsencrypt["email"], letsencrypt.get("cert_name", names[0]),
                            cloudflare.get("api_token", ""), cloudflare.get("zone", ""),
                            resolve_path(certificate.get("output_dir", f"data/certificates/{names[0]}"), self.root),
                            server.getboolean("deploy", False), server.get("server", ""),
                            split_csv(certificate.get("certbot_extra", "")),
                            {section_name.removeprefix("deploy:"): DeploymentBinding(
                                parser[section_name].get("certificate_path", ""), parser[section_name].get("private_key_path", ""),
                                parser[section_name].getboolean("reload_nginx", True), parser[section_name].get("reload_command", "systemctl reload nginx"))
                             for section_name in parser.sections() if section_name.startswith("deploy:")})

    @staticmethod
    def _read(path: Path) -> configparser.ConfigParser:
        if not path.exists():
            raise ValueError(f"配置文件不存在：{path}")
        parser = configparser.ConfigParser(interpolation=None)
        try:
            with path.open(encoding="utf-8") as handle:
                parser.read_file(handle)
        except (OSError, configparser.Error) as exc:
            raise ValueError(f"配置文件格式错误：{path.name}") from exc
        return parser

    def credentials_path(self, domain: DomainConfig) -> Path:
        path = self.cloudflare_dir / f"{domain.file.stem}.ini"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"dns_cloudflare_api_token = {domain.api_token}\n", encoding="utf-8")
        try:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        return path

    def write_server(self, values: dict) -> Path:
        self.ensure_dirs()
        path = self.servers_dir / f"{values['server']['name']}-config.ini"
        with path.open("w", encoding="utf-8") as handle:
            handle.write("# ZhangCertbot 服务器配置；每个字段均可按需修改。\n\n")
            server = values["server"]
            ssh = values["ssh"]
            deploy = values["deploy"]
            certificates = values.get("certificates", {})
            handle.write(f"[server]\n# 服务器显示名称\nname = {server['name']}\n# SSH 地址\nhost = {server['host']}\n# SSH 端口\nport = {server['port']}\n# SSH 用户名\nusername = {server['username']}\n\n")
            handle.write(f"[ssh]\n# 是否启用自动 SSH 上传\nenabled = {ssh['enabled']}\n# SSH 私钥路径\nprivate_key = {ssh['private_key']}\n\n")
            handle.write(f"[deploy]\n# fullchain.pem 目标路径\ncertificate_path = {deploy['certificate_path']}\n# privkey.pem 目标路径\nprivate_key_path = {deploy['private_key_path']}\n# 是否在 nginx -t 成功后 reload\nreload_nginx = {deploy['reload_nginx']}\n# reload 命令\nreload_command = {deploy['reload_command']}\n\n")
            handle.write(f"[certificates]\n# 关联的域名配置文件\ndomains = {certificates.get('domains', '')}\n")
        return path

    def write_domain(self, values: dict) -> Path:
        self.ensure_dirs()
        path = self.domains_dir / f"{values['name'].replace('*.', 'wildcard-')}.ini"
        with path.open("w", encoding="utf-8") as handle:
            handle.write("# ZhangCertbot 域名配置；Cloudflare Token 仅供本机使用。\n\n")
            sections = (("domain", {"name": "域名显示名称", "wildcard": "是否申请泛域名", "domains": "申请的域名列表"}), ("letsencrypt", {"environment": "Let's Encrypt 环境", "email": "注册邮箱", "cert_name": "Certbot 证书名称"}), ("cloudflare", {"api_token": "Cloudflare API Token", "zone": "Cloudflare Zone"}), ("certificate", {"output_dir": "本地证书导出目录", "certbot_extra": "额外 Certbot 参数"}), ("server", {"deploy": "是否部署到服务器", "server": "服务器配置文件名"}))
            for section, comments in sections:
                handle.write(f"[{section}]\n")
                for key, comment in comments.items():
                    handle.write(f"# {comment}\n{key} = {values.get(section, {}).get(key, '')}\n")
                handle.write("\n")
            for server_file, binding in values.get("deploy_bindings", {}).items():
                handle.write(f"[deploy:{server_file}]\n# 远程 fullchain.pem 路径\ncertificate_path = {binding.get('certificate_path', '')}\n# 远程 privkey.pem 路径\nprivate_key_path = {binding.get('private_key_path', '')}\n# 是否 reload Nginx\nreload_nginx = {binding.get('reload_nginx', 'true')}\n# reload 命令\nreload_command = {binding.get('reload_command', 'systemctl reload nginx')}\n\n")
        try:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        return path


def mask_secret(value: str) -> str:
    return "未配置" if not value else "已配置"