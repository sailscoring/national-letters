# national-letters

A versioned, public-domain dataset of the three-letter national codes used in
sail racing, with English country names and flag images. Built to be consumed
by sail-racing scoring software for entry-list dropdowns and results displays.

**Status:** in development. See [`national-letters-spec.md`](./national-letters-spec.md)
for the full design specification.

## Nature of this dataset

This repository consolidates factual reference data that is in the public
domain or otherwise freely reusable. Specifically:

- **Three-letter codes** (e.g. `IRL`, `GBR`, `ARG`) are short factual
  identifiers. Lists of such codes are not copyrightable subject matter — they
  are facts about a coding system, comparable to ISO country codes or airport
  codes.
- **English country names** are factual common nouns drawn from authoritative
  references (the World Sailing membership list and English Wikipedia, both of
  which permit factual reuse).
- **Flag images** are sourced from Wikimedia Commons. Each file retains and
  records its original Commons licence in `data/flags-manifest.json`. Most
  national flags are public-domain or freely licensed; any file with attribution
  or share-alike terms is flagged in the manifest so downstream consumers can
  comply.
- **The RRS Appendix G code list** is extracted as a factual reference table.
  The Racing Rules of Sailing PDF itself is not redistributed; only the
  uncopyrightable list of three-letter codes and the country names they
  identify are reproduced.
- **The Sailwave flag directory** is used only as a *list of filenames*
  (i.e. a list of three-letter codes seen in practice). The JPG image assets
  themselves are neither downloaded nor redistributed.

The dataset published by this repository (`data/*.json`, scripts, sources) is
released under [CC0-1.0](./LICENSE) — i.e. dedicated to the public domain — so
that any sail-racing tool, commercial or open-source, can use it freely.

## Layout

- `data/` — published dataset (`codes.json`, `aliases.json`, `flags-manifest.json`,
  `unresolved.json`)
- `flags/` — per-code SVG flag images
- `sources/` — committed raw inputs used to build the dataset
- `scripts/` — extraction, merge, and validation pipeline

## Consumers

Intended for sail-racing scoring software (entry-list dropdowns, results
displays, HTML exports with inlined flag SVGs). Consume by pinning a tagged
GitHub Release and downloading `codes.json` + `flags.tar.gz` at build time;
see §8 of the spec.

## Licence

- **Dataset** (`data/`, scripts, sources): [CC0-1.0](./LICENSE)
- **Flag images** (`flags/`): each file retains its original Wikimedia Commons
  licence; per-file terms are recorded in `data/flags-manifest.json`. Where a
  flag's licence requires attribution, downstream consumers must surface it.

## Development

Requires Python 3.12+ and [`uv`](https://docs.astral.sh/uv/).

```sh
uv sync
uv run pytest
uv run ruff check
```

### Rebuilding the dataset

The RRS 2025–2028 PDF is not redistributed in this repo. Obtain it from
World Sailing and point the extraction script at it:

```sh
export RRS_PDF_PATH=/path/to/rrs-2025-2028.pdf
uv run python scripts/01_extract_rrs.py        # → sources/rrs-2025-2028-appendix-g.json
uv run python scripts/02_fetch_world_sailing.py # → sources/world-sailing-members.{html,json}
uv run python scripts/03_extract_sailwave.py   # → sources/sailwave-flags.json
uv run python scripts/04_merge.py              # → data/codes.json + data/unresolved.json
uv run python scripts/05_fetch_flags.py        # → flags/*.svg + data/flags-manifest.json
uv run python scripts/06_optimise_flags.py     # SVGO + viewBox synthesis (needs Node + npx)
uv run python scripts/04_merge.py              # re-merge so flag.sha256 reflects optimised files
uv run python scripts/07_validate.py
uv run pytest                                  # pins extraction against reference rows
```

Curation lives in `sources/`:
- `flag-overrides.yaml` — per-code Commons file overrides with citations
- `extended-names.yaml` — English names + classifications for Sailwave-only
  codes (extended / historical / unresolved-with-reason)

The flag-fetch step downloads SVGs from Wikimedia Commons. It is
**resumable** — partially-completed runs leave a valid manifest, and a
re-run skips codes whose local file already matches its recorded sha256.
Codes whose default Commons title (`File:Flag of {names.en}.svg`) does not
resolve are added to `sources/flag-overrides.yaml` with a citation URL.
