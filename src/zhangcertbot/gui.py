from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .batch_manager import BatchProcessor, BatchSettings
from .config_manager import ConfigManager, mask_secret, validate_domains


class ZhangCertbotGUI:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.manager = ConfigManager(self.root)
        self.manager.ensure_dirs()
        self.window = tk.Tk()
        self.window.title("ZhangCertbot - 证书管理")
        self.window.geometry("1250x780")
        self.window.minsize(1050, 650)
        self.selected_server_file = ""
        self.selected_domain_file = ""
        self.mode = tk.StringVar(value="orphan")
        self.parallel = tk.BooleanVar(value=False)
        self.workers = tk.IntVar(value=4)
        self._build()
        self.show_servers()

    def _build(self):
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(1, weight=1)
        toolbar = ttk.Frame(self.window, padding=10)
        toolbar.grid(row=0, column=0, sticky="ew")
        ttk.Button(toolbar, text="孤立域名", command=self.show_orphans).pack(side="left", padx=3)
        ttk.Button(toolbar, text="新建孤立域名", command=self.new_orphan).pack(side="left", padx=3)
        ttk.Button(toolbar, text="新建服务器部署域名", command=self.new_deploy_domain).pack(side="left", padx=3)
        ttk.Button(toolbar, text="刷新", command=self.show_servers).pack(side="left", padx=3)
        ttk.Label(toolbar, text="批量并发").pack(side="left", padx=(24, 3))
        ttk.Checkbutton(toolbar, text="启用", variable=self.parallel).pack(side="left")
        ttk.Label(toolbar, text="最大线程数").pack(side="left", padx=(8, 3))
        ttk.Spinbox(toolbar, from_=1, to=32, width=5, textvariable=self.workers).pack(side="left")
        ttk.Button(toolbar, text="续期全部", command=self.renew_all).pack(side="right", padx=3)

        pane = ttk.PanedWindow(self.window, orient="horizontal")
        pane.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        left = ttk.Frame(pane, padding=6)
        right = ttk.Frame(pane, padding=10)
        pane.add(left, weight=1)
        pane.add(right, weight=4)
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)
        ttk.Label(left, text="服务器列表").grid(row=0, column=0, sticky="w")
        self.server_list = tk.Listbox(left, exportselection=False)
        self.server_list.grid(row=1, column=0, sticky="nsew", pady=(5, 8))
        self.server_list.bind("<<ListboxSelect>>", self.on_server_select)
        ttk.Button(left, text="批量续期选中服务器", command=self.renew_server).grid(row=2, column=0, sticky="ew", pady=2)
        ttk.Button(left, text="批量上传选中服务器", command=self.deploy_server).grid(row=3, column=0, sticky="ew", pady=2)

        right.rowconfigure(1, weight=1)
        right.rowconfigure(4, weight=1)
        right.columnconfigure(0, weight=1)
        self.domain_title = ttk.Label(right, text="请选择服务器", font=("Microsoft YaHei UI", 15, "bold"))
        self.domain_title.grid(row=0, column=0, sticky="w")
        list_frame = ttk.Frame(right)
        list_frame.grid(row=1, column=0, sticky="nsew", pady=(8, 10))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        self.domain_list = tk.Listbox(list_frame, height=8, exportselection=False)
        self.domain_list.grid(row=0, column=0, sticky="nsew")
        self.domain_list.bind("<<ListboxSelect>>", self.on_domain_select)
        domain_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.domain_list.yview)
        domain_scroll.grid(row=0, column=1, sticky="ns")
        self.domain_list.configure(yscrollcommand=domain_scroll.set)
        buttons = ttk.Frame(right)
        buttons.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        for text, command in (("新建孤立域名", self.new_orphan), ("新建服务器部署域名", self.new_deploy_domain), ("申请当前", self.issue_current), ("续期当前", self.renew_current), ("上传当前", self.deploy_current), ("保存域名", self.save_domain)):
            ttk.Button(buttons, text=text, command=command).pack(side="left", padx=2)
        self._build_form(right)

    def _build_form(self, parent):
        self.form = ttk.LabelFrame(parent, text="域名配置", padding=10)
        self.form.grid(row=3, column=0, sticky="ew")
        self.form.columnconfigure(1, weight=1)
        self.entries: dict[str, ttk.Entry] = {}
        self.field_labels: dict[str, ttk.Label] = {}
        fields = [("域名（前缀 * 表示泛域名）", "name"), ("Cloudflare Token", "token"), ("服务器名称", "server_name"), ("服务器 IP", "host"), ("SSH 端口", "port"), ("SSH 私钥", "private_key"), ("远程 fullchain 路径", "certificate_path"), ("远程 privkey 路径", "private_key_path"), ("重载命令（可选）", "reload_command")]
        for row, (label, key) in enumerate(fields):
            label_widget = ttk.Label(self.form, text=label)
            label_widget.grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
            self.field_labels[key] = label_widget
            entry = ttk.Entry(self.form, show="*" if key == "token" else None)
            entry.grid(row=row, column=1, sticky="ew", pady=3)
            self.entries[key] = entry
            if key == "private_key":
                ttk.Button(self.form, text="选择文件", command=self.choose_key).grid(row=row, column=2, padx=(5, 0))
        self.auto_upload = tk.BooleanVar(value=False)
        self.auto_reload = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.form, text="自动上传", variable=self.auto_upload).grid(row=len(fields), column=1, sticky="w", pady=3)
        ttk.Checkbutton(self.form, text="自动重载", variable=self.auto_reload).grid(row=len(fields) + 1, column=1, sticky="w", pady=3)
        self.form_mode_label = ttk.Label(self.form, text="当前模式：孤立域名")
        self.form_mode_label.grid(row=len(fields) + 2, column=1, sticky="w", pady=3)

    def choose_key(self):
        path = filedialog.askopenfilename(title="选择 SSH 私钥文件")
        if path:
            self.entries["private_key"].delete(0, "end")
            self.entries["private_key"].insert(0, path)

    def _clear_form(self):
        for entry in self.entries.values(): entry.delete(0, "end")
        self.entries["port"].insert(0, "22")
        self.auto_upload.set(False)
        self.auto_reload.set(True)

    def show_servers(self):
        servers = self.manager.list_servers()
        self.server_list.delete(0, "end")
        for server in servers:
            self.server_list.insert("end", server.name)
        self.selected_server_file = ""
        self.domain_title.configure(text="请选择服务器")
        self.domain_list.delete(0, "end")
        self._clear_form()

    def on_server_select(self, _event=None):
        selection = self.server_list.curselection()
        if not selection: return
        servers = self.manager.list_servers()
        server = servers[selection[0]]
        self.selected_server_file = server.file.name
        self.mode.set("deploy")
        self.domain_title.configure(text=f"服务器：{server.name} 的域名列表")
        self.domain_list.delete(0, "end")
        for domain in self.manager.list_domains():
            if domain.deploy and domain.server_file == self.selected_server_file:
                self.domain_list.insert("end", domain.name)
        self.new_deploy_domain(server)

    def show_orphans(self):
        self.selected_server_file = ""
        self.mode.set("orphan")
        self.domain_title.configure(text="孤立域名列表")
        self.domain_list.delete(0, "end")
        for domain in self.manager.list_domains():
            if not domain.deploy:
                self.domain_list.insert("end", domain.name)
        self.new_orphan()

    def on_domain_select(self, _event=None):
        selection = self.domain_list.curselection()
        if not selection: return
        name = self.domain_list.get(selection[0])
        domain = next((x for x in self.manager.list_domains() if x.name == name), None)
        if domain:
            self.selected_domain_file = domain.file.name
            self.load_domain(domain)

    def _set_deploy_fields_visible(self, visible: bool):
        state = "normal" if visible else "disabled"
        for key in ("server_name", "host", "port", "private_key", "certificate_path", "private_key_path", "reload_command"):
            self.entries[key].configure(state=state)
            self.field_labels[key].configure(state=state)

    def new_orphan(self):
        self.mode.set("orphan")
        self.form_mode_label.configure(text="当前模式：孤立域名")
        self._clear_form()
        self._set_deploy_fields_visible(False)
        self.auto_upload.set(False)
        self.auto_reload.set(False)

    def new_deploy_domain(self, server=None):
        self.mode.set("deploy")
        self.form_mode_label.configure(text="当前模式：服务器部署域名")
        self._clear_form()
        self._set_deploy_fields_visible(True)
        if server:
            self.entries["server_name"].insert(0, server.name)
            self.entries["host"].insert(0, server.host)
            self.entries["port"].insert(0, str(server.port))
            self.entries["private_key"].insert(0, server.private_key)
            self.entries["certificate_path"].insert(0, server.certificate_path)
            self.entries["private_key_path"].insert(0, server.private_key_path)
            self.entries["reload_command"].insert(0, server.reload_command)
            self.auto_upload.set(True); self.auto_reload.set(server.reload_nginx)

    def load_domain(self, domain):
        self.mode.set("deploy" if domain.deploy else "orphan")
        self.form_mode_label.configure(text="当前模式：服务器部署域名" if domain.deploy else "当前模式：孤立域名")
        self._clear_form()
        self.entries["name"].insert(0, domain.name)
        self.entries["token"].insert(0, domain.api_token)
        self.auto_upload.set(domain.deploy)
        if domain.deploy:
            server = next((x for x in self.manager.list_servers() if x.file.name == domain.server_file), None)
            self.new_deploy_domain(server)
            self.entries["name"].insert(0, domain.name)
            self.entries["token"].insert(0, domain.api_token)
            binding = domain.binding_for(domain.server_file)
            self.entries["certificate_path"].delete(0, "end"); self.entries["certificate_path"].insert(0, binding.certificate_path)
            self.entries["private_key_path"].delete(0, "end"); self.entries["private_key_path"].insert(0, binding.private_key_path)
            self.entries["reload_command"].delete(0, "end"); self.entries["reload_command"].insert(0, binding.reload_command)
            self.auto_upload.set(True); self.auto_reload.set(binding.reload_nginx)
        else:
            self.new_orphan(); self.entries["name"].insert(0, domain.name); self.entries["token"].configure(state="normal"); self.entries["token"].insert(0, domain.api_token)

    def save_domain(self):
        try:
            raw_name = self.entries["name"].get().strip().lower()
            names = validate_domains([raw_name])
            name = names[0]
            token = self.entries["token"].get().strip()
            if not token: raise ValueError("Cloudflare Token 不能为空")
            if self.mode.get() == "orphan":
                values = {"name": name, "domain": {"name": name, "wildcard": str(raw_name.startswith("*.")).lower(), "domains": ", ".join(names)}, "letsencrypt": {"environment": "production", "email": "", "cert_name": name}, "cloudflare": {"api_token": token, "zone": name.removeprefix("*.")}, "certificate": {"output_dir": f"data/certificates/{name.removeprefix('*.')}", "certbot_extra": ""}, "server": {"deploy": "false", "server": ""}}
            else:
                server_name = self.entries["server_name"].get().strip()
                if not server_name: raise ValueError("服务器名称不能为空")
                server_values = {"server": {"name": server_name, "host": self.entries["host"].get().strip(), "port": self.entries["port"].get().strip() or "22", "username": "root"}, "ssh": {"enabled": "true", "private_key": self.entries["private_key"].get().strip()}, "deploy": {"certificate_path": self.entries["certificate_path"].get().strip(), "private_key_path": self.entries["private_key_path"].get().strip(), "reload_nginx": str(self.auto_reload.get()).lower(), "reload_command": self.entries["reload_command"].get().strip() or "systemctl reload nginx"}, "certificates": {"domains": ""}}
                server_path = self.manager.write_server(server_values)
                values = {"name": name, "domain": {"name": name, "wildcard": str(raw_name.startswith("*.")).lower(), "domains": ", ".join(names)}, "letsencrypt": {"environment": "production", "email": "", "cert_name": name}, "cloudflare": {"api_token": token, "zone": name.removeprefix("*.")}, "certificate": {"output_dir": f"data/certificates/{name.removeprefix('*.')}", "certbot_extra": ""}, "server": {"deploy": str(self.auto_upload.get()).lower(), "server": server_path.name}, "deploy_bindings": {server_path.name: {"certificate_path": self.entries["certificate_path"].get().strip(), "private_key_path": self.entries["private_key_path"].get().strip(), "reload_nginx": str(self.auto_reload.get()).lower(), "reload_command": self.entries["reload_command"].get().strip() or "systemctl reload nginx"}}}
            path = self.manager.write_domain(values)
            self.log(f"已保存：{path.name}，Token：{mask_secret(token)}")
            self.show_servers() if self.mode.get() == "deploy" else self.show_orphans()
        except Exception as exc: messagebox.showerror("保存失败", str(exc))

    def _settings(self): return BatchSettings(self.parallel.get(), max(1, int(self.workers.get())))
    def _processor(self): return BatchProcessor(self.manager)
    def _async(self, function, label):
        def work():
            try:
                results = function()
                self.window.after(0, lambda: [self.log(f"{label}：{x.domain} - {x.message}{'，已部署' if x.deployed else ''}") for x in results])
            except Exception as exc: self.window.after(0, lambda: self.log(f"{label}失败：{exc}"))
        threading.Thread(target=work, daemon=True).start()

    def current_domain(self):
        if not self.selected_domain_file: return None
        return next((x for x in self.manager.list_domains() if x.file.name == self.selected_domain_file), None)

    def issue_current(self):
        domain = self.current_domain()
        if domain: self._async(lambda: self._processor().issue([domain], self._settings()), "申请")

    def renew_current(self):
        domain = self.current_domain()
        if domain: self._async(lambda: self._processor().renew([domain], self._settings()), "续期")

    def deploy_current(self):
        domain = self.current_domain()
        if domain: self._async(lambda: self._processor().deploy([domain], self._settings()), "上传")

    def server_domains(self):
        return [x for x in self.manager.list_domains() if x.deploy and x.server_file == self.selected_server_file]

    def renew_server(self): self._async(lambda: self._processor().renew(self.server_domains(), self._settings()), "服务器批量续期")
    def deploy_server(self): self._async(lambda: self._processor().deploy(self.server_domains(), self._settings()), "服务器批量上传")
    def renew_all(self): self._async(lambda: self._processor().renew(self.manager.list_domains(), self._settings()), "全部批量续期")

    def log(self, text):
        if not hasattr(self, "output"):
            self.output = tk.Text(self.window, height=5, state="disabled")
        self.output.configure(state="normal"); self.output.insert("end", text + "\n"); self.output.see("end"); self.output.configure(state="disabled")

    def run(self): self.window.mainloop()


def main():
    ZhangCertbotGUI(Path(__file__).resolve().parents[2]).run()


if __name__ == "__main__": main()
