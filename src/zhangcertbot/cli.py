from __future__ import annotations

import argparse
import getpass
import logging
from pathlib import Path

from . import __version__
from .certbot_runner import CertbotRunner
from .certificate_manager import CertificateManager
from .config_manager import ConfigManager, mask_secret, validate_domains
from .deploy_manager import DeployManager

ROOT = Path(__file__).resolve().parents[2]
LOG = logging.getLogger("zhangcertbot")


def setup_logging(debug: bool) -> None:
    logging.basicConfig(level=logging.DEBUG if debug else logging.INFO, format="[%(levelname)s] %(message)s")


def setup_server(manager: ConfigManager) -> int:
    name = input("请输入服务器名称：").strip()
    values = {
        "server": {"name": name, "host": input("请输入 SSH 地址：").strip(), "port": input("请输入 SSH 端口（默认 22）：").strip() or "22", "username": input("请输入 SSH 用户名：").strip()},
        "ssh": {"enabled": "false", "private_key": ""},
        "deploy": {"certificate_path": "", "private_key_path": "", "reload_nginx": "false", "reload_command": "systemctl reload nginx"},
        "certificates": {"domains": ""},
    }
    enabled = input("是否启用自动 SSH 上传？1. 是  2. 否：").strip() == "1"
    values["ssh"]["enabled"] = str(enabled).lower()
    if enabled:
        values["ssh"]["private_key"] = input("请输入 SSH 私钥文件路径：").strip()
        values["deploy"]["certificate_path"] = input("请输入服务器上的 fullchain.pem 路径：").strip()
        values["deploy"]["private_key_path"] = input("请输入服务器上的 privkey.pem 路径：").strip()
        values["deploy"]["reload_nginx"] = str(input("上传后是否自动 reload Nginx？1. 是  2. 否：").strip() == "1").lower()
    print(f"服务器名称：{name}\nSSH 地址：{values['server']['host']}\nSSH 用户：{values['server']['username']}\n自动上传：{'是' if enabled else '否'}")
    if input("是否保存？1. 保存  2. 返回：").strip() == "1":
        print(f"已保存：{manager.write_server(values)}")
    return 0


def setup_domain(manager: ConfigManager) -> int:
    name = input("请输入域名：").strip().lower()
    wildcard = input("是否申请泛域名证书？1. 是  2. 否：").strip() == "1"
    domains = validate_domains([name, f"*.{name}"] if wildcard else [name])
    environment = "staging" if input("Let's Encrypt 环境：1. Production  2. Staging：").strip() == "2" else "production"
    email = input("请输入邮箱：").strip()
    token = getpass.getpass("请输入 Cloudflare API Token（不会回显）：").strip()
    servers = manager.list_servers()
    selected = ""
    if input("是否绑定服务器？1. 是  2. 否：").strip() == "1" and servers:
        for index, server in enumerate(servers, 1):
            print(f"{index}. {server.name}")
        choice = int(input("请选择："))
        if 0 < choice <= len(servers):
            selected = servers[choice - 1].file.name
    values = {
        "domain": {"name": name, "wildcard": str(wildcard).lower(), "domains": ", ".join(domains)},
        "letsencrypt": {"environment": environment, "email": email, "cert_name": name},
        "cloudflare": {"api_token": token, "zone": name},
        "certificate": {"output_dir": f"data/certificates/{name}", "certbot_extra": ""},
        "server": {"deploy": str(bool(selected)).lower(), "server": selected},
    }
    print(f"域名：{name}\n环境：{environment}\nCloudflare Token：{mask_secret(token)}\n部署服务器：{selected or '无'}")
    if input("是否保存？1. 保存  2. 返回：").strip() == "1":
        print(f"已保存：{manager.write_domain(values)}")
    return 0


def list_configs(manager: ConfigManager, domains: bool) -> int:
    items = manager.list_domains() if domains else manager.list_servers()
    for item in items:
        print(f"- {item.name}：{item.file.name}")
    if not items:
        print("暂无配置")
    return 0


