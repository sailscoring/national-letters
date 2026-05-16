"""Validate data/codes.json against the spec (§6.8).

M3 scope: schema shape, code format, uniqueness, category enum,
name/names.en consistency, flag presence + sha256 + manifest licence,
and §6.7 SVG structural constraints (single root <svg> with viewBox;
no <image>, <script>, external xlink:href, or external fonts).
Aliases land in M6.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CODES_PATH = REPO_ROOT / "data" / "codes.json"
MANIFEST_PATH = REPO_ROOT / "data" / "flags-manifest.json"
ALIASES_PATH = REPO_ROOT / "data" / "aliases.json"

CODE_RE = re.compile(r"^[A-Z]{3}$")
VALID_CATEGORIES = {"rrs", "world-sailing", "extended", "historical"}
VALID_SOURCES = {"rrs", "world-sailing", "sailwave"}

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
# An xlink:href value pointing outside the document (i.e. not an in-doc
# fragment reference like "#flag-IRL") makes the SVG non-self-contained.
REMOTE_HREF_RE = re.compile(r"^(?:https?:)?//|^data:|^file:|^ftp:", re.IGNORECASE)


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

    errors.extend(_validate_svg_structure(file_rel, path))
    return errors


def _validate_svg_structure(rel: str, path: Path) -> list[str]:
    """Enforce spec §6.7: SVG must be safely inlineable as a <symbol>."""
    errors: list[str] = []
    try:
        tree = ET.parse(path)
    except ET.ParseError as e:
        errors.append(f"flags/{rel}: malformed XML ({e})")
        return errors

    root = tree.getroot()
    if root.tag != f"{{{SVG_NS}}}svg":
        errors.append(f"flags/{rel}: root element is {root.tag!r}, expected <svg>")
        return errors
    if not root.get("viewBox"):
        errors.append(f"flags/{rel}: root <svg> missing viewBox")

    for el in root.iter():
        tag = el.tag
        if tag == f"{{{SVG_NS}}}image":
            errors.append(f"flags/{rel}: contains <image> element")
        elif tag == f"{{{SVG_NS}}}script":
            errors.append(f"flags/{rel}: contains <script> element")
        elif tag == f"{{{SVG_NS}}}font" or tag == f"{{{SVG_NS}}}font-face":
            errors.append(f"flags/{rel}: contains <{tag.split('}')[-1]}> (external font)")

        href = el.get(f"{{{XLINK_NS}}}href") or el.get("href")
        if href and REMOTE_HREF_RE.match(href):
            errors.append(f"flags/{rel}: external reference {href!r}")

        style = el.get("style") or ""
        if "@import" in style or "url(http" in style:
            errors.append(f"flags/{rel}: external CSS reference in style attribute")

    return errors


def _validate_aliases(payload: dict, all_codes: set[str]) -> list[str]:
    errors: list[str] = []
    aliases = payload.get("aliases", {})
    if not isinstance(aliases, dict):
        errors.append("aliases.json: 'aliases' must be a mapping")
        return errors
    for alias, entry in aliases.items():
        prefix = f"aliases[{alias!r}]"
        if not CODE_RE.match(alias):
            errors.append(f"{prefix}: alias does not match ^[A-Z]{{3}}$")
        if not isinstance(entry, dict):
            errors.append(f"{prefix}: entry must be a mapping")
            continue
        canonical = entry.get("canonical")
        if not canonical:
            errors.append(f"{prefix}.canonical: missing")
        elif canonical not in all_codes:
            errors.append(f"{prefix}.canonical: {canonical!r} not in codes.json")
        if not entry.get("source"):
            errors.append(f"{prefix}.source: missing (citation required per §5.5)")
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

    if ALIASES_PATH.is_file():
        aliases_payload = json.loads(ALIASES_PATH.read_text())
        all_codes = {r["code"] for r in payload.get("codes", [])}
        errors.extend(_validate_aliases(aliases_payload, all_codes))
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        print(f"\nvalidation failed: {len(errors)} error(s)", file=sys.stderr)
        return 1

    print(f"ok: {len(payload['codes'])} codes validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
