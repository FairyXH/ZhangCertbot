# ZhangCertbot

ZhangCertbot 是一个轻量、独立、无数据库的 Let's Encrypt 证书管理工具。它使用 ACME v2 完成 DNS-01 验证，首版支持 Cloudflare API Token，适合泛域名证书和 Linux VPS 无人值守续期。

当前版本：`0.1.0`

## 功能范围

- Let's Encrypt Production 和 Staging
- ACME v2
- DNS-01 challenge
- Cloudflare API Token
- 泛域名，例如 `example.com` 和 `*.example.com`
- 额外 SAN，例如 `api.example.com`
- ECDSA P-256 或 RSA 2048 证书私钥
- ACME Account 私钥持久化，续期复用同一个 Account
- 公共 DNS resolver 传播检查，支持超时、重试和间隔
- challenge 成功、失败、异常路径尽力清理 TXT
- 多个 TXT value 共存，不因清理一个 challenge 而删除其他 value
- PEM、SAN、有效期、证书/私钥匹配校验
- 临时文件加 `os.replace` 原子更新
- 可选 deploy hook，例如 reload Nginx
- cron 和 systemd timer 部署方式
- 非交互 `renew`，适合 cron/systemd

首版明确不实现 HTTP-01、其他 CA、Web 管理后台、数据库、Docker、自动修改 DNS Nameserver 或自动修改 Nginx 配置。

## 系统要求

- Python 3.10 或更高版本
- Linux VPS、Windows 开发机均可运行
- 域名 DNS 必须由 Cloudflare 托管，或者 Cloudflare Zone 至少能管理目标 DNS 记录
- 申请泛域名必须使用 DNS-01

## 安装

Linux：

```bash
git clone <repository-url> ZhangCertbot
cd ZhangCertbot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell：

```powershell
cd D:\Files\Develop\Algorithm_Development\Python\ZhangCertbot
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

第三方依赖：

- `acme`：Let's Encrypt 官方 ACME Python 客户端生态，处理目录、JWS、Account、Order、Authorization、Finalize 等协议细节。
- `josepy`：为 `acme` 提供 ACME 所需的 JWK/JWS 签名对象。
- `cryptography`：生成 ECDSA/RSA 密钥、CSR，以及验证下载证书和私钥。
- `dnspython`：通过指定的公共 DNS resolver 查询 TXT。
- `tomli`：仅 Python 3.10 使用，因为 Python 3.11 起已经内置 `tomllib`。

## Cloudflare Token

在 Cloudflare 创建 API Token，推荐限制到目标 Zone，并授予：

- `Zone:Read`
- `DNS:Edit`

不要使用 Global API Key。不要把 Token 写入 shell 历史、工单、截图或日志。

Token 仅用于 Cloudflare API 请求，不会发送到其他第三方服务。程序日志不会打印 Token。

## 首次申请

首次运行：

```bash
python main.py
```

程序会依次询问：

1. Let's Encrypt 环境
   - `1`：Production
   - `2`：Staging
2. ACME Account Email
3. 域名列表，使用逗号分隔
4. Cloudflare API Token

示例：

```text
Let's Encrypt environment [1 Production / 2 Staging] (default 1): 2
Email: admin@example.com
Domains (comma-separated, include example.com and *.example.com): example.com, *.example.com, api.example.com
Cloudflare API Token: <token>
```

Production 会受到 Let's Encrypt rate limit 限制。第一次配置、DNS 委托变更和故障排查时应优先选 Staging。Staging 证书不受浏览器信任，只用于流程测试。

当配置文件不存在时，程序创建 `config.toml`，随后执行一次完整申请。配置文件已经存在时，直接运行 `python main.py` 会显示证书信息，不会覆盖配置。

域名必须是域名而不是 URL：

```text
正确：example.com
正确：*.example.com
错误：https://example.com
错误：example.com/path
```

## 配置文件

配置文件是项目根目录的 `config.toml`，模板是 `config.example.toml`：

```toml
[acme]
email = "admin@example.com"
environment = "staging"

[certificate]
domains = [
    "example.com",
    "*.example.com",
    "api.example.com"
]
key_type = "ecdsa"
output_dir = "./data/certificates/example.com"

[dns]
provider = "cloudflare"
api_token = ""
propagation_timeout = 120
propagation_interval = 5
resolvers = ["1.1.1.1", "8.8.8.8"]

[renew]
days_before_expiry = 30

[deploy]
command = ""
```

字段说明：

- `acme.email`：ACME Account 联系邮箱。
- `acme.environment`：`production` 或 `staging`。
- `certificate.domains`：所有申请域名，包含 wildcard 和 SAN。
- `certificate.key_type`：`ecdsa` 或 `rsa`。
- `certificate.output_dir`：证书输出目录。相对路径相对于项目根目录。
- `dns.provider`：当前必须是 `cloudflare`。
- `dns.api_token`：Cloudflare API Token。
- `dns.propagation_timeout`：DNS 传播最大等待秒数。
- `dns.propagation_interval`：DNS 查询失败后的重试间隔秒数。
- `dns.resolvers`：查询 TXT 的公共 DNS resolver。
- `renew.days_before_expiry`：小于等于该天数时触发续期。
- `deploy.command`：续期完成后执行的命令，空字符串表示不执行。

