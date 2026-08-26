# ZhangCertbot

ZhangCertbot 是 Certbot 的中文自动化管理层，不重新实现 ACME。它管理多个服务器、多个域名、Cloudflare DNS-01、Certbot 证书生命周期，以及通过 SSH/SFTP 向 Linux Nginx 部署证书。

## 工作原理

- Certbot 负责 ACME Account、Order、Authorization、DNS-01、证书申请和续期。
- `certbot-dns-cloudflare` 负责 Cloudflare DNS-01；ZhangCertbot 只生成 credentials 文件和 Certbot 参数。
- `paramiko` 负责 SSH/SFTP；上传先写临时文件，完整校验后原子替换。
- Windows 机器运行 ZhangCertbot 和 Certbot；Linux 目标机只需运行 Nginx。

## 安装

需要 Python 3.10 或更高版本。Windows PowerShell：

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

依赖至少包括：`certbot`、`certbot-dns-cloudflare`、`paramiko`。程序会从 PATH 查找 `certbot`，找不到时尝试 `python -m certbot`；两者都不可用时会显示中文错误。

## Cloudflare Token

创建 Cloudflare API Token，并限制到目标 Zone。所需权限：

- `Zone:Read`
- `DNS:Edit`

Token 保存于域名配置和 `data/runtime/cloudflare/` credentials 文件中，不会放进 Certbot 命令行参数，也不会打印到控制台。真实配置文件、runtime、日志和密钥文件已加入 `.gitignore`。模板文件以 `.ini.example` 结尾。

## GUI 模式

提供独立 Tkinter 图形界面：

```powershell
python gui.py
```

或使用启动脚本：

```powershell
run.bat gui
```

GUI 提供服务器配置、域名配置、泛域名开关、Production/Staging、Token 隐藏输入，以及申请、检查、续期、刷新等操作。GUI 与 CLI 共用同一套 INI 配置和 Certbot 编排逻辑。首次保存时会自动在 `data/servers/` 或 `data/domains/` 生成配置文件。


直接启动中文菜单：

```powershell
python main.py
```

也可以使用：

```powershell
python main.py --help
python main.py version
python main.py add-server
python main.py add-domain
python main.py list-servers
python main.py list-domains
```

向导生成的配置目录：

```text
data/
├── servers/                 # 每台服务器一个独立 INI
├── domains/                 # 每个域名一个独立 INI
├── certificates/            # ZhangCertbot 导出的最终证书
└── runtime/cloudflare/      # Certbot credentials，不提交 Git
```

## 域名创建模式

GUI 提供两种明确的创建模式。

### 创建孤立域名

点击“新建孤立域名”时只显示两个输入框：

- Cloudflare Token
- 域名

域名如果输入：

```text
*.example.com
```

程序会自动申请：

```text
example.com
*.example.com
```

孤立域名不绑定服务器，不保存 SSH 信息，也不会执行上传或 Nginx reload。

### 创建服务器部署域名

点击“新建服务器部署域名”时显示：

- Cloudflare Token
- 域名
- 服务器名称
- 服务器 IP
- SSH 端口
- SSH 私钥
- SSH 私钥文件选择器
- 远程 fullchain.pem 路径
- 远程 privkey.pem 路径
- 重载命令（可选）
- 自动重载
- 自动上传

域名前缀为 `*.` 时自动生成基础域名和泛域名两个 Certbot SAN。

保存服务器部署域名时，程序会写入服务器配置和域名配置；远程证书路径保存在该域名自己的 `[deploy:<server-config>]` 段中，不会与同服务器的其他域名混用。


GUI 左侧树状列表按以下层级展示：

```text
服务器：Zhang服务器
├── domain-a.example.com
└── domain-b.example.com

孤立域名（不部署）
├── local-a.example.com
└── local-b.example.com
```

点击服务器节点会选中该服务器；点击其下域名会加载该域名的完整配置。每个域名的部署段独立保存：

- 远程 `fullchain.pem` 路径
- 远程 `privkey.pem` 路径
- Nginx reload 开关
- Nginx reload 命令

因此同一台服务器下的多个域名可以使用完全不同的远程证书目录。

不绑定服务器的域名进入“孤立域名（不部署）”列表，只执行本地 Certbot 申请、续期和导出，不执行 SSH 上传或 Nginx reload。

如果实时日志出现：

```text
Using SOCKS proxy, but the 'socksio' package is not installed
```

请在运行 ZhangCertbot 的同一个 Python 环境执行：

```powershell
python -m pip install "httpx[socks]"
```

项目的 `requirements.txt` 已包含 `httpx[socks]`。安装完成后重启 GUI。

如果代理端口未监听，会直接在实时日志中显示明确错误，例如：

```text
SOCKS5 代理无法连接：127.0.0.1:7890：[WinError 10061] 由于目标计算机积极拒绝
```

这通常表示 Clash 的 SOCKS5 端口不是 7890，或者 Clash/代理程序当前未启动。请以实际代理软件配置为准；Clash 常见 HTTP/Mixed 端口为 7890，SOCKS5 端口可能为 7891。


GUI 顶部提供“代理”按钮，点击后打开 SOCKS5 设置窗口：

- 启用/关闭代理
- 代理地址
- 代理端口
- 保存和取消

设置保存到：

```text
data/runtime/proxy.ini
```

启用后，Certbot 子进程会继承：

```text
HTTP_PROXY=socks5h://地址:端口
HTTPS_PROXY=socks5h://地址:端口
ALL_PROXY=socks5h://地址:端口
```

使用 `socks5h` 会让代理负责 DNS 解析，适合 Clash、VPN、Proxifier 等环境。代理设置只影响 ZhangCertbot 启动的 Certbot 子进程，不修改系统全局代理。


