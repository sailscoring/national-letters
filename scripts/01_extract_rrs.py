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

# The table renders as 4 columns: (name, code, name, code). Word x0 values
# observed in the 2025-2028 PDF: name1≈102, code1≈255, name2≈329, code2≈475.
# Splitting at the midpoints between adjacent columns gives generous slack.
COL_BOUNDARIES_X = (240.0, 320.0, 460.0)
# Same printed line shares a y-position within ~2pt; rows are ~18pt apart.
ROW_Y_TOLERANCE = 3.0


def _is_code(value: str) -> bool:
    return len(value) == 3 and value.isalpha() and value.isupper()


def _column_of(x0: float) -> int:
    for i, bound in enumerate(COL_BOUNDARIES_X):
        if x0 < bound:
            return i
    return len(COL_BOUNDARIES_X)


def _group_words_into_rows(words: list[dict]) -> list[list[dict]]:
    """Group words by approximate y-position into visual rows."""
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: (w["top"], w["x0"]))
    rows: list[list[dict]] = []
    current: list[dict] = [sorted_words[0]]
    for w in sorted_words[1:]:
        if abs(w["top"] - current[0]["top"]) <= ROW_Y_TOLERANCE:
            current.append(w)
        else:
            rows.append(current)
            current = [w]
    rows.append(current)
    return rows


def _row_to_pairs(row_words: list[dict]) -> list[tuple[str, str]]:
    """Bucket words into the 4 table columns and yield (name, code) pairs."""
    cells: list[list[str]] = [[], [], [], []]
    for w in sorted(row_words, key=lambda w: w["x0"]):
        cells[_column_of(w["x0"])].append(w["text"])

    pairs: list[tuple[str, str]] = []
    for name_idx, code_idx in ((0, 1), (2, 3)):
        name = " ".join(cells[name_idx]).strip()
        code_tokens = cells[code_idx]
        if not name or len(code_tokens) != 1 or not _is_code(code_tokens[0]):
            continue
        pairs.append((name, code_tokens[0]))
    return pairs


def _table_pages(pdf: pdfplumber.PDF) -> list[int]:
    """Return 0-indexed page numbers that hold (part of) the table."""
    pages: list[int] = []
    found_start = False
    for i, page in enumerate(pdf.pages):
        text = page.extract_text() or ""
        lines = [line.strip() for line in text.splitlines()]
        if not found_start:
            if TABLE_START_LINE in lines:
                found_start = True
                pages.append(i)
            continue
        # Stop once we hit the page containing the end marker.
        if any(TABLE_END_MARKER_RE.match(line) for line in lines):
            pages.append(i)
            break
        pages.append(i)
    if not found_start:
        raise RuntimeError(f"could not find '{TABLE_START_LINE}' heading")
    return pages


def extract_rows(pdf_path: Path) -> list[dict[str, str]]:
    """Return a list of {'code', 'name'} dicts in the order they appear.

    Column-aware extraction (spec §6.2): words are bucketed into the 4 table
    columns by x-coordinate, so 3-letter all-caps fragments that happen to
    appear inside a country name (e.g. "Korea, DPR") are correctly treated
    as part of the name rather than as a code.
    """
    rows: list[dict[str, str]] = []
    seen_codes: set[str] = set()

    with pdfplumber.open(pdf_path) as pdf:
        for page_index in _table_pages(pdf):
            page = pdf.pages[page_index]
            # Only consider words that lie below the "Letters" header line.
            # The per-page heading "Appendix G IDENTIFICATION ON SAILS" and
            # the "National authority / Letters" header sit above the data.
            header_bottom = _header_bottom_y(page)
            footer_top = _footer_top_y(page)
            words = [
                w
                for w in page.extract_words()
                if w["top"] > header_bottom and w["top"] < footer_top
            ]
            for row_words in _group_words_into_rows(words):
                for name, code in _row_to_pairs(row_words):
                    if code in seen_codes:
                        continue
                    rows.append({"code": code, "name": name})
                    seen_codes.add(code)

    return rows


def _header_bottom_y(page: pdfplumber.page.Page) -> float:
    """Y-coordinate below the 'National authority / Letters' header row."""
    for w in page.extract_words():
        if w["text"] == "Letters" and w["x0"] > 200:
            return w["bottom"]
    # Fallback: above any data row.
    return 0.0


def _footer_top_y(page: pdfplumber.page.Page) -> float:
    """Y-coordinate above the rule G1.2 line, if present on this page."""
    for w in page.extract_words():
        if w["text"].startswith("G1.2"):
            return w["top"]
    return float("inf")


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
