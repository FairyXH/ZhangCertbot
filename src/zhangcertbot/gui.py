from __future__ import annotations

import os
import socket
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

try:
    import paramiko
except ImportError:
    paramiko = None

from .batch_manager import BatchProcessor, BatchSettings
from .certbot_runner import CertbotRunner
from .certificate_manager import CertificateManager, certificate_files
from .config_manager import ConfigManager, mask_secret, validate_domains
from .proxy_manager import ProxyConfig, ProxyManager
from .ssh_manager import SSHManager


class ZhangCertbotGUI:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.manager = ConfigManager(self.root)
        self.manager.ensure_dirs()
        self.proxy_manager = ProxyManager(self.root)
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
        ttk.Button(toolbar, text="代理", command=self.open_proxy_dialog).pack(side="left", padx=3)
        ttk.Label(toolbar, text="批量并发").pack(side="left", padx=(24, 3))
        ttk.Checkbutton(toolbar, text="启用", variable=self.parallel).pack(side="left")
        ttk.Label(toolbar, text="最大线程数").pack(side="left", padx=(8, 3))
        ttk.Spinbox(toolbar, from_=1, to=32, width=5, textvariable=self.workers).pack(side="left")
        ttk.Label(toolbar, text="最大重试次数").pack(side="left", padx=(12, 3))
        self.retries = tk.IntVar(value=2)
        ttk.Spinbox(toolbar, from_=0, to=10, width=5, textvariable=self.retries).pack(side="left")
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
        ttk.Button(left, text="删除服务器", command=self.delete_server).grid(row=4, column=0, sticky="ew", pady=2)

        right.rowconfigure(1, weight=1)
        right.rowconfigure(3, weight=1)
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
        for text, command in (("新建孤立域名", self.new_orphan), ("新建服务器部署域名", self.new_deploy_domain), ("申请当前", self.issue_current), ("续期当前", self.renew_current), ("上传当前", self.deploy_current), ("打开 SSH", self.open_ssh_current), ("保存域名", self.save_domain), ("删除域名", self.delete_domain)):
            ttk.Button(buttons, text=text, command=command).pack(side="left", padx=2)
        lower = ttk.PanedWindow(right, orient="horizontal")
        lower.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        form_host = ttk.Frame(lower)
        log_host = ttk.Frame(lower)
        lower.add(form_host, weight=3)
        lower.add(log_host, weight=2)
        self._build_form(form_host)
        self._build_log_panel(log_host)
        self._build_certificate_panel(log_host)


    def _build_form(self, parent):
        self.form = ttk.LabelFrame(parent, text="域名配置", padding=10)
        self.form.grid(row=3, column=0, sticky="ew")
        self.form.columnconfigure(1, weight=1)
        self.entries: dict[str, ttk.Entry] = {}
        self.field_labels: dict[str, ttk.Label] = {}
        fields = [("域名（前缀 * 表示泛域名）", "name"), ("Cloudflare Token", "token"), ("邮箱（可选）", "email"), ("服务器名称", "server_name"), ("服务器 IP", "host"), ("SSH 端口", "port"), ("SSH 用户名", "username"), ("SSH 密码（可选）", "password"), ("SSH 私钥", "private_key"), ("远程 fullchain 路径", "certificate_path"), ("远程 privkey 路径", "private_key_path"), ("重载命令（可选）", "reload_command")]
        for row, (label, key) in enumerate(fields):
            label_widget = ttk.Label(self.form, text=label)
            label_widget.grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
            self.field_labels[key] = label_widget
            entry = ttk.Entry(self.form, show="*" if key == "password" else None)
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

    def _build_log_panel(self, parent):
        parent.rowconfigure(0, weight=2)
        parent.rowconfigure(2, weight=1)
        parent.columnconfigure(0, weight=1)
        self.log_panel = ttk.LabelFrame(parent, text="实时日志", padding=6)
        self.log_panel.grid(row=0, column=0, sticky="nsew")
        self.log_panel.rowconfigure(0, weight=1)
        self.log_panel.columnconfigure(0, weight=1)
        self.output = tk.Text(self.log_panel, height=8, state="disabled", wrap="word")
        self.output.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(self.log_panel, orient="vertical", command=self.output.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.output.configure(yscrollcommand=scroll.set)
        ttk.Button(self.log_panel, text="清空日志", command=self.clear_log).grid(row=1, column=0, sticky="e", pady=(5, 0))

    def _build_certificate_panel(self, parent):
        self.certificate_panel = ttk.LabelFrame(parent, text="当前域名证书", padding=6)
        self.certificate_panel.grid(row=2, column=0, sticky="nsew", pady=(10, 0))
        self.certificate_list = tk.Listbox(self.certificate_panel, exportselection=False, height=6)
        self.certificate_list.pack(side="left", fill="both", expand=True)
        self.certificate_list.bind("<ButtonRelease-1>", self.open_selected_certificate)
        scrollbar = ttk.Scrollbar(self.certificate_panel, orient="vertical", command=self.certificate_list.yview)
        scrollbar.pack(side="right", fill="y")
        self.certificate_list.configure(yscrollcommand=scrollbar.set)
        self.certificate_paths: list[Path] = []
        self.certificate_list.bind("<Return>", self.open_selected_certificate)
        ttk.Button(self.certificate_panel, text="打开内容", command=self.open_selected_certificate).pack(side="bottom", fill="x", pady=(5, 0))

    def refresh_certificate_list(self, domain):
        if domain:
            CertificateManager(CertbotRunner(self.root)).restore_from_archive(domain)
        self.certificate_list.delete(0, "end")
        self.certificate_paths = certificate_files(domain.output_dir) if domain else []
        for path in self.certificate_paths:
            self.certificate_list.insert("end", path.name)
        if not self.certificate_paths:
            self.certificate_list.insert("end", "暂无已导出证书")

    def open_selected_certificate(self, _event=None):
        selection = self.certificate_list.curselection()
        if not selection or selection[0] >= len(self.certificate_paths):
            return
        path = self.certificate_paths[selection[0]]
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="utf-8", errors="replace")
        dialog = tk.Toplevel(self.window)
        dialog.title(f"证书内容 - {path.name}")
        dialog.geometry("900x650")
        dialog.rowconfigure(0, weight=1)
        dialog.columnconfigure(0, weight=1)
        text = tk.Text(dialog, wrap="none")
        text.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        text.insert("1.0", content)
        text.configure(state="disabled")
        yscroll = ttk.Scrollbar(dialog, orient="vertical", command=text.yview)
        yscroll.grid(row=0, column=1, sticky="ns", pady=8)
        text.configure(yscrollcommand=yscroll.set)
        ttk.Button(dialog, text="复制内容", command=lambda: self.copy_certificate_content(content)).grid(row=1, column=0, sticky="e", padx=8, pady=(0, 8))

    def copy_certificate_content(self, content):
        self.window.clipboard_clear()
        self.window.clipboard_append(content)
        self.window.update()
        self.log("证书内容已复制到剪贴板")
    def clear_log(self):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.configure(state="disabled")

    def open_proxy_dialog(self):
        config = self.proxy_manager.load()
        dialog = tk.Toplevel(self.window)
        dialog.title("SOCKS5 代理设置")
        dialog.geometry("430x220")
        dialog.resizable(False, False)
        dialog.transient(self.window)
        dialog.grab_set()
        enabled = tk.BooleanVar(value=config.enabled)
        host = tk.StringVar(value=config.host)
        port = tk.IntVar(value=config.port)
        ttk.Checkbutton(dialog, text="启用 SOCKS5 代理", variable=enabled).grid(row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(18, 10))
        ttk.Label(dialog, text="代理地址").grid(row=1, column=0, sticky="w", padx=18, pady=6)
        ttk.Entry(dialog, textvariable=host, width=28).grid(row=1, column=1, padx=18, pady=6)
        ttk.Label(dialog, text="代理端口").grid(row=2, column=0, sticky="w", padx=18, pady=6)
        ttk.Spinbox(dialog, from_=1, to=65535, textvariable=port, width=26).grid(row=2, column=1, padx=18, pady=6)
        ttk.Label(dialog, text="格式：socks5h://地址:端口").grid(row=3, column=0, columnspan=2, sticky="w", padx=18, pady=4)
        def save():
            try:
                value = ProxyConfig(enabled.get(), host.get().strip(), int(port.get()))
                if not value.host:
                    raise ValueError("代理地址不能为空")
                if not 1 <= value.port <= 65535:
                    raise ValueError("代理端口必须在 1-65535 范围内")
                self.proxy_manager.save(value)
                self.log(f"SOCKS5 代理已{'启用' if value.enabled else '关闭'}：{value.host}:{value.port}")
                dialog.destroy()
            except Exception as exc:
                messagebox.showerror("代理设置失败", str(exc), parent=dialog)
        buttons = ttk.Frame(dialog)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", padx=18, pady=14)
        ttk.Button(buttons, text="保存", command=save).pack(side="left", padx=4)
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="left", padx=4)

    def choose_key(self):
        path = filedialog.askopenfilename(title="选择 SSH 私钥文件")
        if path:
            self.entries["private_key"].delete(0, "end")
            self.entries["private_key"].insert(0, path)

    def _replace_entry(self, key: str, value: str):
        entry = self.entries[key]
        entry.configure(state="normal")
        entry.delete(0, "end")
        entry.insert(0, value or "")

    def _clear_form(self):
        for entry in self.entries.values():
            entry.configure(state="normal")
            entry.delete(0, "end")
        self.auto_upload.set(False)
        self.auto_reload.set(True)

    def delete_server(self):
        selection = self.server_list.curselection()
        if not selection:
            return
        servers = self.manager.list_servers()
        server = servers[selection[0]]
        if not messagebox.askyesno("确认删除", f"确定删除服务器“{server.name}”及其连接配置吗？\n域名配置和证书文件不会删除。"):
            return
        self.manager.delete_server(server.file)
        self.selected_server_file = ""
        self.selected_domain_file = ""
        self.log(f"已删除服务器配置：{server.name}")
        self.show_servers()

    def delete_domain(self):
        domain = self.current_domain()
        if domain is None:
            return
        if not messagebox.askyesno("确认删除", f"确定删除域名配置“{domain.name}”吗？\n本地证书文件不会删除。"):
            return
        self.manager.delete_domain(domain.file)
        self.selected_domain_file = ""
        self.log(f"已删除域名配置：{domain.name}")
        if self.selected_server_file:
            self.on_server_select()
        else:
            self.show_orphans()
    def show_servers(self):
        servers = self.manager.list_servers()
        self.server_list.delete(0, "end")
        for server in servers:
            self.server_list.insert("end", server.name)
        self.selected_server_file = ""
        self.domain_title.configure(text="请选择服务器")
        self.domain_list.delete(0, "end")
        self._clear_form()
        self.refresh_certificate_list(None)

    def on_server_select(self, _event=None):
        selection = self.server_list.curselection()
        if not selection:
            return
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
        self.refresh_certificate_list(None)

    def on_domain_select(self, _event=None):
        selection = self.domain_list.curselection()
        if not selection: return
        name = self.domain_list.get(selection[0])
        domain = next((x for x in self.manager.list_domains() if x.name == name), None)
        if domain:
            self.selected_domain_file = domain.file.name
            self.load_domain(domain)
            self.refresh_certificate_list(domain)

    def _set_deploy_fields_visible(self, visible: bool):
        state = "normal" if visible else "disabled"
        for key in ("server_name", "host", "port", "username", "password", "private_key", "certificate_path", "private_key_path", "reload_command"):
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
            self._replace_entry("server_name", server.name)
            self._replace_entry("host", server.host)
            self._replace_entry("port", str(server.port))
            self._replace_entry("username", server.username or "root")
            self._replace_entry("password", server.password)
            self._replace_entry("private_key", server.private_key)
            self._replace_entry("certificate_path", server.certificate_path)
            self._replace_entry("private_key_path", server.private_key_path)
            self._replace_entry("reload_command", server.reload_command)
            self.auto_upload.set(True); self.auto_reload.set(server.reload_nginx)
        else:
            self._replace_entry("username", "root")
            self.entries["port"].insert(0, "22")

    def load_domain(self, domain):
        self.mode.set("deploy" if domain.deploy else "orphan")
        self.form_mode_label.configure(text="当前模式：服务器部署域名" if domain.deploy else "当前模式：孤立域名")
        self._clear_form()
        self._replace_entry("name", domain.name)
        self._replace_entry("token", domain.api_token)
        self._replace_entry("email", domain.email)
        self.auto_upload.set(domain.deploy)
        if domain.deploy:
            server = next((x for x in self.manager.list_servers() if x.file.name == domain.server_file), None)
            self.new_deploy_domain(server)
            self._replace_entry("name", domain.name)
            self._replace_entry("token", domain.api_token)
            self._replace_entry("email", domain.email)
            binding = domain.binding_for(domain.server_file)
            self._replace_entry("certificate_path", binding.certificate_path)
            self._replace_entry("private_key_path", binding.private_key_path)
            self._replace_entry("reload_command", binding.reload_command)
            self.auto_upload.set(True); self.auto_reload.set(binding.reload_nginx)
        else:
            self.new_orphan()
            self._replace_entry("name", domain.name)
            self._replace_entry("token", domain.api_token)
            self._replace_entry("email", domain.email)

    def save_domain(self):
        try:
            raw_name = self.entries["name"].get().strip().lower()
            names = validate_domains([raw_name])
            name = raw_name
            base_name = raw_name.removeprefix("*.")
            token = self.entries["token"].get().strip()
            if not token: raise ValueError("Cloudflare Token 不能为空")
            if self.mode.get() == "orphan":
                values = {"name": name, "domain": {"name": name, "wildcard": str(raw_name.startswith("*.")).lower(), "domains": ", ".join(names)}, "letsencrypt": {"environment": "production", "email": self.entries["email"].get().strip(), "cert_name": base_name}, "cloudflare": {"api_token": token, "zone": base_name}, "certificate": {"output_dir": f"data/certificates/{base_name}", "certbot_extra": ""}, "server": {"deploy": "false", "server": ""}}
            else:
                server_name = self.entries["server_name"].get().strip()
                if not server_name: raise ValueError("服务器名称不能为空")
                server_values = {"server": {"name": server_name, "host": self.entries["host"].get().strip(), "port": self.entries["port"].get().strip() or "22", "username": self.entries["username"].get().strip() or "root"}, "ssh": {"enabled": "true", "private_key": self.entries["private_key"].get().strip(), "password": self.entries["password"].get()}, "deploy": {"certificate_path": self.entries["certificate_path"].get().strip(), "private_key_path": self.entries["private_key_path"].get().strip(), "reload_nginx": str(self.auto_reload.get()).lower(), "reload_command": self.entries["reload_command"].get().strip() or "systemctl reload nginx"}, "certificates": {"domains": ""}}
                server_path = self.manager.write_server(server_values)
                values = {"name": name, "domain": {"name": name, "wildcard": str(raw_name.startswith("*.")).lower(), "domains": ", ".join(names)}, "letsencrypt": {"environment": "production", "email": self.entries["email"].get().strip(), "cert_name": base_name}, "cloudflare": {"api_token": token, "zone": base_name}, "certificate": {"output_dir": f"data/certificates/{base_name}", "certbot_extra": ""}, "server": {"deploy": str(self.auto_upload.get()).lower(), "server": server_path.name}, "deploy_bindings": {server_path.name: {"certificate_path": self.entries["certificate_path"].get().strip(), "private_key_path": self.entries["private_key_path"].get().strip(), "reload_nginx": str(self.auto_reload.get()).lower(), "reload_command": self.entries["reload_command"].get().strip() or "systemctl reload nginx"}}}
            path = self.manager.write_domain(values)
            self.log(f"已保存：{path.name}，Token：{mask_secret(token)}")
            self.show_servers() if self.mode.get() == "deploy" else self.show_orphans()
            self.refresh_certificate_list(None)
        except Exception as exc: messagebox.showerror("保存失败", str(exc))

    def _settings(self): return BatchSettings(self.parallel.get(), max(1, int(self.workers.get())), max(0, int(self.retries.get())))
    def _processor(self): return BatchProcessor(self.manager)
    def _async(self, function, label):
        self.log(f"[{label}] 开始执行 Certbot（详细模式 -v，已关闭 SSL 校验）")
        def progress(item):
            self.window.after(0, lambda: self.log(f"[{label}] {item.domain}：{item.message}{'，已部署' if item.deployed else ''}"))
        def work():
            try:
                results = function(progress)
                ok_count = sum(1 for item in results if item.ok)
                fail_count = len(results) - ok_count
                self.window.after(0, lambda: self._finish_async(label, results))
            except Exception as exc:
                self.window.after(0, lambda: self.log(f"[{label}] 失败：{exc}"))
        threading.Thread(target=work, daemon=True).start()

    def _finish_async(self, label, results):
        ok_count = sum(1 for item in results if item.ok)
        fail_count = len(results) - ok_count
        self.log(f"[{label}] 处理结束：成功 {ok_count}，失败 {fail_count}，共 {len(results)} 个域名")
        domain = self.current_domain()
        if domain:
            self.refresh_certificate_list(domain)

    def current_domain(self):
        if not self.selected_domain_file: return None
        return next((x for x in self.manager.list_domains() if x.file.name == self.selected_domain_file), None)

    def open_ssh_current(self):
        domain = self.current_domain()
        if domain is None or not domain.deploy:
            messagebox.showwarning("无法打开 SSH", "请先选择一个服务器部署域名。")
            return
        server = next((item for item in self.manager.list_servers() if item.file.name == domain.server_file), None)
        if server is None:
            messagebox.showerror("打开 SSH 失败", f"服务器配置不存在：{domain.server_file}")
            return
        if paramiko is None:
            messagebox.showerror("打开 SSH 失败", "未安装 Paramiko，请先安装项目依赖。")
            return
        dialog = tk.Toplevel(self.window)
        dialog.title(f"SSH 终端 - {server.name}")
        dialog.geometry("900x600")
        dialog.rowconfigure(0, weight=1)
        dialog.columnconfigure(0, weight=1)
        output = tk.Text(dialog, wrap="word", state="disabled", bg="#111111", fg="#eeeeee", insertbackground="#ffffff")
        output.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=8, pady=8)
        scroll = ttk.Scrollbar(dialog, orient="vertical", command=output.yview)
        scroll.grid(row=0, column=2, sticky="ns", pady=8)
        output.configure(yscrollcommand=scroll.set)
        command = tk.StringVar()
        entry = ttk.Entry(dialog, textvariable=command)
        entry.grid(row=1, column=0, sticky="ew", padx=(8, 4), pady=(0, 8))
        dialog.columnconfigure(0, weight=1)
        session = {}
        def append(text):
            if dialog.winfo_exists():
                output.configure(state="normal")
                output.insert("end", text)
                output.see("end")
                output.configure(state="disabled")
        def send(_event=None):
            value = command.get()
            channel = session.get("channel")
            if value and channel:
                command.set("")
                try: channel.send(value + "\n")
                except Exception as exc: append(f"发送失败：{exc}\n")
        def worker():
            client = None
            try:
                client, channel = SSHManager().open_shell(server)
                session["channel"] = channel
                self.window.after(0, append, f"已连接：{server.username or 'root'}@{server.host}:{server.port}\n")
                while dialog.winfo_exists():
                    try:
                        data = channel.recv(4096)
                        if data: self.window.after(0, append, data.decode(errors="replace"))
                    except (socket.timeout, TimeoutError): continue
                    except Exception as exc: self.window.after(0, append, f"\nSSH 会话结束：{exc}\n"); break
            except Exception as exc: self.window.after(0, append, f"连接失败：{exc}\n")
            finally:
                if client: client.close()
        entry.bind("<Return>", send)
        ttk.Button(dialog, text="发送", command=send).grid(row=1, column=1, padx=4, pady=(0, 8))
        threading.Thread(target=worker, daemon=True).start()
        entry.focus_set()

    def issue_current(self):
        domain = self.current_domain()
        if domain:
            self._async(lambda callback: self._processor().issue([domain], self._settings(), callback), "申请")

    def renew_current(self):
        domain = self.current_domain()
        if domain: self._async(lambda callback: self._processor().renew([domain], self._settings(), callback=callback), "续期")

    def deploy_current(self):
        domain = self.current_domain()
        if domain: self._async(lambda callback: self._processor().deploy([domain], self._settings(), callback), "上传")

    def server_domains(self):
        return [x for x in self.manager.list_domains() if x.deploy and x.server_file == self.selected_server_file]

    def renew_server(self): self._async(lambda callback: self._processor().renew(self.server_domains(), self._settings(), callback=callback), "服务器批量续期")
    def deploy_server(self): self._async(lambda callback: self._processor().deploy(self.server_domains(), self._settings(), callback), "服务器批量上传")
    def renew_all(self): self._async(lambda callback: self._processor().renew(self.manager.list_domains(), self._settings(), callback=callback), "全部批量续期")

    def log(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text + "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def run(self): self.window.mainloop()


def main():
    ZhangCertbotGUI(Path(__file__).resolve().parents[2]).run()


if __name__ == "__main__": main()
