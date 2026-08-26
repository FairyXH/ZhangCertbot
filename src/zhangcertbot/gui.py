from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from pathlib import Path

from .batch_manager import BatchItemResult, BatchProcessor, BatchSettings
from .certbot_runner import CertbotRunner
from .config_manager import ConfigManager, DeploymentBinding, DomainConfig, ServerConfig, mask_secret, validate_domains
from .deploy_manager import DeployManager


class ZhangCertbotGUI:
    """Tkinter GUI with a server -> domain tree and per-domain deployment settings."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.manager = ConfigManager(self.root)
        self.manager.ensure_dirs()
        self.window = tk.Tk()
        self.window.title("ZhangCertbot - Certbot 证书管理")
        self.window.geometry("1180x760")
        self.window.minsize(980, 620)
        self.selected_domain: DomainConfig | None = None
        self.selected_server: ServerConfig | None = None
        self._build()
        self.refresh()

    def _build(self):
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(self.window, padding=10)
        toolbar.grid(row=0, column=0, sticky="ew")
        ttk.Button(toolbar, text="添加服务器", command=self.add_server).pack(side="left", padx=3)
        ttk.Button(toolbar, text="添加域名", command=self.add_domain).pack(side="left", padx=3)
        ttk.Button(toolbar, text="刷新列表", command=self.refresh).pack(side="left", padx=3)
        ttk.Label(toolbar, text="批量并发：").pack(side="left", padx=(22, 3))
        self.parallel = tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar, text="启用", variable=self.parallel).pack(side="left")
        ttk.Label(toolbar, text="最大线程数").pack(side="left", padx=(8, 3))
        self.workers = tk.IntVar(value=4)
        ttk.Spinbox(toolbar, from_=1, to=32, width=5, textvariable=self.workers).pack(side="left")
        ttk.Button(toolbar, text="批量续期全部", command=self.batch_renew_all).pack(side="right", padx=3)

        pane = ttk.PanedWindow(self.window, orient="horizontal")
        pane.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        left = ttk.Frame(pane, padding=6)
        right = ttk.Frame(pane, padding=12)
        pane.add(left, weight=1)
        pane.add(right, weight=3)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        right.columnconfigure(1, weight=1)
        right.rowconfigure(13, weight=1)
        self.detail_title = ttk.Label(right, text="请选择服务器或域名", font=("Microsoft YaHei UI", 16, "bold"))
        self.detail_title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        self.fields: dict[str, tk.Entry] = {}
        self._field(right, 1, "域名", "name")
        self._field(right, 2, "申请域名列表", "domains")
        self._field(right, 3, "邮箱", "email")
        self._field(right, 4, "Cloudflare API Token", "api_token")
        self._field(right, 5, "Let's Encrypt 环境", "environment")
        self._field(right, 6, "Certbot cert-name", "cert_name")
        self._field(right, 7, "Cloudflare Zone", "zone")
        self._field(right, 8, "本地导出目录", "output_dir")
        self._field(right, 9, "绑定服务器配置", "server_file")
        self._field(right, 10, "远程 fullchain.pem", "certificate_path")
        self._field(right, 11, "远程 privkey.pem", "private_key_path")
        self._field(right, 12, "Nginx reload 命令", "reload_command")
        self.wildcard = tk.BooleanVar(value=False)
        self.deploy = tk.BooleanVar(value=False)
        self.reload_nginx = tk.BooleanVar(value=True)
        ttk.Checkbutton(right, text="泛域名", variable=self.wildcard).grid(row=13, column=1, sticky="w", pady=3)
        ttk.Checkbutton(right, text="部署到服务器", variable=self.deploy).grid(row=14, column=1, sticky="w", pady=3)
        ttk.Checkbutton(right, text="nginx -t 成功后 reload", variable=self.reload_nginx).grid(row=15, column=1, sticky="nw", pady=3)
        buttons = ttk.Frame(right)
        buttons.grid(row=16, column=0, columnspan=2, sticky="ew", pady=(14, 6))
        for text, command in (("保存当前域名", self.save_domain), ("申请当前", self.issue_selected), ("续期当前", self.renew_selected), ("上传当前", self.deploy_selected), ("批量申请当前服务器", self.batch_issue_server), ("批量续期当前服务器", self.batch_renew_server), ("批量上传当前服务器", self.batch_deploy_server), ("批量申请孤立域名", self.batch_issue_orphans), ("批量续期孤立域名", self.batch_renew_orphans), ("批量上传孤立域名", self.batch_deploy_orphans)):
            ttk.Button(buttons, text=text, command=command).pack(side="left", padx=2)
        self.output = tk.Text(right, height=9, state="disabled", wrap="word")
        self.output.grid(row=17, column=0, columnspan=2, sticky="nsew", pady=(8, 0))

    def _field(self, parent, row, label, key):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
        entry = ttk.Entry(parent, show="*" if key == "api_token" else None)
        entry.grid(row=row, column=1, sticky="ew", pady=3)
        self.fields[key] = entry

    def _set_field(self, key, value):
        entry = self.fields[key]
        entry.delete(0, "end")
        entry.insert(0, value or "")

    def _clear_details(self):
        for key in self.fields: self._set_field(key, "")
        self.wildcard.set(False); self.deploy.set(False); self.reload_nginx.set(True)

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self._clear_details()
        self.selected_domain = None
        self.selected_server = None
        domains = self.manager.list_domains()
        servers = self.manager.list_servers()
        assigned: set[str] = set()
        for server in servers:
            sid = self.tree.insert("", "end", text=f"服务器：{server.name}", values=("server", server.file.name))
            for domain in domains:
                if domain.server_file == server.file.name and domain.deploy:
                    assigned.add(domain.file.name)
                    self.tree.insert(sid, "end", text=domain.name, values=("domain", domain.file.name))
        orphan = self.tree.insert("", "end", text="孤立域名（不部署）", values=("orphan", ""))
        for domain in domains:
            if not domain.deploy or domain.file.name not in assigned:
                self.tree.insert(orphan, "end", text=domain.name, values=("domain", domain.file.name))
        self.tree.item(orphan, open=True)

    def on_select(self, _event=None):
        selection = self.tree.selection()
        if not selection: return
        item = self.tree.item(selection[0])
        kind, filename = item.get("values", ["", ""])
        if kind == "server":
            self.selected_server = next((x for x in self.manager.list_servers() if x.file.name == filename), None)
            self.selected_domain = None
            self.detail_title.configure(text=f"服务器：{self.selected_server.name if self.selected_server else filename}")
            return
        if kind == "domain":
            self.selected_domain = next((x for x in self.manager.list_domains() if x.file.name == filename), None)
            self.selected_server = None
            self.load_domain(self.selected_domain)

    def load_domain(self, domain: DomainConfig | None):
        if domain is None: return
        self.detail_title.configure(text=f"域名：{domain.name}")
        self._set_field("name", domain.name)
        self._set_field("domains", ", ".join(domain.domains))
        self._set_field("email", domain.email)
        self._set_field("api_token", domain.api_token)
        self._set_field("environment", domain.environment)
        self._set_field("cert_name", domain.cert_name)
        self._set_field("zone", domain.zone)
        self._set_field("output_dir", str(domain.output_dir))
        self._set_field("server_file", domain.server_file)
        binding = domain.binding_for(domain.server_file)
        self._set_field("certificate_path", binding.certificate_path)
        self._set_field("private_key_path", binding.private_key_path)
        self._set_field("reload_command", binding.reload_command)
        self.wildcard.set(domain.wildcard); self.deploy.set(domain.deploy); self.reload_nginx.set(binding.reload_nginx)

    def save_domain(self):
        try:
            name = self.fields["name"].get().strip().lower()
            names = validate_domains([x.strip() for x in self.fields["domains"].get().split(",") if x.strip()])
            server_file = self.fields["server_file"].get().strip()
            values = {"name": name, "domain": {"name": name, "wildcard": str(self.wildcard.get()).lower(), "domains": ", ".join(names)}, "letsencrypt": {"environment": self.fields["environment"].get().strip().lower() or "production", "email": self.fields["email"].get().strip(), "cert_name": self.fields["cert_name"].get().strip() or name}, "cloudflare": {"api_token": self.fields["api_token"].get().strip(), "zone": self.fields["zone"].get().strip()}, "certificate": {"output_dir": self.fields["output_dir"].get().strip() or f"data/certificates/{name}", "certbot_extra": ""}, "server": {"deploy": str(self.deploy.get()).lower(), "server": server_file}, "deploy_bindings": {server_file: {"certificate_path": self.fields["certificate_path"].get().strip(), "private_key_path": self.fields["private_key_path"].get().strip(), "reload_nginx": str(self.reload_nginx.get()).lower(), "reload_command": self.fields["reload_command"].get().strip() or "systemctl reload nginx"}} if server_file else {}}
            path = self.manager.write_domain(values)
            self.log(f"已保存域名配置：{path.name}")
            self.refresh()
        except Exception as exc: messagebox.showerror("保存失败", str(exc))

    def add_server(self):
        self._server_dialog()

    def _server_dialog(self):
        dialog = tk.Toplevel(self.window); dialog.title("添加服务器"); dialog.transient(self.window); dialog.grab_set()
        entries = {}
        for row, label, default in ((0, "服务器名称", ""), (1, "SSH 地址", ""), (2, "SSH 端口", "22"), (3, "SSH 用户名", "root"), (4, "SSH 私钥路径", ""), (5, "fullchain 默认路径", ""), (6, "privkey 默认路径", "")):
            ttk.Label(dialog, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=5); entry = ttk.Entry(dialog, width=55); entry.grid(row=row, column=1, padx=10, pady=5); entry.insert(0, default); entries[label] = entry
        def save():
            values = {"server": {"name": entries["服务器名称"].get().strip(), "host": entries["SSH 地址"].get().strip(), "port": entries["SSH 端口"].get().strip() or "22", "username": entries["SSH 用户名"].get().strip()}, "ssh": {"enabled": "true", "private_key": entries["SSH 私钥路径"].get().strip()}, "deploy": {"certificate_path": entries["fullchain 默认路径"].get().strip(), "private_key_path": entries["privkey 默认路径"].get().strip(), "reload_nginx": "true", "reload_command": "systemctl reload nginx"}, "certificates": {"domains": ""}}
            try: self.manager.write_server(values); dialog.destroy(); self.refresh(); self.log("服务器已保存")
            except Exception as exc: messagebox.showerror("保存失败", str(exc), parent=dialog)
        ttk.Button(dialog, text="保存", command=save).grid(row=7, column=1, sticky="e", padx=10, pady=10)

    def add_domain(self):
        self._clear_details(); self.selected_domain = None; self.detail_title.configure(text="新建域名")

    def _settings(self): return BatchSettings(self.parallel.get(), max(1, int(self.workers.get())))
    def _processor(self): return BatchProcessor(self.manager)
    def _run_async(self, operation, label):
        import threading
        def work():
            try:
                results = operation()
                self.window.after(0, lambda: [self.log(f"{label}：{x.domain} - {x.message}{'，已部署' if x.deployed else ''}") for x in results])
            except Exception as exc: self.window.after(0, lambda: self.log(f"{label}失败：{exc}"))
        threading.Thread(target=work, daemon=True).start()

    def issue_selected(self):
        if self.selected_domain: self._run_async(lambda: self._processor().issue([self.selected_domain], self._settings()), "申请")

    def renew_selected(self):
        if self.selected_domain:
            self._run_async(lambda: self._processor().renew([self.selected_domain], self._settings()), "续期")

    def deploy_selected(self):
        if self.selected_domain:
            try: self._processor().deployer.deploy(self.selected_domain); self.log(f"上传成功：{self.selected_domain.name}")
            except Exception as exc: messagebox.showerror("上传失败", str(exc))

    def batch_issue_server(self):
        if self.selected_server:
            domains = [x for x in self.manager.list_domains() if x.server_file == self.selected_server.file.name]
            self._run_async(lambda: self._processor().issue(domains, self._settings()), "服务器批量申请")

    def batch_renew_server(self):
        if self.selected_server:
            domains = [x for x in self.manager.list_domains() if x.server_file == self.selected_server.file.name]
            self._run_async(lambda: self._processor().renew(domains, self._settings()), "服务器批量续期")

    def batch_deploy_server(self):
        if self.selected_server:
            domains = [x for x in self.manager.list_domains() if x.server_file == self.selected_server.file.name]
            self._run_async(lambda: self._processor().deploy(domains, self._settings()), "服务器批量上传")

    def batch_issue_orphans(self):
        domains = [x for x in self.manager.list_domains() if not x.deploy]
        self._run_async(lambda: self._processor().issue(domains, self._settings()), "孤立域名批量申请")

    def batch_deploy_orphans(self):
        self.log("孤立域名不执行 SSH 上传")

    def batch_renew_orphans(self):
        domains = [x for x in self.manager.list_domains() if not x.deploy]
        self._run_async(lambda: self._processor().renew(domains, self._settings()), "孤立域名批量续期")

    def batch_renew_all(self):
        self._run_async(lambda: self._processor().renew(self.manager.list_domains(), self._settings()), "全部批量续期")

    def log(self, text):
        self.output.configure(state="normal"); self.output.insert("end", text + "\n"); self.output.see("end"); self.output.configure(state="disabled")

    def run(self): self.window.mainloop()


def main():
    ZhangCertbotGUI(Path(__file__).resolve().parents[2]).run()


if __name__ == "__main__": main()
