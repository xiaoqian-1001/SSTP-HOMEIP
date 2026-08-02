#!/usr/bin/env python3
"""与 check.socks5.cmliussss.net 交互的共享模块。

接口: GET /check?socks5=host:port
      GET /check?http=host:port / ?https= / ?turn= / ?sstp=
      GET /check?proxy=scheme://host:port
      支持带认证格式 user:pass@host:port

返回: success(可用性) / responseTime(延迟ms) / colo(入口节点) /
      exit(出口 IP 完整信息, 成功时) / error(失败原因)

风险评级算法与前端一致，基于出口 IP 的 abuser_score 与
is_proxy/is_vpn/is_tor/is_crawler/is_abuser/is_bogon 标记。
"""

import os
import re
import urllib.parse
import urllib.request

CHECK_API = "https://check.socks5.cmliussss.net/check"
CHECK_TIMEOUT = 40
CONCURRENCY = int(os.environ.get("PROXY_CHECK_CONCURRENCY", "6"))

ABUSER_RE = re.compile(r"\s*([0-9]+(?:\.[0-9]+)?)")


def as_score(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    m = ABUSER_RE.match(str(v or ""))
    return float(m.group(1)) if m else 0.0


def calc_risk(exit_data: dict | None) -> dict | None:
    if not exit_data:
        return None
    company = as_score((exit_data.get("company") or {}).get("abuser_score"))
    asn = as_score((exit_data.get("asn") or exit_data.get("asnInfo") or {}).get("abuser_score"))
    base = ((company + asn) / 2) * 5
    flags = [exit_data.get("is_crawler"), exit_data.get("is_proxy"),
             exit_data.get("is_vpn"), exit_data.get("is_tor"), exit_data.get("is_abuser")]
    risk_count = sum(1 for f in flags if f is True)
    score = base + risk_count * 0.15
    if exit_data.get("is_bogon"):
        score += 1.0
    if base == 0 and risk_count == 0 and not exit_data.get("is_bogon"):
        return None
    pct = score * 100
    if pct >= 100:
        level = "critical"
    elif pct >= 20:
        level = "high"
    elif pct >= 5:
        level = "elevated"
    elif pct >= 0.25:
        level = "low"
    else:
        level = "verylow"
    return {"score": round(score, 4), "percent": round(pct, 2), "level": level}


def extract_exit_fields(exit_data: dict | None) -> dict:
    if not exit_data:
        return {}
    loc = exit_data.get("location") or {}
    dc = exit_data.get("datacenter") or {}
    asn_obj = exit_data.get("asn") or exit_data.get("asnInfo") or {}
    return {
        "exit_ip": exit_data.get("ip"),
        "exit_country": loc.get("country") or dc.get("country"),
        "exit_countryCode": loc.get("country_code") or dc.get("country"),
        "exit_asn": asn_obj.get("asn"),
        "exit_org": asn_obj.get("org") or asn_obj.get("descr"),
    }


def check_api(target: str, ptype: str, timeout: int = CHECK_TIMEOUT) -> dict:
    q = urllib.parse.urlencode({ptype: target})
    req = urllib.request.Request(
        f"{CHECK_API}?{q}",
        headers={"User-Agent": "Mozilla/5.0 (proxy-list updater)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json_load(resp.read().decode("utf-8", errors="replace"))


def json_load(text: str) -> dict:
    import json
    return json.loads(text)
