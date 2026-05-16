"""Scrape the Sailwave flag directory for the list of codes it carries.

The Sailwave directory (https://www.sailwave.com/flags/) is a static page
listing per-country JPG flags as `<img src="./big/XXX.jpg">`. We extract
only the 3-letter codes from those filenames — the JPG assets themselves
are not downloaded or redistributed (spec §4.1: the directory has no
licence statement and is treated as an index, not an asset library).

The page has not been updated since 2011; treat the output as a frozen
historical artefact.

Outputs:
  sources/sailwave-flags-listing.html  — raw HTML as fetched
  sources/sailwave-flags.json          — sorted list of 3-letter codes
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
HTML_PATH = REPO_ROOT / "sources" / "sailwave-flags-listing.html"
JSON_PATH = REPO_ROOT / "sources" / "sailwave-flags.json"

SAILWAVE_URL = "https://www.sailwave.com/flags/"
USER_AGENT = (
    "national-letters/0.5 "
    "(https://github.com/sailscoring/national-letters; markbmc@gmail.com)"
)

# Match <img src="./big/XXX.jpg"> regardless of attribute order/quotes.
FILENAME_RE = re.compile(r'(?:\./)?big/([A-Z]{3})\.jpg', re.IGNORECASE)


def main() -> int:
    print(f"fetching {SAILWAVE_URL} …", file=sys.stderr)
    r = requests.get(SAILWAVE_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    html = r.text
    HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    HTML_PATH.write_text(html)

    codes = sorted({m.group(1).upper() for m in FILENAME_RE.finditer(html)})
    if not codes:
        print(
            "error: extracted 0 codes — page structure may have changed",
            file=sys.stderr,
        )
        return 1

    timestamp = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    payload = {
        "source": "sailwave",
        "retrievedAt": timestamp,
        "sourceUrl": SAILWAVE_URL,
        "note": (
            "Sailwave's flag directory has not been updated since 2011. "
            "Treat as a frozen historical artefact. Only the filenames "
            "(codes) are extracted; JPG assets are not redistributed."
        ),
        "count": len(codes),
        "codes": codes,
    }
    JSON_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(codes)} codes to {JSON_PATH.relative_to(REPO_ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
