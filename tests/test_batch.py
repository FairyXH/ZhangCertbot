from pathlib import Path
from types import SimpleNamespace

from src.zhangcertbot.batch_manager import BatchProcessor, BatchSettings
from src.zhangcertbot.config_manager import ConfigManager, DeploymentBinding, DomainConfig
from src.zhangcertbot.deploy_manager import DeployManager


def make_domain(tmp_path: Path, name: str, deploy: bool = False) -> DomainConfig:
    return DomainConfig(tmp_path / f"{name}.ini", name, [name], False, "staging", "a@example.com", name,
                        "token", name, tmp_path / "certificates" / name, deploy, "server1-config.ini")


def test_batch_settings_limits_workers():
    assert BatchSettings(False, 20).workers(10) == 1
    assert BatchSettings(True, 3).workers(10) == 3
    assert BatchSettings(True, 20).workers(2) == 2


def test_batch_issue_processes_each_domain_independently(tmp_path: Path):
    manager = ConfigManager(tmp_path)
    domains = [make_domain(tmp_path, "one.example"), make_domain(tmp_path, "two.example")]
    calls = []

    class Runner:
        def issue(self, domain):
            calls.append(domain.name)
            return SimpleNamespace(ok=True, stderr="")

    class Certificates:
        def export(self, domain):
            return True

    class Deployer:
        certificates = Certificates()

        def deploy(self, domain):
            raise AssertionError("本地域名不应部署")

    results = BatchProcessor(manager, Runner(), Deployer()).issue(domains, BatchSettings(True, 2))
    assert {item.domain for item in results} == {"one.example", "two.example"}
    assert sorted(calls) == ["one.example", "two.example"]


def test_batch_callback_receives_each_completed_domain(tmp_path: Path):
    manager = ConfigManager(tmp_path)
    domain = make_domain(tmp_path, "one.example")
    events = []

    class Runner:
        def issue(self, item):
            return SimpleNamespace(ok=True, stderr="")

    class Certificates:
        def export(self, item):
            return True

    class Deployer:
        certificates = Certificates()

    BatchProcessor(manager, Runner(), Deployer()).issue([domain], BatchSettings(), events.append)
    assert len(events) == 1
    assert events[0].domain == "one.example"
    assert events[0].message == "申请成功"


def test_deploy_manager_uses_domain_specific_binding(tmp_path: Path):
    manager = ConfigManager(tmp_path)
    server_path = manager.servers_dir / "server1-config.ini"
    manager.ensure_dirs()
    server_path.write_text("""[server]\nname = server1\nhost = 192.0.2.1\nusername = root\n[ssh]\nenabled = true\nprivate_key = key\n[deploy]\n[certificates]\n""", encoding="utf-8")
    domain = make_domain(tmp_path, "example.com", True)
    domain = DomainConfig(domain.file, domain.name, domain.domains, domain.wildcard, domain.environment, domain.email,
                          domain.cert_name, domain.api_token, domain.zone, domain.output_dir, True, domain.server_file,
                          [], {domain.server_file: DeploymentBinding("/a/fullchain.pem", "/a/privkey.pem", False, "reload")})
    calls = {}

    class SSH:
        def deploy(self, server, fullchain, private_key, binding):
            calls["binding"] = binding

    DeployManager(manager, SimpleNamespace(), SSH()).deploy(domain)
    assert calls["binding"].certificate_path == "/a/fullchain.pem"
    assert calls["binding"].reload_nginx is False
