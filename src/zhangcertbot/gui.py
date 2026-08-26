from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from pathlib import Path

from .certbot_runner import CertbotRunner
from .cli import ROOT
from .config_manager import ConfigManager, mask_secret, validate_domains


class ZhangCertbotGUI:
    def __init__(self, root: Path = ROOT):
        self.root = root
        self.manager = ConfigManager(root)
        self.manager.ensure_dirs()
        self.window = tk.Tk()
        self.window.title("ZhangCertbot")
        self.window.geometry("760x560")
        self.window.minsize(680, 480)
        self._build()

    def _build(self):
        self.notebook = ttk.Notebook(self.window)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=12)
        self.server_tab = ttk.Frame(self.notebook, padding=12)
        self.domain_tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.server_tab, text="服务器")
        self.notebook.add(self.domain_tab, text="域名")
        self._build_server_tab()
        self._build_domain_tab()
        action = ttk.Frame(self.window, padding=(12, 0, 12, 12))
        action.pack(fill="x")
        ttk.Button(action, text="申请证书", command=self.issue).pack(side="left", padx=4)
        ttk.Button(action, text="检查证书", command=self.check).pack(side="left", padx=4)
        ttk.Button(action, text="续期证书", command=self.renew).pack(side="left", padx=4)
        ttk.Button(action, text="刷新", command=self.refresh).pack(side="left", padx=4)
        ttk.Button(action, text="退出", command=self.window.destroy).pack(side="right", padx=4)
        self.output = tk.Text(self.window, height=8, state="disabled", wrap="word")
        self.output.pack(fill="both", padx=12, pady=(0, 12))

    def _entry(self, parent, row, label, show=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=5)
        entry = ttk.Entry(parent, width=58, show=show)
        entry.grid(row=row, column=1, sticky="ew", pady=5)
        parent.columnconfigure(1, weight=1)
        return entry

    def _build_server_tab(self):
        self.server_name = self._entry(self.server_tab, 0, "服务器名称")
        self.server_host = self._entry(self.server_tab, 1, "SSH 地址")
        self.server_port = self._entry(self.server_tab, 2, "SSH 端口")
        self.server_port.insert(0, "22")
        self.server_user = self._entry(self.server_tab, 3, "SSH 用户名")
        self.server_key = self._entry(self.server_tab, 4, "SSH 私钥路径")
        self.remote_fullchain = self._entry(self.server_tab, 5, "远程 fullchain.pem")
        self.remote_privkey = self._entry(self.server_tab, 6, "远程 privkey.pem")
        self.server_reload = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.server_tab, text="上传后 reload Nginx", variable=self.server_reload).grid(row=7, column=1, sticky="w")
        ttk.Button(self.server_tab, text="保存服务器", command=self.save_server).grid(row=8, column=1, sticky="e", pady=10)

    def _build_domain_tab(self):
        self.domain_name = self._entry(self.domain_tab, 0, "域名")
        self.domain_wildcard = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.domain_tab, text="申请泛域名（自动包含基础域名）", variable=self.domain_wildcard).grid(row=1, column=1, sticky="w", pady=5)
        self.domain_email = self._entry(self.domain_tab, 2, "邮箱")
        self.domain_token = self._entry(self.domain_tab, 3, "Cloudflare API Token", show="*")
        self.domain_environment = ttk.Combobox(self.domain_tab, values=("production", "staging"), state="readonly")
        self.domain_environment.set("production")
        ttk.Label(self.domain_tab, text="Let's Encrypt 环境").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=5)
        self.domain_environment.grid(row=4, column=1, sticky="w", pady=5)
        self.domain_server = self._entry(self.domain_tab, 5, "服务器配置文件（可空）")
        ttk.Button(self.domain_tab, text="保存域名", command=self.save_domain).grid(row=6, column=1, sticky="e", pady=10)

    def save_server(self):
        try:
            values = {"server": {"name": self.server_name.get().strip(), "host": self.server_host.get().strip(), "port": self.server_port.get().strip(), "username": self.server_user.get().strip()}, "ssh": {"enabled": "true", "private_key": self.server_key.get().strip()}, "deploy": {"certificate_path": self.remote_fullchain.get().strip(), "private_key_path": self.remote_privkey.get().strip(), "reload_nginx": str(self.server_reload.get()).lower(), "reload_command": "systemctl reload nginx"}, "certificates": {"domains": ""}}
            path = self.manager.write_server(values)
            self.log(f"服务器配置已保存：{path.name}")
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    def save_domain(self):
        try:
            name = self.domain_name.get().strip().lower()
            names = validate_domains([name, f"*.{name}"] if self.domain_wildcard.get() else [name])
            values = {"name": name, "domain": {"name": name, "wildcard": str(self.domain_wildcard.get()).lower(), "domains": ", ".join(names)}, "letsencrypt": {"environment": self.domain_environment.get(), "email": self.domain_email.get().strip(), "cert_name": name}, "cloudflare": {"api_token": self.domain_token.get().strip(), "zone": name}, "certificate": {"output_dir": f"data/certificates/{name}", "certbot_extra": ""}, "server": {"deploy": str(bool(self.domain_server.get().strip())).lower(), "server": self.domain_server.get().strip()}}
            path = self.manager.write_domain(values)
            self.log(f"域名配置已保存：{path.name}，Token：{mask_secret(self.domain_token.get())}")
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc))

    def issue(self):
        self.log("开始调用 Certbot 申请证书……")
        for domain in self.manager.list_domains():
            result = CertbotRunner(self.root).issue(domain)
            self.log(f"{domain.name}：{'成功' if result.ok else '失败'}")
            if not result.ok: self.log(result.stderr.strip())

    def check(self):
        result = CertbotRunner(self.root).certificates()
        self.log(result.stdout.strip() or result.stderr.strip())

    def renew(self):
        result = CertbotRunner(self.root).renew()
        self.log(result.stdout.strip() or result.stderr.strip())

    def refresh(self):
        self.log(f"服务器：{len(self.manager.list_servers())} 台，域名：{len(self.manager.list_domains())} 个")

    def log(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text + "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def run(self):
        self.window.mainloop()


def main():
    ZhangCertbotGUI().run()


if __name__ == "__main__":
    main()