日志示例：

```text
[申请] 开始执行
[申请] example.com：申请失败，第 1 次重试：网络超时
[申请] example.com：申请失败，第 2 次重试：网络超时
[申请] example.com：申请失败，重试次数已用尽：网络超时
[申请] 处理结束：成功 0，失败 1，共 1 个域名
```

GUI 的“域名配置”右侧新增“实时日志”栏，与域名表单并排显示。申请、续期、上传和批量操作会实时写入：

- 操作开始
- 每个域名的处理结果
- Certbot 失败摘要
- 证书导出结果
- SSH 上传结果
- Nginx reload 结果
- 批量操作完成数量

日志更新通过 Tk 主线程队列执行，后台线程不会直接操作 Tk 控件。日志不会输出 Cloudflare Token、SSH 私钥内容或其他敏感值。可以点击“清空日志”删除当前界面日志。


GUI 顶部可以控制：

- 是否启用并发
- 最大线程数，范围 1-32

批量操作支持：

- 当前服务器批量申请
- 当前服务器批量续期
- 当前服务器批量上传
- 孤立域名批量申请
- 孤立域名批量续期
- 全部域名批量续期

Certbot 的批量 `renew` 命令本身只调用一次；证书导出和每个域名的 SSH 上传可以并发执行。关闭并发时使用单线程顺序处理。


执行 `python main.py add-server`，填写 SSH 地址、端口、用户名、私钥路径、远程 `fullchain.pem` 和 `privkey.pem` 路径。默认使用 SSH 私钥认证，不保存 SSH 密码。

服务器配置支持：

- 自动上传开关
- SSH Host、Port、Username、私钥路径
- 两个远程证书路径
- `nginx -t` 后是否 reload
- 自定义 reload 命令

## 添加域名

执行 `python main.py add-domain`。泛域名会自动生成：

```text
example.com
*.example.com
```

可以选择 Production 或 Staging、邮箱、Cloudflare Token，以及绑定某一台服务器。不绑定服务器时 `deploy = false`，证书仍会申请、续期并导出到本地，不执行 SSH 或 Nginx 操作。

## 申请证书

配置完成后执行：

```powershell
python main.py issue
```

生成的核心命令等价于：

```text
certbot certonly --dns-cloudflare --dns-cloudflare-credentials <runtime文件>
  --email <邮箱> --agree-tos --non-interactive
  --server <Production或Staging目录>
  --cert-name <名称> -d <域名>
```

不建议反复对 Production 执行首次申请。先使用 Staging 验证域名、Token、DNS 委托和 SSH 配置。

## 自动续期

```powershell
python main.py renew
```

程序实际调用 `certbot renew`，不自行根据剩余天数重新实现续期判断，也不默认使用 `--force-renewal`。Certbot 返回成功后，程序只在导出证书内容发生变化时部署；未更新时不上传旧证书。

强制续期必须明确执行：

```powershell
python main.py renew --force
```

程序会先提示速率限制风险。

Windows 任务计划程序可每天执行 `run.bat renew`，工作目录设置为项目目录。也可以使用：

```text
python main.py renew
```

## SSH 自动部署与 Nginx

部署流程：

1. 读取 Certbot `live/<cert-name>/fullchain.pem` 和 `privkey.pem`。
2. 导出到 `data/certificates/<domain>/`。
3. SFTP 上传到远程临时文件。
4. 校验远程文件大小后原子替换旧文件。
5. 执行 `nginx -t`。
6. 测试成功才执行配置的 reload 命令。

SSH 失败会保留本地新证书；`nginx -t` 失败时明确提示未 reload。

Linux Nginx 示例：

```nginx
ssl_certificate /etc/nginx/ssl/example/fullchain.pem;
ssl_certificate_key /etc/nginx/ssl/example/privkey.pem;
```

## 多服务器、多域名

每个域名通过 `[server]` 的 `deploy` 和 `server` 字段决定部署目标；服务器配置不会硬编码在 Python 源码中。不同域名可以绑定不同服务器，也可以全部设置为本地保存。

## 检查与部署

```powershell
python main.py check
python main.py deploy
```

`check` 显示 Certbot 维护的证书信息。`deploy` 只处理已绑定服务器的域名。

## 安全注意事项

- 不要把真实 `.ini`、Token、私钥、PEM、runtime 或日志提交到 Git。
- 不要把 Token 放到命令行参数、截图、任务计划程序参数或日志中。
- SSH 只使用私钥路径；私钥内容不会被读取后打印。
- 生产环境先用 `certbot renew --dry-run` 或 Staging 验证，避免触发 Let's Encrypt 速率限制。
- Certbot 的 `config-dir`、`work-dir`、`live/`、`archive/` 和 `renewal/` 保持独立；ZhangCertbot 只读取 live 结果并导出最终文件。

## 测试

测试使用 pytest 和 mock，不向 Production Let's Encrypt 申请证书：

```powershell
pytest
python -m compileall main.py src tests
python main.py --help
python main.py version
```

## 常见错误

- `未找到 Certbot`：安装 `certbot` 并确认 PATH，或确认当前 Python 环境已安装 Certbot。
- DNS Challenge 失败：检查 Token 权限、Zone、域名委托和 Cloudflare 记录权限。
- SSH 私钥不存在/格式错误：检查配置中的路径和当前 Windows 用户权限。
- 目标目录不存在：先在 Linux 服务器创建目录并确认 SSH 用户有写权限。
- `nginx -t` 失败：检查证书路径、私钥权限和 Nginx 配置；程序不会 reload。
- 证书不存在：先执行 `python main.py issue`，或确认 Certbot 的 `cert-name` 与域名配置一致。
