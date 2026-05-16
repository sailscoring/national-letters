"""Validate data/codes.json against the spec (§6.8).

M1 scope: schema shape, code format, uniqueness, category enum, name/names.en
consistency. Flag-related checks and aliases land in later milestones.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CODES_PATH = REPO_ROOT / "data" / "codes.json"

CODE_RE = re.compile(r"^[A-Z]{3}$")
VALID_CATEGORIES = {"rrs", "world-sailing", "extended", "historical"}
VALID_SOURCES = {"rrs", "world-sailing", "sailwave"}


def validate(payload: dict) -> list[str]:
    errors: list[str] = []

    if payload.get("schemaVersion") != "1.0":
        errors.append(f"schemaVersion: expected '1.0', got {payload.get('schemaVersion')!r}")

    codes = payload.get("codes")
    if not isinstance(codes, list):
        errors.append("codes: must be a list")
        return errors

    seen: set[str] = set()
    for i, record in enumerate(codes):
        prefix = f"codes[{i}]"
        code = record.get("code")
        if not isinstance(code, str) or not CODE_RE.match(code):
            errors.append(f"{prefix}.code: {code!r} does not match ^[A-Z]{{3}}$")
            continue
        if code in seen:
            errors.append(f"{prefix}.code: duplicate code {code!r}")
        seen.add(code)

        name = record.get("name")
        names = record.get("names")
        if not isinstance(name, str) or not name:
            errors.append(f"{prefix}.name: missing or empty")
        if not isinstance(names, dict) or not names.get("en"):
            errors.append(f"{prefix}.names.en: missing or empty")
        elif name != names["en"]:
            errors.append(
                f"{prefix}: name {name!r} != names.en {names['en']!r}"
            )

        category = record.get("category")
        if category not in VALID_CATEGORIES:
            errors.append(
                f"{prefix}.category: {category!r} not in {sorted(VALID_CATEGORIES)}"
            )

        present_in = record.get("presentIn")
        if not isinstance(present_in, list) or not present_in:
            errors.append(f"{prefix}.presentIn: must be a non-empty list")
        else:
            bad = [s for s in present_in if s not in VALID_SOURCES]
            if bad:
                errors.append(
                    f"{prefix}.presentIn: unknown source(s) {bad!r}"
                )

    return errors


def main() -> int:
    if not CODES_PATH.is_file():
        print(f"error: {CODES_PATH.relative_to(REPO_ROOT)} not found", file=sys.stderr)
        return 2

    payload = json.loads(CODES_PATH.read_text())
    errors = validate(payload)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        print(f"\nvalidation failed: {len(errors)} error(s)", file=sys.stderr)
        return 1

    print(f"ok: {len(payload['codes'])} codes validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
