# ZhangCertbot

ZhangCertbot 是一个中文 Certbot 图形化与命令行管理工具，面向 Windows 上的证书申请、续期、导出和 Linux Nginx 部署。它不重新实现 ACME：Certbot 负责证书生命周期，`certbot-dns-cloudflare` 负责 Cloudflare DNS-01，Paramiko 负责 SSH/SFTP。

> 请仅在你拥有管理权限的域名、服务器和证书环境中使用。生产申请前请先用 Staging 验证配置。

## 特性

- Tkinter GUI 与中文 CLI 共用配置和业务逻辑。
- 支持多个服务器、多个域名、孤立域名和每个域名独立的部署路径。
- 支持普通域名和泛域名；输入 `*.example.com` 会生成 `example.com` 与 `*.example.com` 两个 SAN。
- 支持 Let's Encrypt Production/Staging 环境。
- Cloudflare Token 写入 credentials 文件，不放入 Certbot 命令行参数。
- 支持申请、续期、检查、证书导出、SSH/SFTP 上传和 Nginx reload。
- 上传使用临时文件、远端校验和原子替换；`nginx -t` 失败时不会 reload。
- GUI 支持实时日志、失败重试、批量处理、证书内容查看和复制。
- 支持 SOCKS5 代理和旧 Certbot 根目录导入。

## 工作流程

```text
GUI/CLI -> INI 配置 -> Certbot + Cloudflare DNS-01 -> 本地证书导出
       -> 可选：SFTP 临时上传 -> 校验 -> 原子替换 -> nginx -t -> reload
```

Certbot 的退出码是申请或续期结果的主要依据。续期成功但证书尚未到期时，不会重复上传旧证书。

## 环境要求

- Windows 10/11，或可运行 Python/Tkinter 的 Linux 环境。
- Python 3.10 或更高版本。
- Certbot 与 `certbot-dns-cloudflare`。
- Linux 目标服务器需要 SSH/SFTP 和 Nginx，并授予部署账号目标目录写权限及必要的 reload 权限。

## 安装

Windows PowerShell：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Linux：

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

依赖包括 `certbot`、`certbot-dns-cloudflare`、`paramiko`、`httpx[socks]` 和 `cryptography`。程序会从 PATH 查找 `certbot`，找不到时尝试当前 Python 环境的 Certbot 模块。

## GUI 使用

源码启动：

```powershell
python gui.py
# 或
run.bat gui
```

基本流程：

1. 选择“新建孤立域名”或“新建服务器部署域名”。
2. 填写域名、Cloudflare Token、邮箱和环境；部署模式另需填写 SSH 与远程证书路径。
3. 保存后使用“申请当前”“续期当前”或批量操作。
4. 在实时日志中确认 Certbot、证书导出、SFTP 和 Nginx 的每一步结果。
5. 使用“刷新”查看证书文件；证书列表可以打开内容并复制到剪贴板。

孤立域名只在本地申请、续期和导出，不执行 SSH 上传或 Nginx reload。GUI 还提供代理设置、旧 Certbot 导入、服务器/域名删除确认、并发线程数和最大重试次数设置。

## CLI 使用

```powershell
python main.py --help
python main.py version
python main.py add-server
python main.py add-domain
python main.py list-servers
python main.py list-domains
python main.py issue
python main.py check
python main.py renew
python main.py renew --force
python main.py deploy
```

`renew --force` 会提示确认，因为强制续期可能触发 CA 速率限制。CLI 无参数时进入中文菜单。

## 配置与数据目录

```text
data/
├── servers/                 # 服务器 INI 配置
├── domains/                 # 域名 INI 配置
├── certificates/            # 导出的 fullchain.pem/privkey.pem
├── runtime/
│   ├── cloudflare/          # Certbot credentials 文件
│   ├── proxy.ini            # 可选 SOCKS5 配置
│   └── certbot-imports.json # 旧 Certbot 根目录列表
└── certbot/                 # 项目使用的 Certbot 工作目录
logs/                        # 运行日志
```

域名的 `[deploy:<server-config>]` 段保存该域名在指定服务器上的远程路径和 reload 策略，因此同一服务器上的不同域名可以使用不同目录。应用会在启动或刷新时创建所需目录。

## Cloudflare 与代理

