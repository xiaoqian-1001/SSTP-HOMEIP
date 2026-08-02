#!/usr/bin/env python3
"""抓取 vpngate.net 网站首页的服务器列表并生成 SSTP 服务器配置文件。

数据来源: https://www.vpngate.net/cn/  （网站服务器列表页面）
从每个服务器行的 MS-SSTP 列提取官方标注的 SSTP 主机名，
生成格式: sstp://vpn:vpn@主机名:端口（默认端口 443）。
"""

import json
import os
import re
import socket
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import proxy_check

PAGE_URL = "https://www.vpngate.net/cn/"
SUB_URL = "https://sub.cmliussss.net/vpngate"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
SSTP_USER = "vpn"
SSTP_PASS = "vpn"
SSTP_PORT = 443

OUTPUT_TXT = "sstp-list.txt"
OUTPUT_JSON = "sstp.json"


def fetch(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_servers(html: str) -> list[dict]:
    servers = []
    for row in re.findall(r"<tr[^>]*>.*?</tr>", html, re.S):
        if "vg_table_row" not in row or "opengw.net" not in row:
            continue
        s: dict = {}

        m = re.search(
            r"<b><span style='font-size: 9pt;'>([^<]+)</span></b>\s*<br>\s*"
            r"<span style='font-size: 10pt;'>([^<]+)</span>",
            row,
            re.S,
        )
        if m:
            s["HostName"] = m.group(1).strip()
            s["IP"] = m.group(2).strip()

        m = re.search(
            r"SSTP 主机名.*?<span[^>]*>\s*([^<]+?)\s*</span>", row, re.S
        )
        if m:
            s["SSTP_HostName"] = m.group(1).strip()

        m = re.search(
            r"<td class='vg_table_row_\d' style='text-align: center;'>.*?<br>\s*(.*?)\s*</td>",
            row,
            re.S,
        )
        if m:
            s["Country"] = m.group(1).strip()

        m = re.search(r"<b><span style='font-size: 10pt;'>([\d.]+) Mbps</span>", row)
        if m:
            s["Speed"] = float(m.group(1))

        m = re.search(r"Ping:\s*<b>([\d.]+) ms</b>", row)
        if m:
            s["Ping"] = float(m.group(1))

        if s.get("SSTP_HostName") or s.get("HostName"):
            servers.append(s)
    return servers


def split_host_port(hostname: str, default_port: int) -> tuple[str, int]:
    if ":" in hostname:
        host, _, port = hostname.rpartition(":")
        if host and port.isdigit():
            return host, int(port)
    return hostname, default_port


def build_records(servers: list[dict]) -> list[dict]:
    records = []
    for s in servers:
        host = (s.get("SSTP_HostName") or s.get("HostName") or "").strip()
        if not host:
            continue
        host, port = split_host_port(host, SSTP_PORT)
        records.append(
            {
                "sstp": f"sstp://{SSTP_USER}:{SSTP_PASS}@{host}:{port}",
                "hostname": host,
                "ip": (s.get("IP") or "").strip(),
                "port": port,
                "username": SSTP_USER,
                "password": SSTP_PASS,
                "country": (s.get("Country") or "").strip(),
                "ping_ms": int(s.get("Ping", 0)),
                "speed_mbps": round(s.get("Speed", 0), 1),
            }
        )
    records.sort(key=lambda r: (-r["speed_mbps"], r["ping_ms"]))
    return records


def check_reachable(host: str, port: int, timeout: int = 4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def filter_reachable(
    records: list[dict], max_workers: int = 20, timeout: int = 4
) -> list[dict]:
    if not records:
        return []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(check_reachable, r["hostname"], r["port"], timeout): r
            for r in records
        }
        ok = [futures[f] for f in futures if f.result()]
    return ok


def fetch_sub_records(url: str) -> list[dict]:
    """抓取第三方订阅源，解析每行 sstp:// 链接。"""
    text = fetch(url)
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("sstp://"):
            continue
        m = re.match(r"sstp://([^@/]+)@([^/]+)$", line)
        if not m:
            continue
        cred, host = m.group(1), m.group(2)
        user, _, passwd = cred.partition(":")
        hostname, _, port_s = host.rpartition(":")
        if not hostname or not port_s.isdigit():
            hostname, port = host, SSTP_PORT
        else:
            port = int(port_s)
        records.append(
            {
                "sstp": f"sstp://{user}:{passwd}@{hostname}:{port}",
                "hostname": hostname,
                "ip": "",
                "port": port,
                "username": user,
                "password": passwd,
                "country": "",
                "ping_ms": 0,
                "speed_mbps": 0,
                "source": url,
            }
        )
    return records


def merge_records(*groups: list[dict]) -> list[dict]:
    merged: dict[tuple[str, int], dict] = {}
    for group in groups:
        for r in group:
            key = (r["hostname"], r["port"])
            if key not in merged:
                merged[key] = r
    return list(merged.values())


def check_via_api(records: list[dict], max_workers: int | None = None) -> list[dict]:
    """通过 check.socks5.cmliussss.net 验证 SSTP 可用性、测速并计算风险评级。"""
    if not records:
        return []
    max_workers = max_workers or proxy_check.CONCURRENCY
    print(f"[*] Verifying via {proxy_check.CHECK_API} ({len(records)} targets, "
          f"concurrency={max_workers})...", flush=True)

    def do_check(r: dict) -> dict:
        target = f"{r['username']}:{r['password']}@{r['hostname']}:{r['port']}"
        try:
            return proxy_check.check_api(target, "sstp")
        except Exception as exc:
            return {"success": False, "error": f"check request failed: {exc}"}

    done = 0
    total = len(records)
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(do_check, r): r for r in records}
        for fut in futures:
            r = futures[fut]
            d = fut.result()
            done += 1
            r["check_ok"] = bool(d.get("success"))
            if d.get("success"):
                r["responseTime"] = d.get("responseTime")
                r["colo"] = d.get("colo")
                r.update(proxy_check.extract_exit_fields(d.get("exit")))
                r["risk"] = proxy_check.calc_risk(d.get("exit"))
            else:
                r["check_error"] = (d.get("error") or "")[:120]
            if done % 25 == 0 or done == total:
                print(f"[*] checked {done}/{total}", flush=True)
    ok = [r for r in records if r["check_ok"]]
    print(f"[*] SSTP check success: {len(ok)}/{total}", flush=True)
    return ok