`renew` 不读取交互输入。配置缺失、配置格式错误、Token 缺失或证书不存在时直接报错并返回非 0。

## CLI 使用

显示帮助：

```bash
python main.py --help
```

显示版本：

```bash
python main.py version
```

查看证书：

```bash
python main.py check
python main.py info
```

`check` 和 `info` 当前输出同一份证书信息：域名、签发时间、过期时间、剩余天数和状态。

自动续期：

```bash
python main.py renew
```

逻辑如下：

1. 读取 `config.toml`。
2. 如果已有证书，解析过期时间。
3. 剩余天数大于 `days_before_expiry` 时输出 `No renewal required` 并退出 0。
4. 剩余天数小于等于阈值时执行一次完整 ACME DNS-01 流程。
5. 创建或复用 ACME Account。
6. 创建 DNS TXT，等待公共 DNS resolver 都查到目标 value。
7. 通知 Let's Encrypt 验证并等待 Authorization 完成。
8. Finalize Order，下载完整证书链。
9. 校验证书 PEM、SAN、日期和证书/私钥匹配。
10. 原子替换证书文件。
11. 执行 deploy hook。
12. 返回状态码。

强制续期：

```bash
python main.py renew --force
```

此命令忽略续期阈值并直接申请新证书。每次 CLI 调用最多执行一轮申请，不会失败后内部无限循环。频繁使用 `--force` 可能触发 Let's Encrypt rate limit。

调试模式：

```bash
python main.py --debug renew
```

普通模式不会打印 traceback；调试模式会附带 traceback。无论模式如何，Token、Account 私钥和证书私钥都不会写入日志。

自定义配置路径：

```bash
python main.py --config /etc/zhangcertbot/config.toml check
python main.py --config /etc/zhangcertbot/config.toml renew
```

## DNS-01 实现

对每个 Authorization，程序选择 DNS-01 challenge，计算 ACME TXT value，并创建：

```text
_acme-challenge.example.com
```

Cloudflare provider 会先查询目标 Zone，再查询同名 TXT 记录。创建时如果相同 value 已存在则不重复创建；删除时只删除本次 challenge 对应的 value，其他 TXT value 保留。

Cloudflare API 返回成功不等于公网 DNS 已经传播。程序会使用配置中的 resolver 查询 TXT，并要求所有 resolver 都发现目标 value；超过 `propagation_timeout` 后失败。DNS 查询异常视为可重试错误。

所有已创建的 TXT value 都在 `finally` 清理。清理失败只记录 warning，不覆盖原始 ACME 错误。

## 证书文件

默认目录：

```text
data/
├── account.key
├── account.url
└── certificates/
    └── example.com/
        ├── cert.pem
        ├── chain.pem
        ├── fullchain.pem
        ├── metadata.json
        └── privkey.pem
```

说明：

- `account.key`：ACME Account 私钥，续期复用，不会每次创建新 Account。
- `account.url`：ACME Account URL，用于恢复已有 Account。
- `cert.pem`：叶子证书。
- `chain.pem`：中间证书链。
- `fullchain.pem`：叶子证书加中间链，Nginx 通常使用此文件。
- `privkey.pem`：证书私钥。
- `metadata.json`：域名、签发时间和过期时间。

下载的新证书先写入临时文件，执行 flush/fsync，再使用 `os.replace` 替换正式文件。只有完成 PEM、SAN、有效期和私钥匹配检查后才会更新正式证书。

## Nginx

配置：

```nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    ssl_certificate /opt/ZhangCertbot/data/certificates/example.com/fullchain.pem;
    ssl_certificate_key /opt/ZhangCertbot/data/certificates/example.com/privkey.pem;
}
```

然后在 `config.toml` 设置：

```toml
[deploy]
command = "systemctl reload nginx"
```

deploy hook 失败不会回滚已经验证并写入的证书，但程序会记录错误并返回非 0，便于 cron/systemd 监控。程序不会自动修改 Nginx 配置。

Wildcard 规则：`*.example.com` 可以匹配 `api.example.com`、`env.example.com`，不能匹配 `foo.bar.example.com`。后者需要另申请 `*.bar.example.com`。

## cron

每 12 小时检查一次：

```cron
0 */12 * * * cd /opt/ZhangCertbot && /opt/ZhangCertbot/.venv/bin/python main.py renew >> /var/log/zhangcertbot.log 2>&1
```

由于 `renew` 会检查证书剩余时间，正常情况下不会每次申请新证书。建议给日志文件配置 logrotate，或改为 systemd journal。

## systemd timer

项目提供：

```text
deploy/systemd/zhangcertbot.service
deploy/systemd/zhangcertbot.timer
```

安装：

