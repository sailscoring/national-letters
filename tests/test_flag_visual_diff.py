"""Cover the report the monthly rebuild PR is reviewed from (spec §11.1).

The rendering and comparison need ImageMagick, so these tests exercise
the report formatting instead — that is where a wrong summary would
mislead a reviewer into merging an artwork regression.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "flag_visual_diff", REPO_ROOT / "scripts" / "flag_visual_diff.py"
    )
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves the defining module through sys.modules, so an
    # importlib-loaded module has to be registered before it is executed.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


fvd = _load()


def test_byte_only_changes_are_reported_as_no_visual_change() -> None:
    results = [
        fvd.FlagChange(code="OMA", status="modified", rmse=0.0),
        fvd.FlagChange(code="SMR", status="modified", rmse=0.0),
    ]

    report = fvd.format_report(results, 256, "rsvg-convert")

    assert "all render" in report
    assert "changed visually" not in report


def test_visual_change_is_named_with_its_triptych() -> None:
    results = [
        fvd.FlagChange(code="OMA", status="modified", rmse=0.0),
        fvd.FlagChange(code="JER", status="modified", rmse=2.6e-05, triptych="JER.png"),
    ]

    report = fvd.format_report(results, 256, "rsvg-convert")

    assert "**1 changed visually**" in report
    assert "`JER`" in report and "JER.png" in report
    assert "The other 1 render pixel-identically" in report


def test_added_and_removed_flags_are_listed_separately() -> None:
    results = [
        fvd.FlagChange(code="AIN", status="added"),
        fvd.FlagChange(code="OLD", status="removed"),
    ]

    report = fvd.format_report(results, 256, "magick")

    assert "New flags" in report and "`AIN`" in report
    assert "Removed flags" in report and "`OLD`" in report


def test_no_changes_says_so() -> None:
    assert "No flag files changed." in fvd.format_report([], 256, "rsvg-convert")
