"""Report which flag SVGs changed *visually*, not merely in bytes.

Not a pipeline stage — a review aid for the monthly rebuild PR (§11).

The flags are single-line SVGs, so a textual diff says nothing a reviewer
can act on, and a byte change is a poor proxy for an artwork change: an
SVGO release can rewrite path data with no visible effect, or drop
geometry that does render. Both look identical in `git diff`.

So render each changed flag from the git ref and from the working tree
with the same renderer in the same run, and compare pixels. Anything
non-zero is a real difference: same inputs, same renderer, no
antialiasing noise to tune around.

Needs ImageMagick (for `compare`) — either 7, where the tools are
subcommands of `magick`, or 6, where they are standalone binaries, as
shipped by Ubuntu's `imagemagick` package. Prefers `rsvg-convert` for
rendering, its SVG support being more faithful than ImageMagick's own;
falls back to ImageMagick when librsvg isn't installed.

Usage:
  python scripts/flag_visual_diff.py [--ref HEAD] [--out-dir .flag-diff]
                                     [--report .flag-diff/report.md]

Writes a markdown summary to --report, and an `old | new | diff`
triptych PNG per visually-changed flag into --out-dir. Exit status is 0
whether or not anything changed; this reports, it does not gate.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FLAGS_DIR = REPO_ROOT / "flags"

# Wide enough that fine detail (crest dots, thin charges) survives the
# raster, small enough that ~250 render pairs stay quick.
DEFAULT_WIDTH = 256

# `magick compare -metric RMSE` prints "1.73061 (2.64075e-05)" — the
# absolute value, then the same figure normalised to 0..1. The normalised
# one is comparable across images of different sizes.
_RMSE_RE = re.compile(r"\(([0-9.eE+-]+)\)")


@dataclass(frozen=True)
class FlagChange:
    code: str
    status: str  # "modified" | "added" | "removed"
    rmse: float | None = None  # None when there is nothing to compare
    triptych: str | None = None


def _im(tool: str) -> list[str]:
    """Command prefix for an ImageMagick tool across major versions.

    ImageMagick 7 exposes them as `magick compare`; 6 — what Ubuntu's
    `imagemagick` package installs — as bare `compare` / `convert`.
    """
    if shutil.which("magick"):
        return ["magick"] if tool == "convert" else ["magick", tool]
    return [tool]


def imagemagick_available() -> bool:
    if shutil.which("magick"):
        return True
    return bool(shutil.which("compare") and shutil.which("convert"))


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout


def changed_flags(ref: str) -> list[tuple[str, str]]:
    """Return (code, status) for every flag differing from `ref`."""
    changes: list[tuple[str, str]] = []
    name_status = _git("diff", "--name-status", ref, "--", "flags/")
    for line in name_status.splitlines():
        if not line.strip():
            continue
        status, _, path = line.partition("\t")
        code = Path(path.strip()).stem
        changes.append((code, {"A": "added", "D": "removed"}.get(status[0], "modified")))

    untracked = _git("ls-files", "--others", "--exclude-standard", "flags/")
    for path in untracked.splitlines():
        if path.strip().endswith(".svg"):
            changes.append((Path(path.strip()).stem, "added"))

    return sorted(set(changes))


def _render(svg: Path, png: Path, width: int, renderer: str) -> bool:
    if renderer == "rsvg-convert":
        cmd = ["rsvg-convert", "-w", str(width), "-o", str(png), str(svg)]
    else:
        cmd = [
            *_im("convert"),
            "-background",
            "none",
            "-density",
            "300",
            str(svg),
            "-resize",
            f"{width}x",
            str(png),
        ]
    return subprocess.run(cmd, capture_output=True).returncode == 0 and png.is_file()


def _rmse(old_png: Path, new_png: Path, diff_png: Path) -> float:
    """Normalised 0..1 difference; 1.0 if the images can't be compared."""
    proc = subprocess.run(
        [*_im("compare"), "-metric", "RMSE", str(old_png), str(new_png), str(diff_png)],
        capture_output=True,
        text=True,
    )
    matched = _RMSE_RE.search(proc.stderr)
    if not matched:
        # Differing dimensions and other hard failures land here. Treat as
        # "definitely changed" rather than silently passing.
        return 1.0
    return float(matched.group(1))


