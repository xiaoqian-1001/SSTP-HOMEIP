#!/usr/bin/env python3
"""临时调研脚本：抓取 vpngate 首页 HTML，打印服务器列表表格结构。"""

import re
import sys
import urllib.request

URL = "https://www.vpngate.net/cn/"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def main() -> int:
    req = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        html = resp.read().decode("utf-8", errors="replace")
    print("HTML size:", len(html), flush=True)

    rows = re.findall(r"<tr[^>]*>.*?</tr>", html, re.S)
    print("table rows:", len(rows), flush=True)

    print("--- all server rows SSTP cell raw html:", flush=True)
    for r in rows:
        if "vg_table_row" in r and ("public-vpn" in r or "opengw.net" in r):
            cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)
            for c in cells:
                if "SSTP" in c or "sstp" in c.lower():
                    clean = re.sub(r"<[^>]+>", "|", c)
                    clean = re.sub(r"\|+", " | ", clean)
                    clean = re.sub(r"\s+", " ", clean).strip()
                    print(clean[:200], flush=True)
                    break
    count = 0
    for ln in html.splitlines():
        if "sstp" in ln.lower():
            print(ln.strip()[:300], flush=True)
            count += 1
            if count >= 10:
                break

    print("--- table headers:", flush=True)
    for h in re.findall(r"<th[^>]*>[^<]*</th>", html)[:40]:
        print(h, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