def main() -> int:
    print(f"[*] Fetching {PAGE_URL}", flush=True)
    html = fetch(PAGE_URL)
    servers = parse_servers(html)
    print(f"[*] Servers on page: {len(servers)}", flush=True)

    records = build_records(servers)
    for r in records:
        r["source"] = PAGE_URL
    print(f"[*] SSTP servers (page): {len(records)}", flush=True)

    try:
        sub_records = fetch_sub_records(SUB_URL)
        print(f"[*] SSTP servers (sub): {len(sub_records)}", flush=True)
    except Exception as exc:
        print(f"[!] Sub source unavailable, skipped: {exc}", file=sys.stderr)
        sub_records = []

    records = merge_records(records, sub_records)
    print(f"[*] Merged after dedup: {len(records)}", flush=True)

    max_check = int(os.environ.get("PROXY_MAX_CHECK", "0")) or None
    if max_check:
        records = records[:max_check]
        print(f"[*] Limited to first {max_check} records", flush=True)

    records = filter_reachable(records)
    print(f"[*] Reachable after TCP pre-screen: {len(records)}", flush=True)

    records = check_via_api(records)
    records.sort(key=lambda r: (r.get("risk") or {}).get("percent") or 0)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        f.write("# vpngate.net SSTP 服务器列表\n")
        f.write(f"# 更新时间: {now}\n")
        f.write(f"# 账号: {SSTP_USER}  密码: {SSTP_PASS}\n")
        f.write(f"# 数据源: {PAGE_URL}\n")
        f.write(f"# 数据源: {SUB_URL}\n")
        f.write(f"# 已通过 {proxy_check.CHECK_API} 验证 SSTP 连通性、测速与风险评级\n")
        f.write("# 按风险评级升序排列（低风险在前）\n")
        f.write("# 格式: sstp://账号:密码@主机:端口\n")
        f.write("#\n")
        for r in records:
            f.write(r["sstp"] + "\n")

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(
            {
                "source": [PAGE_URL, SUB_URL],
                "updated": now,
                "username": SSTP_USER,
                "password": SSTP_PASS,
                "port": SSTP_PORT,
                "count": len(records),
                "servers": records,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"[*] Wrote {OUTPUT_TXT} and {OUTPUT_JSON}", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"[!] Failed: {exc}", file=sys.stderr)
        sys.exit(1)
