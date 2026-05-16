"""Extract the National Sail Letters table from RRS Appendix G.

The Racing Rules of Sailing 2025-2028 PDF is published by World Sailing and
not redistributed in this repo. Provide the path via the RRS_PDF_PATH env
var. The script extracts pages 119-121 (Appendix G) using column-aware
table extraction and writes a structured JSON snapshot to:

    sources/rrs-2025-2028-appendix-g.json

The output preserves the source spelling verbatim. Any corrections happen
downstream in the merge step (see spec §6.4) with a cited override.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import pdfplumber

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = REPO_ROOT / "sources" / "rrs-2025-2028-appendix-g.json"

EDITION = "2025-2028"

# The National Sail Letters table sits inside Appendix G. We locate the table
# by content markers rather than by hard-coded page numbers, so the script
# survives editions where pagination shifts. The table starts at the
# "NATIONAL SAIL LETTERS" heading and ends at the next rule ("G1.2").
# The standalone heading that introduces the table. We match it exactly
# (not as a substring) so the matcher does not fire on the table-of-contents
# entry "Up-to-date table of National Sail Letters Appendix G".
TABLE_START_LINE = "NATIONAL SAIL LETTERS"
TABLE_END_MARKER_RE = re.compile(r"^\s*G1\.2\b")
HEADER_LINE_RE = re.compile(r"^National authority\s+Letters", re.IGNORECASE)


def _is_code(value: str) -> bool:
    return len(value) == 3 and value.isalpha() and value.isupper()


def _parse_table_line(line: str) -> list[tuple[str, str]]:
    """Parse one rendered line of the table into (name, code) tuples.

    The PDF renders each row as two side-by-side (country, code) columns,
    e.g. "Algeria ALG Egypt EGY". A row may carry one pair (last row of
    the table) or two. Country names may span multiple whitespace-separated
    tokens, including punctuation ("Trinidad & Tobago", "St Lucia",
    "Macedonia (FYRO)").
    """
    tokens = line.split()
    if not tokens:
        return []

    # Find every position holding a 3-letter uppercase code. Names occupy
    # the spans between code positions (or from the start, for the first).
    code_positions = [i for i, tok in enumerate(tokens) if _is_code(tok)]
    if not code_positions:
        return []

    pairs: list[tuple[str, str]] = []
    prev = 0
    for pos in code_positions:
        name_tokens = tokens[prev:pos]
        if not name_tokens:
            continue
        name = " ".join(name_tokens)
        pairs.append((name, tokens[pos]))
        prev = pos + 1
    return pairs


def extract_rows(pdf_path: Path) -> list[dict[str, str]]:
    """Return a list of {'code', 'name'} dicts in the order they appear.

    Walks every page, enters table-collection mode at the
    "NATIONAL SAIL LETTERS" marker, and stops at the first line matching
    the end marker (rule G1.2).
    """
    rows: list[dict[str, str]] = []
    seen_codes: set[str] = set()
    in_table = False

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                stripped = line.strip()
                if not in_table:
                    if stripped == TABLE_START_LINE:
                        in_table = True
                    continue
                if TABLE_END_MARKER_RE.match(stripped):
                    return rows
                if HEADER_LINE_RE.match(stripped):
                    continue
                # Drop the per-page repeating heading
                if stripped.startswith("Appendix G"):
                    continue
                for name, code in _parse_table_line(stripped):
                    if code in seen_codes:
                        continue
                    rows.append({"code": code, "name": name})
                    seen_codes.add(code)

    if not in_table:
        raise RuntimeError(
            f"could not find '{TABLE_START_LINE}' heading in {pdf_path.name}"
        )
    return rows


def main() -> int:
    pdf_env = os.environ.get("RRS_PDF_PATH")
    if not pdf_env:
        print(
            "error: set RRS_PDF_PATH to the path of the RRS 2025-2028 PDF",
            file=sys.stderr,
        )
        return 2

    pdf_path = Path(pdf_env).expanduser().resolve()
    if not pdf_path.is_file():
        print(f"error: {pdf_path} is not a file", file=sys.stderr)
        return 2

    rows = extract_rows(pdf_path)
    if not rows:
        print("error: no rows extracted from Appendix G", file=sys.stderr)
        return 1

    payload = {
        "source": "rrs",
        "edition": EDITION,
        "extractedAt": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "pdfSha256": _sha256_file(pdf_path),
        "count": len(rows),
        "rows": rows,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} rows to {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


def _sha256_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
