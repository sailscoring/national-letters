"""Merge source extractions into data/codes.json.

M4 scope: RRS + World Sailing. Sailwave/extended/historical categories,
aliases, ISO mapping, and Wikidata flag fallback are added in later
milestones. Flag fields are stamped in by scripts/05_fetch_flags.py.

Per spec §5.3, name precedence is RRS first, then World Sailing.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RRS_INPUT = REPO_ROOT / "sources" / "rrs-2025-2028-appendix-g.json"
WS_INPUT = REPO_ROOT / "sources" / "world-sailing-members.json"
MANIFEST_PATH = REPO_ROOT / "data" / "flags-manifest.json"
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
    rrs_by_code = {row["code"]: row["name"] for row in rrs["rows"]}

    ws: dict | None = None
    ws_by_code: dict[str, dict] = {}
    if WS_INPUT.is_file():
        ws = json.loads(WS_INPUT.read_text())
        ws_by_code = {m["code"]: m for m in ws["members"]}

    all_codes = sorted(set(rrs_by_code) | set(ws_by_code))
    codes: list[dict] = []
    for code in all_codes:
        in_rrs = code in rrs_by_code
        in_ws = code in ws_by_code

        # Name precedence: RRS first (§5.3), then WS.
        name = rrs_by_code[code] if in_rrs else ws_by_code[code]["name"]
        present_in = []
        if in_rrs:
            present_in.append("rrs")
        if in_ws:
            present_in.append("world-sailing")
        category = "rrs" if in_rrs else "world-sailing"

        codes.append(
            {
                "code": code,
                "name": name,
                "category": category,
                "presentIn": present_in,
                "names": {"en": name},
            }
        )

    # Preserve flag.file + flag.sha256 from a prior fetch run so the
    # merge step stays composable: run merge -> fetch_flags -> merge.
    if MANIFEST_PATH.is_file():
        flag_index = {e["code"]: e for e in json.loads(MANIFEST_PATH.read_text())}
        for record in codes:
            entry = flag_index.get(record["code"])
            if entry is not None:
                record["flag"] = {
                    "file": f"flags/{record['code']}.svg",
                    "sha256": entry["sha256"],
                }

    sources: dict[str, dict] = {"rrs": {"edition": rrs["edition"]}}
    if ws is not None:
        sources["worldSailing"] = {
            "retrievedAt": ws["retrievedAt"],
            "sourceUrl": ws.get("sourceUrl"),
        }

    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "sources": sources,
        "codes": codes,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(codes)} codes to {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
