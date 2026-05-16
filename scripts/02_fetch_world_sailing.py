"""Fetch the World Sailing Member National Authorities list.

The membership page (https://www.sailing.org/inside-world-sailing/
organisation/governance/world-sailing-membership/) is rendered by a Nuxt
SSR app: the visible accordion is empty in the static HTML, but the
"Member National Authority Groups" table is embedded as a unicode-escaped
HTML string inside the `window.__NUXT__` payload. We extract that string,
unescape it, then parse the (Country, Code, Group) table with BeautifulSoup.

Outputs:
  sources/world-sailing-members.html  — raw HTML as fetched
  sources/world-sailing-members.json  — parsed list of {code, name, group}
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parent.parent
HTML_PATH = REPO_ROOT / "sources" / "world-sailing-members.html"
JSON_PATH = REPO_ROOT / "sources" / "world-sailing-members.json"

WS_URL = (
    "https://www.sailing.org/inside-world-sailing/organisation/governance/"
    "world-sailing-membership/"
)
USER_AGENT = (
    "national-letters/0.4 "
    "(https://github.com/sailscoring/national-letters; markbmc@gmail.com)"
)

# Match the Nuxt payload block. It's emitted as
#   window.__NUXT__=(function(...){...}(...));
# Some Nuxt versions use a non-IIFE form too; we accept either.
NUXT_RE = re.compile(r"window\.__NUXT__\s*=\s*(.+?)</script>", re.DOTALL)
CODE_RE = re.compile(r"^[A-Z]{3}$")


def fetch(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    return r.text


def _decode_unicode_escapes(s: str) -> str:
    """Turn \\u003C / \\u002F sequences in JS source back into characters."""
    return re.sub(
        r"\\u([0-9A-Fa-f]{4})",
        lambda m: chr(int(m.group(1), 16)),
        s,
    )


def extract_members(html: str) -> list[dict[str, str]]:
    """Return all (code, name, group) rows from the embedded MNA table."""
    nuxt_match = NUXT_RE.search(html)
    if not nuxt_match:
        raise RuntimeError("could not find window.__NUXT__ block in HTML")
    decoded = _decode_unicode_escapes(nuxt_match.group(1))

    # The MNA Groups tables have three columns with the canonical header
    # row "Nation | Code | Group". The page also embeds a Subscription
    # Categories block whose rows are 5-column lists of country names —
    # those rows occasionally include cells like "USA" or "GBR" that look
    # like codes but are not. The header check filters them out.
    soup = BeautifulSoup(decoded, "html.parser")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for table in soup.find_all("table"):
        trs = table.find_all("tr")
        if not trs:
            continue
        header = [td.get_text(strip=True).lower() for td in trs[0].find_all(["td", "th"])]
        if header[:3] != ["nation", "code", "group"]:
            continue
        for tr in trs[1:]:
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            name, code = cells[0], cells[1]
            group = cells[2] if len(cells) > 2 else ""
            if not name or not CODE_RE.match(code):
                continue
            if code in seen:
                continue
            rows.append({"code": code, "name": name, "group": group})
            seen.add(code)
    return rows


def main() -> int:
    print(f"fetching {WS_URL} …", file=sys.stderr)
    html = fetch(WS_URL)
    HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    HTML_PATH.write_text(html)

    members = extract_members(html)
    if not members:
        print(
            "error: extracted 0 members — page structure may have changed",
            file=sys.stderr,
        )
        return 1

    timestamp = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    payload = {
        "source": "world-sailing",
        "retrievedAt": timestamp,
        "sourceUrl": WS_URL,
        "count": len(members),
        "members": sorted(members, key=lambda m: m["code"]),
    }
    JSON_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(
        f"wrote {len(members)} members to {JSON_PATH.relative_to(REPO_ROOT)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