def renew(manager: ConfigManager, force: bool = False) -> int:
    runner = CertbotRunner(manager.root)
    result = runner.renew(force=force)
    print(result.stdout.strip() or result.stderr.strip())
    if not result.ok:
        return result.code or 1
    certificates = CertificateManager(runner)
    deployer = DeployManager(manager, certificates)
    failures = 0
    for domain in manager.list_domains():
        try:
            changed = certificates.export(domain)
            if changed:
                print(f"已导出更新证书：{domain.name}")
                if domain.deploy:
                    print(f"部署结果：{domain.name} → {deployer.deploy(domain)}")
            else:
                print(f"未更新：{domain.name}，不执行部署")
        except Exception as exc:
            failures += 1
            print(f"处理失败：{domain.name}：{exc}")
    return 1 if failures else 0


def run_menu() -> int:
    print("================================\n       ZhangCertbot\n================================")
    print("1. 添加服务器\n2. 添加域名\n3. 查看服务器\n4. 查看域名\n5. 申请证书\n6. 检查证书\n7. 续期证书\n8. 部署证书\n9. 批量处理\n0. 退出")
    choice = input("请输入数字：").strip()
    mapping = {"1": "add-server", "2": "add-domain", "3": "list-servers", "4": "list-domains", "5": "issue", "6": "check", "7": "renew", "8": "deploy", "9": "renew"}
    return 0 if choice == "0" else main([mapping[choice]]) if choice in mapping else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="基于 Certbot 的多服务器、多域名中文证书管理工具")
    parser.add_argument("--debug", action="store_true", help="显示调试信息")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("add-server", help="添加服务器")
    sub.add_parser("add-domain", help="添加域名")
    sub.add_parser("list-servers", help="查看服务器")
    sub.add_parser("list-domains", help="查看域名")
    sub.add_parser("issue", help="申请证书")
    sub.add_parser("check", help="检查 Certbot 证书")
    sub.add_parser("deploy", help="部署本地导出证书")
    renew_parser = sub.add_parser("renew", help="使用 certbot renew 自动续期")
    renew_parser.add_argument("--force", action="store_true", help="强制续期，可能触发速率限制")
    sub.add_parser("version", help="显示版本")
    args = parser.parse_args(argv)
    setup_logging(args.debug)
    try:
        manager = ConfigManager(ROOT)
        manager.ensure_dirs()
        if args.command == "version":
            print(f"ZhangCertbot {__version__}")
            return 0
        if args.command is None:
            return run_menu()
        if args.command == "add-server":
            return setup_server(manager)
        if args.command == "add-domain":
            return setup_domain(manager)
        if args.command == "list-servers":
            return list_configs(manager, False)
        if args.command == "list-domains":
            return list_configs(manager, True)
        if args.command == "renew":
            if args.force and input("强制续期可能触发速率限制，确认？1. 是  2. 否：").strip() != "1":
                return 0
            return renew(manager, args.force)
        runner = CertbotRunner(ROOT)
        if args.command == "issue":
            failures = 0
            for domain in manager.list_domains():
                result = runner.issue(domain)
                print(f"申请{'成功' if result.ok else '失败'}：{domain.name}")
                if not result.ok:
                    failures += 1
                    print(result.stderr.strip())
                else:
                    certificates = CertificateManager(runner)
                    deployer = DeployManager(manager, certificates)
                    changed = certificates.export(domain)
                    if changed and domain.deploy:
                        print(f"部署结果：{domain.name} → {deployer.deploy(domain)}")
            return 1 if failures else 0
        if args.command == "check":
            result = runner.certificates()
            print(result.stdout.strip() or result.stderr.strip())
            return result.code
        if args.command == "deploy":
            certificates = CertificateManager(runner)
            deployer = DeployManager(manager, certificates)
            for domain in manager.list_domains():
                if domain.deploy:
                    print(f"部署结果：{domain.name} → {deployer.deploy(domain)}")
            return 0
        parser.error("未知命令")
    except Exception as exc:
        print(f"错误：{exc}")
        if args.debug:
            LOG.exception("调试信息")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