```bash
sudo cp deploy/systemd/zhangcertbot.service /etc/systemd/system/
sudo cp deploy/systemd/zhangcertbot.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now zhangcertbot.timer
sudo systemctl start zhangcertbot.service
```

查看状态：

```bash
systemctl list-timers zhangcertbot.timer
systemctl status zhangcertbot.timer
journalctl -u zhangcertbot.service
```

修改 service 中的 `WorkingDirectory` 和 `ExecStart`，使其与实际安装路径一致。

## 安全措施

- 使用 Cloudflare API Token，不使用 Global API Key。
- Token 不进入日志、证书文件或网络请求以外的其他输出。
- Account 私钥和证书私钥以 PEM 保存，Linux 尝试设置为 600。
- `data` 和证书输出目录尝试设置为 700。
- `config.toml` 尝试设置为 600。
- `.gitignore` 忽略 `config.toml`、`data/`、`*.key`、`*.pem`。
- 证书更新使用临时文件、fsync 和原子 rename。
- 更新前校验证书格式、SAN、有效期和证书/私钥匹配。
- DNS TXT 使用 value 级别清理，避免误删并行 challenge 的其他 value。
- `renew` 每次调用最多申请一次，不在程序内部无限重试。
- deploy hook 不回显 stdout，失败会返回明确错误。

Linux 上建议额外执行：

```bash
chmod 700 /opt/ZhangCertbot/data
chmod 600 /opt/ZhangCertbot/config.toml
chmod 600 /opt/ZhangCertbot/data/account.key
```

不要把以下内容提交 Git 或发送给其他人：

```text
config.toml
data/account.key
data/account.url
data/**/*.key
data/**/*.pem
```

## Staging 测试

在首次初始化时选择 `2`，或者编辑：

```toml
[acme]
environment = "staging"
```

然后执行：

```bash
python main.py renew --force
python main.py check
```

Staging 环境的 Account、Order 和证书与 Production 隔离。确认以下内容后再切换 Production：

- Cloudflare Token 权限正确。
- 域名 Zone 正确。
- `_acme-challenge` TXT 能被公共 resolver 查到。
- DNS 清理成功。
- 证书文件生成且可以被 `cryptography` 解析。
- Nginx reload hook 成功。

Staging 证书通常不被浏览器信任，这是预期行为，不代表 DNS-01 流程失败。

## 常见错误

### `Configuration not found`

先运行 `python main.py` 完成初始化，或使用 `--config` 指定正确路径。

### `Please enter a domain name, not a URL`

删除 `https://`、路径和端口，只输入域名。

### `Cloudflare API error`

检查 Token 是否有目标 Zone 的 `Zone:Read` 和 `DNS:Edit` 权限，检查 Zone 是否确实由当前 Cloudflare 账户管理。

### `Could not find Cloudflare zone`

目标域名的父 Zone 不在当前 Token 可访问范围内，或者 DNS 并未托管在 Cloudflare。

### `DNS propagation timeout`

检查 NS 委托、Cloudflare Zone、TXT 记录名称，以及 VPS 到 `1.1.1.1`/`8.8.8.8` 的出站 DNS 访问。可以适当增大 `propagation_timeout`，但不要只靠 sleep 解决委托错误。

### ACME challenge failed

先切换 Staging，确认 TXT value 在公共 resolver 可查到。不要反复对 Production 使用 `--force`。

### `certificate does not match the private key`

程序会拒绝替换旧证书。检查是否有外部程序改写了证书目录，或恢复了不匹配的临时文件。

### deploy hook 失败

证书已经更新，但服务 reload 失败。手动执行 hook，检查 systemd 权限、Nginx 配置和服务用户权限。

## 测试与验收

安装依赖后运行：

```bash
python -m pytest -q
python -m compileall .
python main.py --help
python main.py version
python main.py check
```

没有 `config.toml` 或证书时，`check` 返回非 0 是正确行为。格式检查：

```bash
git diff --check
```

项目测试不自动申请 Let's Encrypt Production 证书，也不包含真实 Cloudflare Token。真实 Staging/Production 申请需要用户提供实际 DNS 委托和 Token，并应由用户在目标 VPS 上执行。

## 项目结构

```text
ZhangCertbot/
├── main.py
├── requirements.txt
├── README.md
├── config.example.toml
├── .gitignore
├── src/
│   └── zhangcertbot/
│       ├── __init__.py
│       ├── acme_client.py
│       ├── certificate.py
│       ├── cli.py
│       ├── config.py
│       └── providers/
│           ├── __init__.py
│           ├── base.py
│           └── cloudflare.py
├── tests/
│   └── test_config.py
└── deploy/
    └── systemd/
        ├── zhangcertbot.service
        └── zhangcertbot.timer
```

DNS Provider 通过 `DNSProvider` 抽象接口隔离，后续增加 AliDNS、DNSPod、腾讯云 DNS 或华为云 DNS 时，可以新增 provider 实现而不改 ACME challenge 核心流程。
