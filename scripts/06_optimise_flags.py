"""Run SVGO across flags/ and restamp sha256 in manifest + codes.json.

Spec §6.7 — conservative config (see svgo.config.mjs): preserve viewBox,
IDs referenced by <use>, and at least 3 decimal precision; strip metadata,
<title>, <desc>, and editor cruft.

Shells out to `npx svgo` once per file (the CLI also supports a directory
mode, but per-file invocation gives us a per-flag exit code and makes it
trivial to know which files actually changed).
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FLAGS_DIR = REPO_ROOT / "flags"
CODES_PATH = REPO_ROOT / "data" / "codes.json"
MANIFEST_PATH = REPO_ROOT / "data" / "flags-manifest.json"
SVGO_CONFIG = REPO_ROOT / "svgo.config.mjs"

WARN_SIZE_BYTES = 20 * 1024


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def optimise(svg_path: Path) -> None:
    subprocess.run(
        [
            "npx",
            "--yes",
            "svgo",
            "--config",
            str(SVGO_CONFIG),
            "--quiet",
            "-i",
            str(svg_path),
            "-o",
            str(svg_path),
        ],
        check=True,
    )


_SVG_OPEN_RE = re.compile(rb"<svg\b([^>]*)>", re.DOTALL)
_VIEWBOX_ATTR_RE = re.compile(rb'\bviewBox\s*=')
_NUMERIC_ATTR_RE = re.compile(rb'\b{name}\s*=\s*["\']([0-9.]+)(?:px)?["\']')


def ensure_viewbox(svg_path: Path) -> bool:
    """Add viewBox="0 0 W H" to the root <svg> if missing.

    Spec §6.7 requires viewBox on every flag so consumers can rewrap the
    inner contents in <symbol> + <use> without distortion. Some Commons
    flags ship with only width/height (e.g. simple tricolours), so we
    synthesise the viewBox from those dimensions.

    Returns True if the file was modified.
    """
    raw = svg_path.read_bytes()
    match = _SVG_OPEN_RE.search(raw)
    if not match:
        return False
    attrs = match.group(1)
    if _VIEWBOX_ATTR_RE.search(attrs):
        return False
    width_match = re.search(_NUMERIC_ATTR_RE.pattern.replace(b"{name}", b"width"), attrs)
    height_match = re.search(_NUMERIC_ATTR_RE.pattern.replace(b"{name}", b"height"), attrs)
    if not (width_match and height_match):
        return False
    width = width_match.group(1).decode()
    height = height_match.group(1).decode()
    viewbox = f' viewBox="0 0 {width} {height}"'.encode()
    new_attrs = attrs + viewbox
    new_open = b"<svg" + new_attrs + b">"
    svg_path.write_bytes(raw[: match.start()] + new_open + raw[match.end() :])
    return True


def main() -> int:
    if not SVGO_CONFIG.is_file():
        print(f"error: {SVGO_CONFIG.relative_to(REPO_ROOT)} missing", file=sys.stderr)
        return 2
    if not MANIFEST_PATH.is_file():
        print(
            f"error: {MANIFEST_PATH.relative_to(REPO_ROOT)} missing; "
            "run scripts/05_fetch_flags.py first",
            file=sys.stderr,
        )
        return 2

    manifest = json.loads(MANIFEST_PATH.read_text())
    codes_payload = json.loads(CODES_PATH.read_text())
    flag_index = {r["code"]: r for r in codes_payload["codes"]}

    changed = 0
    warnings: list[str] = []
    for entry in sorted(manifest, key=lambda e: e["code"]):
        code = entry["code"]
        svg_path = FLAGS_DIR / f"{code}.svg"
        if not svg_path.is_file():
            print(f"  {code}: missing (skipped)", file=sys.stderr)
            continue

        before = svg_path.read_bytes()
        optimise(svg_path)
        ensure_viewbox(svg_path)
        after = svg_path.read_bytes()

        new_sha = _sha256(after)
        if new_sha != entry["sha256"]:
            entry["sha256"] = new_sha
            if code in flag_index:
                flag_index[code]["flag"]["sha256"] = new_sha
            changed += 1
            reduction = (1 - len(after) / max(len(before), 1)) * 100
            print(
                f"  {code}: {len(before):>6} → {len(after):>6} bytes "
                f"({reduction:5.1f}% smaller)",
                file=sys.stderr,
            )

        if len(after) > WARN_SIZE_BYTES:
            warnings.append(f"{code}: {len(after)} bytes (> {WARN_SIZE_BYTES})")

    MANIFEST_PATH.write_text(
        json.dumps(sorted(manifest, key=lambda e: e["code"]), indent=2, ensure_ascii=False) + "\n"
    )
    CODES_PATH.write_text(json.dumps(codes_payload, indent=2, ensure_ascii=False) + "\n")

    print(f"\noptimised {changed}/{len(manifest)} flags", file=sys.stderr)
    if warnings:
        print(
            f"\n{len(warnings)} flag(s) exceed {WARN_SIZE_BYTES} bytes (warning only):",
            file=sys.stderr,
        )
        for w in warnings:
            print(f"  {w}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
