#!/usr/bin/env python3
"""抓取 vpngate.net 的服务器列表并生成 SSTP 服务器配置文件。

数据来源: https://www.vpngate.net/api/iphone/  （与 vpngate.net 首页列表同源）
vpngate 服务器均基于 SoftEther VPN Server，原生支持 SSTP 协议。
SSTP 连接参数: hostname/IP + 端口 443，账号 vpn，密码 vpn。
"""

import csv
import io
import json
import sys
import urllib.request
from datetime import datetime, timezone

API_URL = "https://www.vpngate.net/api/iphone/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36 "
    "vpngate-sstp-fetcher/1.0"
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


def parse_csv(text: str) -> list[dict]:
    lines = [
        line
        for line in text.splitlines()
        if line and not line.startswith(("#", "*"))
    ]
    if not lines:
        return []
    return list(csv.DictReader(io.StringIO("\n".join(lines))))


def to_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_records(servers: list[dict]) -> list[dict]:
    records = []
    for s in servers:
        if to_int(s.get("State")) < 1:
            continue
        hostname = (s.get("HostName") or "").strip()
        ip = (s.get("IP") or "").strip()
        if not (hostname or ip):
            continue
        host = hostname or ip
        records.append(
            {
                "sstp": f"sstp://{host}:{SSTP_PORT}",
                "hostname": hostname,
                "ip": ip,
                "port": SSTP_PORT,
                "username": SSTP_USER,
                "password": SSTP_PASS,
                "country": (s.get("Country") or "").strip(),
                "load": to_int(s.get("Load")),
                "availability": to_float(s.get("Availability")),
                "speed_mbps": to_int(s.get("Bandwidth")),
                "clients": to_int(s.get("NumClients")),
            }
        )
    records.sort(key=lambda r: (-r["availability"], r["load"]))
    return records


def main() -> int:
    print(f"[*] Fetching {API_URL}", flush=True)
    raw = fetch(API_URL)
    servers = parse_csv(raw)
    print(f"[*] Total servers: {len(servers)}", flush=True)

    records = build_records(servers)
    print(f"[*] Online servers (SSTP capable): {len(records)}", flush=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        f.write("# vpngate.net SSTP 服务器列表\n")
        f.write(f"# 更新时间: {now}\n")
        f.write(f"# 账号: {SSTP_USER}  密码: {SSTP_PASS}  端口: {SSTP_PORT}\n")
        f.write("# 格式: sstp://主机:端口 | 国家 | 负载 | 可用性 | 速度Mbps\n")
        f.write("#\n")
        for r in records:
            f.write(
                "{sstp} | {country} | load {load} | avail {availability:.1f}% | {speed} Mbps\n".format(
                    sstp=r["sstp"],
                    country=r["country"],
                    load=r["load"],
                    availability=r["availability"],
                    speed=r["speed_mbps"],
                )
            )

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(
            {
                "source": API_URL,
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
