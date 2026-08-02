#!/usr/bin/env python3
"""抓取 vpngate.net 的服务器列表并生成 SSTP 服务器配置文件。

数据来源: https://www.vpngate.net/api/iphone/  （与 vpngate.net 首页列表同源）
vpngate 服务器均基于 SoftEther VPN Server，原生支持 SSTP 协议。
SSTP 连接参数: hostname/IP + 端口 443，账号 vpn，密码 vpn。
"""

import csv
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
    lines = text.splitlines()
    header_idx = None
    for i, line in enumerate(lines):
        stripped = line.lstrip("#* \t")
        if stripped.startswith("HostName,"):
            header_idx = i
            break
    if header_idx is None:
        return []
    header = lines[header_idx].lstrip("#* \t")
    body = lines[header_idx + 1:]
    return list(csv.DictReader([header] + body))


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
        hostname = (s.get("HostName") or "").strip()
        ip = (s.get("IP") or "").strip()
        if not (hostname or ip):
            continue
        host = hostname or ip
        speed_bps = to_float(s.get("Speed"))
        records.append(
            {
                "sstp": f"sstp://{host}:{SSTP_PORT}",
                "hostname": hostname,
                "ip": ip,
                "port": SSTP_PORT,
                "username": SSTP_USER,
                "password": SSTP_PASS,
                "country": (s.get("CountryLong") or "").strip(),
                "country_short": (s.get("CountryShort") or "").strip(),
                "score": to_int(s.get("Score")),
                "ping_ms": to_int(s.get("Ping")),
                "speed_mbps": round(speed_bps / 125000, 1),
                "sessions": to_int(s.get("NumVpnSessions")),
            }
        )
    records.sort(key=lambda r: (-r["score"], r["ping_ms"]))
    return records


def main() -> int:
    print(f"[*] Fetching {API_URL}", flush=True)
    raw = fetch(API_URL)
    servers = parse_csv(raw)
    print(f"[*] Total servers: {len(servers)}", flush=True)

    records = build_records(servers)
    print(f"[*] SSTP servers: {len(records)}", flush=True)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    with open(OUTPUT_TXT, "w", encoding="utf-8") as f:
        f.write("# vpngate.net SSTP 服务器列表\n")
        f.write(f"# 更新时间: {now}\n")
        f.write(f"# 账号: {SSTP_USER}  密码: {SSTP_PASS}  端口: {SSTP_PORT}\n")
        f.write("# 格式: sstp://主机:端口 | 国家 | 评分 | 延迟ms | 速度Mbps\n")
        f.write("#\n")
        for r in records:
            f.write(
                "{sstp} | {country} | score {score} | ping {ping}ms | {speed} Mbps\n".format(
                    sstp=r["sstp"],
                    country=r["country"],
                    score=r["score"],
                    ping=r["ping_ms"],
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
