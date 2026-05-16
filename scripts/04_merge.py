"""Merge source extractions into data/codes.json.

M5 scope: RRS + World Sailing + Sailwave. Per spec §5.4, Sailwave-only
codes either:
  - get a category=extended record if curated in sources/extended-names.yaml
  - get a category=historical record if curated likewise
  - go to data/unresolved.json (with reason) otherwise

Aliases (§5.5), ISO mapping (§6.5), and Wikidata flag fallback remain
later milestones. Flag fields are stamped in by scripts/05_fetch_flags.py.

Per spec §5.3, name precedence is RRS first, then World Sailing.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RRS_INPUT = REPO_ROOT / "sources" / "rrs-2025-2028-appendix-g.json"
WS_INPUT = REPO_ROOT / "sources" / "world-sailing-members.json"
SW_INPUT = REPO_ROOT / "sources" / "sailwave-flags.json"
EXT_NAMES_INPUT = REPO_ROOT / "sources" / "extended-names.yaml"
MANIFEST_PATH = REPO_ROOT / "data" / "flags-manifest.json"
OUTPUT_PATH = REPO_ROOT / "data" / "codes.json"
UNRESOLVED_PATH = REPO_ROOT / "data" / "unresolved.json"

SCHEMA_VERSION = "1.0"


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text()) or {}


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

    sw: dict | None = None
    sw_codes: set[str] = set()
    if SW_INPUT.is_file():
        sw = json.loads(SW_INPUT.read_text())
        sw_codes = set(sw["codes"])

    extended_curation = _load_yaml(EXT_NAMES_INPUT)
    extended_map: dict[str, dict] = extended_curation.get("extended", {}) or {}
    historical_map: dict[str, dict] = extended_curation.get("historical", {}) or {}
    explicit_unresolved: dict[str, dict] = extended_curation.get("unresolved", {}) or {}
    curated = set(extended_map) | set(historical_map) | set(explicit_unresolved)

    all_codes = set(rrs_by_code) | set(ws_by_code) | set(extended_map) | set(historical_map)
    codes: list[dict] = []
    unresolved: list[dict] = []

    for code in sorted(all_codes):
        in_rrs = code in rrs_by_code
        in_ws = code in ws_by_code
        in_sw = code in sw_codes
        in_ext = code in extended_map
        in_hist = code in historical_map

        if in_rrs:
            category = "rrs"
            name = rrs_by_code[code]
        elif in_ws:
            category = "world-sailing"
            name = ws_by_code[code]["name"]
        elif in_hist:
            category = "historical"
            name = historical_map[code]["name"]
        elif in_ext:
            category = "extended"
            name = extended_map[code]["name"]
        else:
            # Should not happen — all_codes is built from these sources.
            continue

        present_in: list[str] = []
        if in_rrs:
            present_in.append("rrs")
        if in_ws:
            present_in.append("world-sailing")
        if in_sw:
            present_in.append("sailwave")

        codes.append(
            {
                "code": code,
                "name": name,
                "category": category,
                "presentIn": present_in,
                "names": {"en": name},
            }
        )

    # Sailwave codes not in any other source AND not curated go to
    # unresolved.json with a "needs research" reason. Explicitly-curated
    # unresolved entries carry their own reason.
    sw_remaining = (
        sw_codes
        - set(rrs_by_code)
        - set(ws_by_code)
        - set(extended_map)
        - set(historical_map)
    )
    for code in sorted(sw_remaining):
        if code in explicit_unresolved:
            entry = explicit_unresolved[code]
            unresolved.append(
                {
                    "code": code,
                    "reason": entry.get("reason", "explicitly unresolved"),
                    "note": entry.get("note"),
                    "source": "sailwave",
                }
            )
        else:
            unresolved.append(
                {
                    "code": code,
                    "reason": "no defensible English name sourced yet — needs research",
                    "source": "sailwave",
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
    if sw is not None:
        sources["sailwave"] = {
            "retrievedAt": sw["retrievedAt"],
            "sourceUrl": sw.get("sourceUrl"),
        }

    timestamp = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": timestamp,
        "sources": sources,
        "codes": codes,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(codes)} codes to {OUTPUT_PATH.relative_to(REPO_ROOT)}")

    unresolved_payload = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": timestamp,
        "note": (
            "Codes seen in source data but excluded from codes.json (spec §5.4). "
            "Entries with reason 'needs research' are candidates for future promotion."
        ),
        "count": len(unresolved),
        "codes": sorted(unresolved, key=lambda u: u["code"]),
    }
    UNRESOLVED_PATH.write_text(json.dumps(unresolved_payload, indent=2, ensure_ascii=False) + "\n")
    print(
        f"wrote {len(unresolved)} unresolved codes to {UNRESOLVED_PATH.relative_to(REPO_ROOT)}"
    )

    if curated - all_codes - set(explicit_unresolved):
        unused = sorted(curated - all_codes - set(explicit_unresolved))
        print(
            f"warning: {len(unused)} curated extended/historical code(s) "
            f"never appeared in any source: {unused}",
            file=sys.stderr,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
