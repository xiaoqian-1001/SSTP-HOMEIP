#!/usr/bin/env python3
"""抓取公开免费 HTTP/HTTPS/SOCKS5 代理列表，通过 check.socks5.cmliussss.net 验证可用性、测速与风险评级。

数据源:
  - TheSpeedX/PROXY-List (socks5 / http)，每小时更新
  - jetkai/proxy-list (socks5 / http)，每日更新
验证:
  - 本地 TCP 预筛（快）
  - check.socks5.cmliussss.net /check 接口测速 + 风险评级
输出:
  - socks5-list.txt / socks5.json
  - http-list.txt / http.json
"""

import concurrent.futures as cf
import json
import os
import re
import socket
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import proxy_check

TCP_CONCURRENCY = 80
TCP_TIMEOUT = 3
MAX_CHECK = int(os.environ.get("PROXY_MAX_CHECK", "150"))

SOURCES = {
    "socks5": [
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
        "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt",
    ],
    "http": [
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
    ],
}

IP_PORT_RE = re.compile(r"^([0-9]{1,3}\.){3}[0-9]{1,3}:[0-9]{1,5}$")
USERPASS_RE = re.compile(r"^[^@:\s/]+:[^@:\s/]+@([0-9]{1,3}\.){3}[0-9]{1,3}:[0-9]{1,5}$")


def now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (proxy-list updater)"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def fetch_candidates(ptype: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for url in SOURCES.get(ptype, []):
        try:
            text = fetch(url)
        except Exception as exc:
            print(f"[!] {ptype} source failed {url}: {exc}", file=sys.stderr)
            continue
        for line in text.splitlines():
            line = line.strip()
            if IP_PORT_RE.match(line) or USERPASS_RE.match(line):
                key = line.rsplit("@", 1)[-1]
                if key not in seen:
                    seen.add(key)
                    out.append(line)
        print(f"[*] {ptype} from {url}: {len([l for l in text.splitlines() if l.strip()])} lines", flush=True)
    return out


def tcp_reachable(target: str, timeout: int = TCP_TIMEOUT) -> bool:
    host, port = target.rsplit("@", 1)[-1].rsplit(":", 1)
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except Exception:
        return False


def tcp_prescreen(targets: list[str]) -> list[str]:
    print(f"[*] TCP pre-screen {len(targets)} targets...", flush=True)
    ok: list[str] = []
    with cf.ThreadPoolExecutor(max_workers=TCP_CONCURRENCY) as pool:
        futures = {pool.submit(tcp_reachable, t): t for t in targets}
        for fut in cf.as_completed(futures):
            if fut.result():
                ok.append(futures[fut])
    ok.sort(key=targets.index)
    print(f"[*] TCP reachable: {len(ok)}", flush=True)
    return ok


def check_batch(targets: list[str], ptype: str) -> list[dict]:
    results: list[dict] = []
    limit = min(len(targets), MAX_CHECK)
    print(f"[*] Checking via {proxy_check.CHECK_API} ({limit} targets, concurrency={proxy_check.CONCURRENCY})...", flush=True)
    with cf.ThreadPoolExecutor(max_workers=proxy_check.CONCURRENCY) as pool:
        futures = {}
        for t in targets[:limit]:
            futures[pool.submit(proxy_check.check_api, t, ptype)] = t
        done = 0
        for fut in cf.as_completed(futures):
            t = futures[fut]
            done += 1
            try:
                data = fut.result()
            except Exception as exc:
                data = {"success": False, "candidate": t, "error": f"check request failed: {exc}"}
            rec = {
                "candidate": data.get("candidate", t),
                "link": data.get("link"),
                "success": bool(data.get("success")),
                "responseTime": data.get("responseTime"),
                "colo": data.get("colo"),
            }
            if data.get("success"):
                exit_data = data.get("exit")
                rec.update(proxy_check.extract_exit_fields(exit_data))
                rec["risk"] = proxy_check.calc_risk(exit_data)
            else:
                rec["error"] = data.get("error")
            results.append(rec)
            if done % 25 == 0 or done == limit:
                print(f"[*] checked {done}/{limit}", flush=True)
    results.sort(key=lambda r: r["candidate"])
    return results


def write_output(ptype: str, targets: list[str], results: list[dict], out_dir: Path):
    now = now_str()
    good = [r for r in results if r["success"]]
    txt_lines = [f"# 免费 {ptype.upper()} 代理列表", f"# 更新时间: {now}",
                 "# 已通过 TCP 预筛 + check.socks5.cmliussss.net 验证", "# 格式: ip:port",
                 "# 仅保留成功且风险评级非 critical/high 的节点", "#"]
    for r in sorted(good, key=lambda r: (r.get("risk") or {}).get("percent") or 0):
        level = (r.get("risk") or {}).get("level")
        if level in ("critical", "high"):
            continue
        txt_lines.append(r["candidate"])

    list_path = out_dir / f"{ptype}-list.txt"
    list_path.write_text("\n".join(txt_lines) + "\n", encoding="utf-8")

    json_path = out_dir / f"{ptype}.json"
    json_path.write_text(json.dumps({
        "updated": now,
        "type": ptype,
        "source": SOURCES.get(ptype),
        "count": len(good),
        "servers": good,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    levels = {}
    for r in good:
        lv = (r.get("risk") or {}).get("level") or "unknown"
        levels[lv] = levels.get(lv, 0) + 1
    print(f"[*] {ptype}: checked={len(results)} success={len(good)} risk={levels}", flush=True)
    print(f"[*] Wrote {list_path.name} and {json_path.name}", flush=True)


def main() -> int:
    out_dir = Path(__file__).resolve().parent.parent
    for ptype in ("socks5", "http"):
        try:
            targets = fetch_candidates(ptype)
            if not targets:
                print(f"[!] no {ptype} candidates fetched, skip", file=sys.stderr)
                continue
            targets = tcp_prescreen(targets)
            if not targets:
                print(f"[!] no {ptype} targets survived TCP pre-screen, skip", file=sys.stderr)
                continue
            results = check_batch(targets, ptype)
            write_output(ptype, targets, results, out_dir)
        except Exception as exc:
            print(f"[!] {ptype} pipeline failed: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