创建仅限目标 Zone 的 API Token，至少授予 `Zone:Read` 与 `DNS:Edit`。Token 只应通过 GUI/CLI 配置输入，不要提交真实 INI、runtime 文件、私钥或 PEM。

GUI 的“代理”窗口可启用 SOCKS5，设置保存在 `data/runtime/proxy.ini`，只影响 Certbot 子进程，不修改系统全局代理。若出现缺少 `socksio`：

```powershell
python -m pip install "httpx[socks]"
```

## 证书申请、续期与部署

```powershell
python main.py issue
python main.py renew
python main.py deploy
```

部署流程为：读取 Certbot 结果、导出到本地目录、上传远端临时文件、校验文件、原子替换、执行 `nginx -t`，最后按配置 reload。SSH 或 Nginx 检查失败不会删除本地证书；孤立域名不会进入部署流程。

Windows 任务计划程序可以每天在项目目录执行 `run.bat renew`，并将“起始于”设置为项目根目录。

## 导入旧 Certbot 数据

GUI 的“导入证书”可以维护多个旧 Certbot 根目录。同步时会扫描 `renewal/` 与 `archive/`，复制账户和证书数据到当前项目，导出证书并创建尚未存在的域名配置。导入域名默认是孤立域名，不会自动连接或修改远程服务器。

## 构建单文件 EXE

执行项目根目录下的 `build_gui.bat`：

```powershell
.\build_gui.bat
```

脚本会检查或安装 PyInstaller，并生成 `dist\ZhangCertbot.exe`。构建选项为 `--onefile --windowed`，目标机器无需安装 Python 即可启动 GUI，但 Certbot 仍需作为外部程序可用。

运行目录应为：

```text
ZhangCertbot.exe
 data\
```

冻结运行时会将数据根目录定位为 EXE 所在目录；源码运行时使用仓库根目录。脚本不会把 Token、私钥、证书、`data/runtime` 或日志打入 EXE。

## 测试与验证

测试使用 mock，不向 Production CA 申请真实证书：

```powershell
python -m pytest -q
python -m compileall main.py gui.py src tests
python main.py --help
python main.py version
.\build_gui.bat
```

打包后可在具有桌面会话的 Windows 机器双击 `dist\ZhangCertbot.exe` 做 GUI 冒烟测试。没有 Certbot、Token、SSH 目标时，只验证窗口启动、配置编辑、日志面板和错误提示。

## 常见问题

- **未找到 Certbot**：确认已安装并执行 `python -m certbot --version`，或确认 `certbot` 在 PATH。
- **DNS Challenge 失败**：检查 Token 权限、Zone、DNS 委托和传播状态；先使用 Staging。
- **缺少 `socksio`**：执行 `python -m pip install "httpx[socks]"`，确保与运行 GUI 的 Python 相同。
- **SSH 连接失败**：检查主机、端口、用户名、私钥路径和目标机防火墙。
- **上传失败**：检查目标目录写权限；程序会保留本地导出文件。
- **`nginx -t` 失败**：修正远程配置或证书路径后再部署，程序不会执行 reload。
- **找不到证书**：确认 `cert-name`、Certbot 根目录和域名配置一致；先执行 `check` 或刷新 GUI。
- **EXE 数据位置不对**：将 `data` 放到 `ZhangCertbot.exe` 同级目录，不要依赖临时解包目录。

## 项目结构

```text
main.py                         # CLI 入口
gui.py                          # GUI 入口
build_gui.bat                   # 单文件 EXE 构建脚本
src/zhangcertbot/
├── gui.py                      # Tkinter 界面
├── cli.py                      # CLI 与交互向导
├── config_manager.py           # INI 模型与持久化
├── certbot_runner.py           # Certbot 子进程
├── certificate_manager.py      # 证书导出与 archive 恢复
├── deploy_manager.py           # 部署编排
├── ssh_manager.py              # SSH/SFTP
├── batch_manager.py            # 批量任务与重试
├── proxy_manager.py            # SOCKS5 配置
└── certbot_import_manager.py  # 旧目录导入
tests/                          # 单元测试
```

## 许可证

仓库当前未声明独立许可证。发布或再分发前，请补充许可证文件，并确认 Certbot、插件及其他依赖的许可证义务。