def compare_flags(ref: str, out_dir: Path, width: int, renderer: str) -> list[FlagChange]:
    results: list[FlagChange] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    scratch = out_dir / ".scratch"
    scratch.mkdir(exist_ok=True)

    for code, status in changed_flags(ref):
        if status != "modified":
            results.append(FlagChange(code=code, status=status))
            continue

        before = scratch / f"{code}.before.svg"
        try:
            before.write_bytes(
                subprocess.check_output(
                    ["git", "show", f"{ref}:flags/{code}.svg"], cwd=REPO_ROOT
                )
            )
        except subprocess.CalledProcessError:
            results.append(FlagChange(code=code, status="added"))
            continue

        old_png = scratch / f"{code}.old.png"
        new_png = scratch / f"{code}.new.png"
        rendered = _render(before, old_png, width, renderer) and _render(
            FLAGS_DIR / f"{code}.svg", new_png, width, renderer
        )
        if not rendered:
            # A flag that will not render is a finding in its own right.
            results.append(FlagChange(code=code, status="modified", rmse=1.0))
            continue

        diff_png = scratch / f"{code}.diff.png"
        rmse = _rmse(old_png, new_png, diff_png)
        triptych = None
        if rmse:
            triptych = f"{code}.png"
            subprocess.run(
                [
                    *_im("convert"),
                    str(old_png),
                    str(new_png),
                    str(diff_png),
                    "+append",
                    str(out_dir / triptych),
                ],
                capture_output=True,
            )
        results.append(
            FlagChange(code=code, status="modified", rmse=rmse, triptych=triptych)
        )

    shutil.rmtree(scratch, ignore_errors=True)
    return results


def format_report(results: list[FlagChange], width: int, renderer: str) -> str:
    modified = [r for r in results if r.status == "modified"]
    visual = sorted(
        (r for r in modified if r.rmse), key=lambda r: r.rmse or 0, reverse=True
    )
    added = [r.code for r in results if r.status == "added"]
    removed = [r.code for r in results if r.status == "removed"]

    lines = ["### Flag artwork check", ""]
    if not results:
        lines.append("No flag files changed.")
        return "\n".join(lines) + "\n"

    if modified:
        if visual:
            lines.append(
                f"{len(modified)} flag file(s) changed bytes; "
                f"**{len(visual)} changed visually** — inspect these:"
            )
            lines += ["", "| flag | RMSE | triptych (old \\| new \\| diff) |", "|---|---|---|"]
            for r in visual:
                art = f"`{r.triptych}`" if r.triptych else "—"
                lines.append(f"| `{r.code}` | {r.rmse:.2e} | {art} |")
            lines.append("")
            identical = len(modified) - len(visual)
            if identical:
                lines.append(f"The other {identical} render pixel-identically (byte changes only).")
        else:
            lines.append(
                f"{len(modified)} flag file(s) changed bytes, and **all render "
                f"pixel-identically** — byte changes only."
            )
        lines.append("")

    if added:
        listed = ", ".join(f"`{c}`" for c in added)
        lines.append(f"New flags (no prior version to compare): {listed}")
        lines.append("")
    if removed:
        lines.append(f"Removed flags: {', '.join(f'`{c}`' for c in removed)}")
        lines.append("")

    lines.append(
        f"<sub>Rendered at {width}px wide with `{renderer}`; RMSE is normalised 0..1. "
        f"A visual change can also mean the Commons source was replaced upstream — "
        f"check `flags-manifest.json` for a licence or attribution change too.</sub>"
    )
    return "\n".join(lines) + "\n"


def pick_renderer() -> str | None:
    if shutil.which("rsvg-convert"):
        return "rsvg-convert"
    if imagemagick_available():
        return "imagemagick"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD", help="git ref to compare against")
    parser.add_argument("--out-dir", default=".flag-diff", type=Path)
    parser.add_argument("--report", default=None, type=Path)
    parser.add_argument("--width", default=DEFAULT_WIDTH, type=int)
    args = parser.parse_args()

    if not imagemagick_available():
        print(
            "error: ImageMagick is required for image comparison "
            "(`magick`, or `compare` + `convert` on ImageMagick 6)",
            file=sys.stderr,
        )
        return 2
    renderer = pick_renderer()
    if renderer is None:
        print("error: no SVG renderer found (rsvg-convert or magick)", file=sys.stderr)
        return 2

    results = compare_flags(args.ref, args.out_dir, args.width, renderer)
    report = format_report(results, args.width, renderer)

    report_path = args.report or (args.out_dir / "report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
