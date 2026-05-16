"""Merge source extractions into data/codes.json.

M6 scope: full merge — RRS + World Sailing + Sailwave + aliases +
ISO 3166 mapping. Wikidata flag fallback runs in 05_fetch_flags.py.

Per spec §5.3, name precedence is RRS first, then World Sailing.
Per spec §6.5, ISO 3166 alpha-2/alpha-3 fields are set ONLY when the
code's name resolves to a single ISO country AND the Commons title we
resolved matches the canonical "File:Flag of {ISO short name}.svg".
The rule is mechanical — no per-code editorial judgement.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pycountry
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RRS_INPUT = REPO_ROOT / "sources" / "rrs-2025-2028-appendix-g.json"
WS_INPUT = REPO_ROOT / "sources" / "world-sailing-members.json"
SW_INPUT = REPO_ROOT / "sources" / "sailwave-flags.json"
EXT_NAMES_INPUT = REPO_ROOT / "sources" / "extended-names.yaml"
ALIASES_INPUT = REPO_ROOT / "sources" / "aliases.yaml"
MANIFEST_PATH = REPO_ROOT / "data" / "flags-manifest.json"
OUTPUT_PATH = REPO_ROOT / "data" / "codes.json"
UNRESOLVED_PATH = REPO_ROOT / "data" / "unresolved.json"
ALIASES_PATH = REPO_ROOT / "data" / "aliases.json"

SCHEMA_VERSION = "1.0"


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _iso_lookup(name: str, code: str | None = None) -> pycountry.db.Country | None:
    """Try to resolve a code to a single ISO 3166 country.

    Tries the code first (when our 3-letter code is itself a valid ISO
    alpha-3 — e.g. GBR, IRL, USA — that's a direct correspondence), then
    falls back to exact name lookup against name/official_name/common_name.
    The flag-equivalence guard in _apply_iso_mapping still prevents false
    positives.
    """
    if code:
        try:
            return pycountry.countries.lookup(code)
        except LookupError:
            pass
    try:
        return pycountry.countries.lookup(name)
    except LookupError:
        return None


def _canonical_iso_flag_titles(country: pycountry.db.Country) -> set[str]:
    """All "File:Flag of …" titles that mean "the canonical flag of <country>".

    Commons names tend to follow "Flag of X" or "Flag of the X". We accept
    either form, against the country's primary, common, and official names.
    """
    candidates: set[str] = set()
    for attr in ("name", "common_name", "official_name"):
        n = getattr(country, attr, None)
        if not n:
            continue
        candidates.add(f"File:Flag of {n}.svg")
        candidates.add(f"File:Flag of the {n}.svg")
    return candidates


def _apply_iso_mapping(records: list[dict], manifest_by_code: dict[str, dict]) -> None:
    """Per §6.5: stamp iso3166Alpha2/Alpha3 when name + flag match."""
    for record in records:
        country = _iso_lookup(record["name"], record["code"])
        if country is None:
            continue
        entry = manifest_by_code.get(record["code"])
        if entry is None:
            continue
        commons_title = entry.get("commonsTitle")
        if commons_title in _canonical_iso_flag_titles(country):
            record["iso3166Alpha2"] = country.alpha_2
            record["iso3166Alpha3"] = country.alpha_3


def _build_aliases(known_codes: set[str]) -> tuple[dict[str, dict], list[str]]:
    """Load sources/aliases.yaml and drop entries whose canonical is unknown.

    Returns (alias_map, warnings).
    """
    warnings: list[str] = []
    raw = _load_yaml(ALIASES_INPUT)
    out: dict[str, dict] = {}
    for alias, entry in (raw.get("aliases") or {}).items():
        if not isinstance(entry, dict):
            warnings.append(f"aliases[{alias}]: not a mapping; skipping")
            continue
        canonical = entry.get("canonical")
        if not canonical:
            warnings.append(f"aliases[{alias}]: missing 'canonical'; skipping")
            continue
        if canonical not in known_codes:
            warnings.append(
                f"aliases[{alias}]: canonical {canonical!r} not in codes.json; skipping"
            )
            continue
        if not entry.get("source"):
            warnings.append(f"aliases[{alias}]: missing 'source' citation; skipping")
            continue
        out[alias] = {
            "canonical": canonical,
            "note": entry.get("note", ""),
            "source": entry["source"],
        }
    return out, warnings


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
    manifest_by_code: dict[str, dict] = {}
    if MANIFEST_PATH.is_file():
        manifest_by_code = {e["code"]: e for e in json.loads(MANIFEST_PATH.read_text())}
        for record in codes:
            entry = manifest_by_code.get(record["code"])
            if entry is not None:
                record["flag"] = {
                    "file": f"flags/{record['code']}.svg",
                    "sha256": entry["sha256"],
                }

    # §6.5 ISO 3166 mapping. Requires the flag manifest (commonsTitle).
    if manifest_by_code:
        _apply_iso_mapping(codes, manifest_by_code)

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

    # Aliases (§5.5). Each entry needs a canonical code that exists in
    # codes.json and a real-world source citation.
    aliases, alias_warnings = _build_aliases({r["code"] for r in codes})
    for w in alias_warnings:
        print(f"warning: {w}", file=sys.stderr)
    aliases_payload = {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": timestamp,
        "aliases": dict(sorted(aliases.items())),
    }
    ALIASES_PATH.write_text(json.dumps(aliases_payload, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(aliases)} aliases to {ALIASES_PATH.relative_to(REPO_ROOT)}")

    iso_count = sum(1 for r in codes if "iso3166Alpha3" in r)
    print(f"ISO 3166 mapping: {iso_count}/{len(codes)} codes have ISO fields set")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
