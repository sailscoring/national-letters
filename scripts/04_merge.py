"""Merge source extractions into data/codes.json.

M1 scope: RRS only. World Sailing, Sailwave, aliases, ISO mapping, and flag
fields are added in later milestones.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RRS_INPUT = REPO_ROOT / "sources" / "rrs-2025-2028-appendix-g.json"
OUTPUT_PATH = REPO_ROOT / "data" / "codes.json"

SCHEMA_VERSION = "1.0"


def main() -> int:
    if not RRS_INPUT.is_file():
        print(
            f"error: {RRS_INPUT.relative_to(REPO_ROOT)} not found; "
            "run scripts/01_extract_rrs.py first",
            file=sys.stderr,
        )
        return 2

    rrs = json.loads(RRS_INPUT.read_text())
    codes = [
        {
            "code": row["code"],
            "name": row["name"],
            "category": "rrs",
            "presentIn": ["rrs"],
            "names": {"en": row["name"]},
        }
        for row in rrs["rows"]
    ]
    codes.sort(key=lambda r: r["code"])

    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "sources": {
            "rrs": {"edition": rrs["edition"]},
        },
        "codes": codes,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(codes)} codes to {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
