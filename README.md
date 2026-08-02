# VPNGATE SSTP 抓取器 + 免费代理检测

通过 GitHub Actions 定时抓取 [vpngate.net](https://www.vpngate.net/cn/) 的公开服务器列表，生成可用于 SSTP 协议连接的服务列表；同时抓取公开免费 HTTP/SOCKS5 代理列表，通过 [check.socks5.cmliussss.net](https://check.socks5.cmliussss.net) 验证可用性、测速并计算风险评级。

## 工作流程

### SSTP 列表

- 数据源 1：`https://www.vpngate.net/cn/`（网站首页服务器列表，质量较高）
- 数据源 2：`https://sub.cmliussss.net/vpngate`（第三方订阅源，与数据源 1 合并去重）
- 抓取结果按 `host:port` 去重，再通过 TCP 连通性验证，仅保留端口可达的服务器
- 输出：`sstp-list.txt`（每行一个 `sstp://vpn:vpn@主机:端口`）、`sstp.json`

### 免费 HTTP/SOCKS5 代理

- 数据源：TheSpeedX/PROXY-List、jetkai/proxy-list（每小时/每日更新）
- 流程：抓取候选 → TCP 预筛 → 调用 `check.socks5.cmliussss.net/check` 测速与风险评级
- 风险评级基于出口 IP 的 `abuser_score` 与 `is_proxy/is_vpn/is_tor/is_crawler/is_abuser/is_bogon` 标记，分五档：极度危险 / 高风险 / 轻微风险 / 纯净 / 极度纯净
- 仅保留验证成功且风险评级非「高风险 / 极度危险」的节点
- 输出：`socks5-list.txt`、`socks5.json`、`http-list.txt`、`http.json`
- 可通过环境变量调参：`PROXY_MAX_CHECK`（单协议最多验证节点数，默认 150）、`PROXY_CHECK_CONCURRENCY`（并发数，默认 6）

- 触发：每 6 小时定时执行（`cron: '0 */6 * * *'`），也可在 GitHub Actions 页面手动触发（`workflow_dispatch`）
- 结果：自动提交回仓库

## 使用步骤

1. 将本仓库推送到 GitHub
2. Actions 默认开启，定时任务会自动运行
3. 也可以到 **Actions -> Fetch vpngate SSTP Servers -> Run workflow** 手动触发一次
4. 运行完成后，仓库根目录会生成：

   - `sstp-list.txt` — 文本格式的 SSTP 服务器列表
   - `sstp.json` — JSON 结构化数据（含 hostname、IP、国家、负载、可用性等）
   - `socks5-list.txt` / `socks5.json` — 免费 SOCKS5 代理（含风险评级）
   - `http-list.txt` / `http.json` — 免费 HTTP 代理（含风险评级）

## SSTP 连接参数

- 服务器地址：列表中的 `hostname` 或 `IP`
- 端口：`443`
- 协议：`SSTP`
- 账号：`vpn`
- 密码：`vpn`

## 在 Windows 上使用

SSTP 为 Windows 原生支持的 VPN 协议，可通过 PowerShell 快速添加：

```powershell
Add-VpnConnection -Name "vpngate-sstp" `
  -ServerAddress "sstp://<服务器hostname>:443" `
  -TunnelType Sstp `
  -AuthenticationMethod EAP `
  -EncryptionLevel Required `
  -Force
```

或使用命令方式手动添加。

## 目录结构

```text
.github/workflows/fetch-sstp.yml   # GitHub Actions 定时任务
scripts/fetch_sstp.py              # 抓取与生成 SSTP 列表脚本
scripts/fetch_proxies.py           # 抓取与检测免费代理脚本
sstp-list.txt / sstp.json          # 生成的 SSTP 服务器列表
socks5-list.txt / socks5.json      # 生成的 SOCKS5 代理列表
http-list.txt / http.json          # 生成的 HTTP 代理列表
```

## 免责声明

vpngate.net 为日本筑波大学的 VPN Gate 学术实验项目，本仓库仅抓取其公开数据用于学习研究。免费代理列表来自公开社区资源，代理节点不稳定且可能被滥用，仅建议用于测试；风险评级仅作参考，请勿用于敏感操作。请遵守当地法律法规及目标网站的使用条款。
