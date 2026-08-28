"""Guard the per-flag id namespacing that spec §9 embedding depends on.

Consumers inline many flags into one document as `<symbol>`s. Commons
files ship generic ids (`a`, `b`, `Layer_1`), so without the prefixIds
pass in svgo.config.mjs a `url(#a)` in one flag resolves against another
flag's definition once both are on the page.

The repo-wide assertion is skipped if the flags haven't been built yet.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CODES_PATH = REPO_ROOT / "data" / "codes.json"


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "validate07", REPO_ROOT / "scripts" / "07_validate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = _load_validator()


def _write_flag(path: Path, body: str) -> None:
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 1">'
        f"{body}</svg>",
        encoding="utf-8",
    )


def _record(code: str, path: Path) -> dict:
    return {"code": code, "flag": {"file": str(path)}}


def test_shared_id_between_two_flags_is_an_error(tmp_path: Path) -> None:
    one, two = tmp_path / "AAA.svg", tmp_path / "BBB.svg"
    _write_flag(one, '<clipPath id="a"><path d="M0 0h2v1H0z"/></clipPath>')
    _write_flag(two, '<clipPath id="a"><path d="M0 0h2v1H0z"/></clipPath>')

    errors = validator._validate_flag_id_uniqueness(
        [_record("AAA", one), _record("BBB", two)]
    )

    assert len(errors) == 1
    assert "'a'" in errors[0]
    assert "AAA" in errors[0] and "BBB" in errors[0]


def test_prefixed_ids_do_not_collide(tmp_path: Path) -> None:
    one, two = tmp_path / "AAA.svg", tmp_path / "BBB.svg"
    _write_flag(one, '<clipPath id="AAA-a"><path d="M0 0h2v1H0z"/></clipPath>')
    _write_flag(two, '<clipPath id="BBB-a"><path d="M0 0h2v1H0z"/></clipPath>')

    assert (
        validator._validate_flag_id_uniqueness(
            [_record("AAA", one), _record("BBB", two)]
        )
        == []
    )


def test_repeated_id_within_one_flag_is_fine(tmp_path: Path) -> None:
    """Duplicate ids inside a single file are that file's business."""
    one = tmp_path / "AAA.svg"
    _write_flag(one, '<g id="AAA-a"/><g id="AAA-a"/>')

    assert validator._validate_flag_id_uniqueness([_record("AAA", one)]) == []


@pytest.mark.skipif(not CODES_PATH.is_file(), reason="pipeline not run yet")
def test_built_flags_have_no_cross_file_id_collisions() -> None:
    codes = json.loads(CODES_PATH.read_text())["codes"]
    assert validator._validate_flag_id_uniqueness(codes) == []
