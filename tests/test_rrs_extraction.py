"""Pin the RRS extraction against the hand-typed reference rows in spec §6.2.

Naive `pdftotext -layout` extraction on the Appendix G table can misalign
adjacent columns and produce records where a country gets paired with the
wrong code. These tests guard against that regression on whatever PDF the
build is currently using.

Skipped automatically if the extraction output is not present (i.e. the
pipeline hasn't been run yet).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RRS_OUTPUT = REPO_ROOT / "sources" / "rrs-2025-2028-appendix-g.json"

# Hand-typed reference rows from spec §6.2. The names follow RRS spelling
# verbatim; if the RRS itself uses a different form, update this list and
# the spec together.
#
# Note: spec §6.2 lists "Trinidad & Tobago" under code TRI, but the actual
# RRS 2025-2028 PDF uses TTO (the ISO 3166-1 alpha-3 code). The PDF is the
# source of truth; the spec needs a corresponding correction.
REFERENCE_ROWS = {
    "ALG": "Algeria",
    "ARG": "Argentina",
    "PAK": "Pakistan",
    "PAN": "Panama",
    "TTO": "Trinidad & Tobago",
    "UGA": "Uganda",
    "ZIM": "Zimbabwe",
}


@pytest.fixture(scope="module")
def rrs_rows() -> dict[str, str]:
    if not RRS_OUTPUT.is_file():
        pytest.skip(f"{RRS_OUTPUT.relative_to(REPO_ROOT)} not present; run 01_extract_rrs.py")
    payload = json.loads(RRS_OUTPUT.read_text())
    return {row["code"]: row["name"] for row in payload["rows"]}


@pytest.mark.parametrize("code,expected_name", REFERENCE_ROWS.items())
def test_reference_row(rrs_rows: dict[str, str], code: str, expected_name: str) -> None:
    assert code in rrs_rows, f"{code} missing from extraction"
    assert rrs_rows[code] == expected_name, (
        f"{code}: extracted {rrs_rows[code]!r}, expected {expected_name!r}"
    )


def test_all_codes_are_three_letter_upper(rrs_rows: dict[str, str]) -> None:
    bad = [c for c in rrs_rows if not (len(c) == 3 and c.isalpha() and c.isupper())]
    assert not bad, f"non-conforming codes: {bad}"


def test_no_duplicate_codes() -> None:
    if not RRS_OUTPUT.is_file():
        pytest.skip("extraction output not present")
    payload = json.loads(RRS_OUTPUT.read_text())
    codes = [row["code"] for row in payload["rows"]]
    assert len(codes) == len(set(codes)), "duplicate codes in extraction"
