"""Validate data/codes.json against the spec (§6.8).

M2 scope: schema shape, code format, uniqueness, category enum,
name/names.en consistency, plus flag presence + sha256 + manifest licence.
Structural SVG constraints land in M3 (post-SVGO); aliases in M6.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CODES_PATH = REPO_ROOT / "data" / "codes.json"
MANIFEST_PATH = REPO_ROOT / "data" / "flags-manifest.json"

CODE_RE = re.compile(r"^[A-Z]{3}$")
VALID_CATEGORIES = {"rrs", "world-sailing", "extended", "historical"}
VALID_SOURCES = {"rrs", "world-sailing", "sailwave"}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def validate(payload: dict, manifest: list[dict] | None) -> list[str]:
    errors: list[str] = []

    if payload.get("schemaVersion") != "1.0":
        errors.append(f"schemaVersion: expected '1.0', got {payload.get('schemaVersion')!r}")

    codes = payload.get("codes")
    if not isinstance(codes, list):
        errors.append("codes: must be a list")
        return errors

    manifest_by_code: dict[str, dict] = {}
    if manifest is not None:
        for entry in manifest:
            code = entry.get("code")
            if isinstance(code, str):
                manifest_by_code[code] = entry

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

        # Flag checks — only enforced when a manifest is present, so M1-era
        # callers running the validator without flags still pass.
        if manifest is not None:
            errors.extend(_validate_flag(prefix, code, record, manifest_by_code))

    return errors


def _validate_flag(
    prefix: str,
    code: str,
    record: dict,
    manifest_by_code: dict[str, dict],
) -> list[str]:
    errors: list[str] = []
    flag = record.get("flag")
    if not isinstance(flag, dict):
        errors.append(f"{prefix}.flag: missing")
        return errors

    file_rel = flag.get("file")
    sha = flag.get("sha256")
    if not isinstance(file_rel, str) or not file_rel:
        errors.append(f"{prefix}.flag.file: missing")
        return errors

    path = REPO_ROOT / file_rel
    if not path.is_file() or path.stat().st_size == 0:
        errors.append(f"{prefix}.flag.file: {file_rel} missing or empty")
        return errors

    actual = _sha256_file(path)
    if sha != actual:
        errors.append(
            f"{prefix}.flag.sha256: stored {sha} != actual {actual}"
        )

    entry = manifest_by_code.get(code)
    if entry is None:
        errors.append(f"{prefix}.flag: no flags-manifest.json entry for {code}")
    else:
        if not entry.get("licence"):
            errors.append(
                f"flags-manifest[{code}].licence: must be non-null"
            )
        if entry.get("sha256") != actual:
            errors.append(
                f"flags-manifest[{code}].sha256: {entry.get('sha256')} != actual {actual}"
            )
    return errors


def main() -> int:
    if not CODES_PATH.is_file():
        print(f"error: {CODES_PATH.relative_to(REPO_ROOT)} not found", file=sys.stderr)
        return 2

    payload = json.loads(CODES_PATH.read_text())
    manifest: list[dict] | None = None
    if MANIFEST_PATH.is_file():
        manifest = json.loads(MANIFEST_PATH.read_text())
    errors = validate(payload, manifest)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        print(f"\nvalidation failed: {len(errors)} error(s)", file=sys.stderr)
        return 1

    print(f"ok: {len(payload['codes'])} codes validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
