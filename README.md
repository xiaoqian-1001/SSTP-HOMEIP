# vpngate SSTP 抓取器

通过 GitHub Actions 定时抓取 [vpngate.net](https://www.vpngate.net/cn/) 的公开服务器列表，生成可用于 SSTP 协议连接的服务列表。

vpngate 的服务器均基于 SoftEther VPN Server，原生支持 SSTP 协议。抓取结果输出到仓库中的 `sstp-list.txt` 和 `sstp.json`。

## 工作流程

- 数据源：`https://www.vpngate.net/api/iphone/`（与 vpngate.net 网站首页服务器列表同源，CSV 格式）
- 触发：每 6 小时定时执行（`cron: '0 */6 * * *'`），也可在 GitHub Actions 页面手动触发（`workflow_dispatch`）
- 结果：自动提交回仓库，生成的 `sstp-list.txt` 为文本列表，`sstp.json` 为结构化数据

## 使用步骤

1. 将本仓库推送到 GitHub
2. Actions 默认开启，定时任务会自动运行
3. 也可以到 **Actions -> Fetch vpngate SSTP Servers -> Run workflow** 手动触发一次
4. 运行完成后，仓库根目录会生成：

   - `sstp-list.txt` — 文本格式的 SSTP 服务器列表
   - `sstp.json` — JSON 结构化数据（含 hostname、IP、国家、负载、可用性等）

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
scripts/fetch_sstp.py              # 抓取与生成脚本
sstp-list.txt                      # 生成的 SSTP 服务器列表
sstp.json                          # 生成的结构化数据
```

## 免责声明

vpngate.net 为日本筑波大学的 VPN Gate 学术实验项目，本仓库仅抓取其公开数据用于学习研究。请遵守当地法律法规及目标网站的使用条款。
