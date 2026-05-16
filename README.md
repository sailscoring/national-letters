# national-letters

A versioned, public-domain dataset of the three-letter national codes used in
sail racing, with English country names and flag images. Built to be consumed
by sail-racing scoring software for entry-list dropdowns and results displays.

See [`national-letters-spec.md`](./national-letters-spec.md) for the full
design specification.

## What's in a release

Each tagged GitHub Release attaches:

- **`codes.json`** — the canonical dataset: every code, its English name,
  category (`rrs` / `world-sailing` / `extended` / `historical`), source
  provenance (`presentIn`), optional `iso3166Alpha2`/`Alpha3` mapping, and
  the path + sha256 of its flag SVG.
- **`flags.tar.gz`** — all per-code SVG flag images, structurally constrained
  to be safely inlineable as `<symbol>` (see [HTML embedding](#html-embedding)).
- **`flags-manifest.json`** — per-flag Commons title, source URL, licence,
  attribution, sha256.
- **`aliases.json`** — non-canonical code variants observed in real-world
  import data, each pointing at a canonical code with a citation.
- **`unresolved.json`** — codes seen in source data but excluded from
  `codes.json`, with reasons. A visible audit ledger.

## Nature of this dataset

This repository consolidates factual reference data that is in the public
domain or otherwise freely reusable:

- **Three-letter codes** (`IRL`, `GBR`, `ARG`) are short factual identifiers.
  Lists of such codes are not copyrightable subject matter — they are facts
  about a coding system, comparable to ISO country codes or airport codes.
- **English country names** are factual common nouns drawn from authoritative
  references (the World Sailing membership list and English Wikipedia, both
  of which permit factual reuse).
- **Flag images** are sourced from Wikimedia Commons. Each file retains and
  records its original Commons licence in `flags-manifest.json`. Most
  national flags are public-domain or freely licensed; any file with
  attribution or share-alike terms is flagged in the manifest so downstream
  consumers can comply.
- **The RRS Appendix G code list** is extracted as a factual reference
  table. The Racing Rules of Sailing PDF itself is not redistributed; only
  the uncopyrightable list of three-letter codes and the country names they
  identify are reproduced.
- **The Sailwave flag directory** is used only as a *list of filenames*
  (a list of three-letter codes seen in practice). The JPG image assets
  themselves are neither downloaded nor redistributed.

The dataset published by this repository (`data/*.json`, scripts, sources)
is released under [CC0-1.0](./LICENSE) — dedicated to the public domain —
so any sail-racing tool, commercial or open-source, can use it freely.

## English-name spelling

`names.en` follows the spelling of the source that *introduced* the row
(spec §5.3):

1. RRS Appendix G spelling, if the code is in RRS
2. World Sailing membership spelling, if it's in WS but not RRS
3. Otherwise, the spelling from the Wikipedia article cited in
   `sources/extended-names.yaml`

In practice this yields British-English spellings with diacritics
("Czechia", "Côte d'Ivoire") because RRS and WS are British-spelling
publications. The schema explicitly does not commit to `en-GB` vs `en-US`.
Regional variants (`en-GB`, `en-US`) may be added in future patch releases
without schema changes; v1 ships `en` only.

## Consuming this dataset

### Build-time download (recommended)

The simplest path — pin a tag, download the release artefacts at build
time, never commit them to your repo.

```jsonc
// In sailscoring/package.json (or any manifest)
{
  "nationalLettersVersion": "v1.0.0"
}
```

```sh
# prebuild script
VERSION=$(jq -r .nationalLettersVersion package.json)
BASE="https://github.com/sailscoring/national-letters/releases/download/$VERSION"
curl -sSL -o lib/nationalities/codes.json "$BASE/codes.json"
curl -sSL -o /tmp/flags.tar.gz "$BASE/flags.tar.gz"
tar -xzf /tmp/flags.tar.gz -C public/
```

Add `lib/nationalities/` and `public/flags/` to `.gitignore`. Bumping the
dataset is a one-line PR.

### HTML embedding

Sailing results HTML files are commonly emailed, archived, and viewed
years later in clubs with poor connectivity. Embeds must be self-contained:
no CDN dependency, no external URLs.

Flag SVGs are structurally constrained (spec §6.7) so they can be inlined
directly into a host document as `<symbol>` definitions. Each flag appears
exactly once regardless of how many competitors share that nationality:

```html
<!-- Once at the top of the document -->
<svg width="0" height="0" style="position:absolute" aria-hidden="true">
  <symbol id="flag-IRL" viewBox="0 0 1200 600">…inner SVG of IRL.svg…</symbol>
  <symbol id="flag-GBR" viewBox="0 0 60 30">…inner SVG of GBR.svg…</symbol>
</svg>

<!-- Per competitor -->
<svg class="flag" viewBox="0 0 1200 600"><use href="#flag-IRL"/></svg> Ireland
```

A 200-competitor regatta with 5 nationalities ends up with ~5 SVG payloads
plus 200×60 B of `<use>` references — about 30 KB total flag-related
markup, fully self-contained. The equivalent naive inlining of 200
separate `<img src="data:…">` would be ~800 KB.

## Per-flag licence attribution

Flags are public-domain in the overwhelming majority of cases. For every
flag, the recorded licence in `flags-manifest.json` is authoritative.
Where a flag carries attribution or share-alike terms, downstream
consumers must surface them — typically as a small footer in HTML
exports, or a credits screen in apps.

A simple check at integration time:

```sh
jq '[.[] | select(.licenceShortName != "Public domain")] | .[].code' flags-manifest.json
```

returns the (small) set of codes whose licence is not plain public domain.

## Layout

- `data/` — published dataset (`codes.json`, `aliases.json`,
  `flags-manifest.json`, `unresolved.json`)
- `flags/` — per-code SVG flag images
- `sources/` — committed raw inputs used to build the dataset
- `scripts/` — extraction, merge, optimisation, and validation pipeline

## Licence

- **Dataset** (`data/`, scripts, sources): [CC0-1.0](./LICENSE)
- **Flag images** (`flags/`): each file retains its original Wikimedia
  Commons licence; per-file terms are in `data/flags-manifest.json`.
  Where a flag's licence requires attribution, downstream consumers must
  surface it.

## Versioning

Semantic versioning, with major versions aligned to RRS editions
(spec §7.1):

- `v1.x.y` — first release based on RRS 2025–2028; patches add codes, fix
  names, refresh flags, or extend the aliases / extended-names curation
- `v2.0.0` — next RRS edition takes effect, breaking changes to the code
  set

## Development

Requires Python 3.12+ and [`uv`](https://docs.astral.sh/uv/).

```sh
uv sync
uv run pytest
uv run ruff check
```

### Rebuilding the dataset

The RRS 2025–2028 PDF is not redistributed in this repo. Obtain it from
World Sailing (or a public mirror) and point the extraction script at it:

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

Curation files live in `sources/`:
- `flag-overrides.yaml` — per-code Commons file overrides with citations
- `extended-names.yaml` — English names + classifications for Sailwave-only
  codes (`extended` / `historical` / `unresolved`-with-reason)
- `aliases.yaml` — alternate codes observed in real-world data, each
  cited

The flag-fetch step is **resumable** — interrupted runs leave a valid
manifest, and a re-run skips codes whose local file already matches its
recorded sha256. Codes whose default Commons title (`File:Flag of
{names.en}.svg`) does not resolve get added to `flag-overrides.yaml`
with a citation URL; if that still fails, the resolver falls back to
Wikidata (P41/P163/P18).

### Automated rebuilds

`.github/workflows/rebuild.yml` runs the WS + Sailwave + merge +
flag-fetch pipeline on the first of each month. If upstream data has
materially diverged (timestamps alone don't count), it opens a PR
labelled `automated` `data-refresh` for human review.
