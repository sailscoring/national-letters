# `sailscoring/national-letters` — design specification

A versioned, public-domain dataset of the three-letter national codes used in
sail racing, with English country names and flag images. Built to be consumed
by sail-racing scoring software for entry-list dropdowns and results displays.

## 1. Goals

- **Codes** that match what scorers and sailors actually enter on entry forms —
  primarily the RRS Appendix G "National Sail Letters" set, supplemented by
  World Sailing's current member national authorities, and extended with the
  set of codes used in practice by sailing scorers that fall outside both.
- **English names** structured so that other-language names can be added later
  without a schema break.
- **Flag images** as SVG, retrieved from Wikimedia Commons, with per-file
  licensing recorded.
- **Provenance** recorded per record so any row can be re-verified against the
  upstream source that introduced it.
- **Reproducibility.** The dataset can be regenerated from sources by running
  scripts in the repo. No hand-edited assets in the published artefacts.

## 2. Non-goals

- Not a general country-code library. ISO 3166 is out of scope except where it
  serves as a localisation key for codes that have a clean 1:1 mapping.
- Not a flag-rendering library. The repo publishes SVG bytes; consumers handle
  display.
- Not a federation database. The dataset maps *codes to names and flags*, not
  to MNA contact details, websites, or membership status changes over time.
- Not perpetually exhaustive. Where the source set contains codes whose name
  cannot be sourced to an authoritative reference, the code is omitted rather
  than guessed at (see §5.4).

## 3. Repository layout

```
sailscoring/national-letters/
├── README.md
├── LICENSE                          # CC0-1.0 (dataset). Flag files retain per-file Commons licences.
├── pyproject.toml                   # Python tooling (see §6)
├── scripts/
│   ├── 01_extract_rrs.py            # Parse Appendix G from the RRS PDF
│   ├── 02_fetch_world_sailing.py    # Fetch WS membership page → JSON
│   ├── 03_extract_sailwave.py       # Scrape Sailwave flag directory listing
│   ├── 04_merge.py                  # Produce data/codes.json from the three intermediates
│   ├── 05_fetch_flags.py            # Per code, resolve and download SVG + licence metadata
│   ├── 06_optimise_flags.py         # Run SVGO across flags/ (shells out to Node)
│   └── 07_validate.py               # Lint the published dataset
├── sources/                         # Committed raw inputs for provenance and diffability
│   ├── rrs-2025-2028-appendix-g.txt # Text extract of pp 119–121 of the RRS PDF
│   ├── world-sailing-members.html   # Saved HTML at fetch time
│   ├── sailwave-flags-listing.html  # Saved HTML at scrape time
│   └── flag-overrides.yaml          # Per-code overrides for the flag resolver (see §6.5)
├── data/
│   ├── codes.json                   # Canonical dataset (see §5)
│   ├── aliases.json                 # Alternate-code → canonical-code map
│   ├── flags-manifest.json          # Per-file: Commons URL, licence, attribution, sha256
│   └── unresolved.json              # Codes seen in sources but omitted (see §5.4)
├── flags/
│   ├── ALG.svg
│   ├── ARG.svg
│   ├── …
│   └── ZIM.svg
└── .github/workflows/
    ├── rebuild.yml                  # Re-run scripts on a schedule, open PR if data changes
    └── release.yml                  # Tag → build and attach release artefacts
```

`sources/` and the generated `data/` and `flags/` directories are all committed.
That trades repository size (≲1 MB total) for diffability: every change to the
published dataset appears as a reviewable diff, with a corresponding diff on
`sources/*` that justifies it.

## 4. Data sources

| Source | Role | Provenance recorded |
|---|---|---|
| **RRS 2025–2028 Appendix G — "National Sail Letters"** | Authoritative codes for sail racing | `{ "source": "rrs", "edition": "2025-2028" }` |
| **World Sailing Member National Authorities** ([sailing.org/.../world-sailing-membership/](https://www.sailing.org/inside-world-sailing/organisation/governance/world-sailing-membership/)) | Current membership, canonical English names | `{ "source": "world-sailing", "retrievedAt": "YYYY-MM-DD" }` |
| **Sailwave flag directory** ([sailwave.com/flags/](https://www.sailwave.com/flags/)) | Codes used by sailing scorers in practice but absent from RRS and WS — filename list only, JPGs not used | `{ "source": "sailwave", "retrievedAt": "YYYY-MM-DD" }` |
| **Wikimedia Commons** | SVG flag images, each with its own per-file licence | Per-flag, in `flags-manifest.json` |
| **English Wikipedia** | Source of English names for codes not covered by WS membership | Per-row, with article URL recorded in `flag-overrides.yaml` |

### 4.1 On using the Sailwave listing

The script extracts a list of three-letter filenames, which is factual data and
not copyrightable. The JPG image assets themselves are not downloaded or
redistributed — Sailwave's flag directory carries no licence statement, so it
is treated as an index, not an asset library. The Sailwave directory has not
been updated since 2011; treat it as a frozen historical artefact, not a
maintained source.

## 5. Data schema

### 5.1 `data/codes.json`

```json
{
  "schemaVersion": "1.0",
  "generatedAt": "2026-05-16T12:00:00Z",
  "sources": {
    "rrs":          { "edition": "2025-2028" },
    "worldSailing": { "retrievedAt": "2026-05-16" },
    "sailwave":     { "retrievedAt": "2026-05-16" }
  },
  "codes": [ /* see §5.2 */ ]
}
```

### 5.2 Code record

```json
{
  "code": "IRL",
  "name": "Ireland",
  "category": "rrs",
  "iso3166Alpha2": "IE",
  "iso3166Alpha3": "IRL",
  "presentIn": ["rrs", "world-sailing", "sailwave"],
  "flag": {
    "file": "flags/IRL.svg",
    "sha256": "…"
  },
  "names": {
    "en": "Ireland"
  }
}
```

Field semantics:

- **`code`** — uppercase three-letter. Primary key. Unique across the file.
- **`name`** — canonical English display name. Mirrors `names.en`; duplicated
  for ergonomic access. Spelling and diacritics follow the source (see §5.3).
- **`category`** — one of:
  - `"rrs"` — listed in RRS Appendix G
  - `"world-sailing"` — listed by World Sailing as a member national authority
    but not in the current RRS edition
  - `"extended"` — appears in the Sailwave list but not in RRS or WS; used in
    practice by scorers (e.g. constituent nations of national federations,
    Crown Dependencies, etc.)
  - `"historical"` — no longer in current use but appears in legacy event
    data and must be representable
- **`iso3166Alpha2`** / **`iso3166Alpha3`** — present only when the code
  corresponds to a single ISO 3166 country whose ISO flag matches the
  flag associated with this code. Omitted otherwise — including for
  sport-specific codes, historical codes, codes covering multiple territories,
  and any code where the associated flag differs from the ISO national flag.
  The fields are intentionally omitted rather than mapped, to avoid implying
  a relationship that does not hold. See §6.5 for how this is decided.
- **`presentIn`** — non-empty array of source identifiers (`"rrs"`,
  `"world-sailing"`, `"sailwave"`). Lets consumers filter by provenance.
- **`flag.file`** — repo-relative path. Always present. Enforced by §6.7.
- **`flag.sha256`** — content hash, lets downstream consumers cache and
  invalidate cleanly.
- **`names`** — open dict keyed by BCP 47 language tag. `en` is required;
  other tags (`fr`, `de`, `pt-BR`, etc.) may be added in patch releases
  without schema changes. The schema explicitly does not commit to `en-GB`
  vs `en-US` — see §5.3.

### 5.3 Name convention

`names.en` follows the canonical name from the source that introduced the row:

1. If the code is in RRS Appendix G, use the RRS spelling.
2. Otherwise, if the code is in the World Sailing membership list, use the WS
   spelling.
3. Otherwise, use the spelling from the Wikipedia article cited in
   `sources/flag-overrides.yaml` for that code.

In practice this yields British-English spellings with diacritics (e.g.
"Czechia", "Côte d'Ivoire") because RRS and WS are British-spelling
publications. The README documents this convention. Regional variants
(`en-GB`, `en-US`) may be added in future patch releases without schema
changes, but are not shipped in v1.

### 5.4 Handling codes the build cannot confidently name

The Sailwave listing contains some codes whose meaning cannot be sourced to an
authoritative reference. The merge step (§6.4) handles them as follows:

1. If the code is in RRS or WS, the name comes from there.
2. If the code is only in Sailwave but a Wikipedia article and Commons flag
   clearly establish it, include it with `category: "extended"` and record
   the Wikipedia citation in `sources/flag-overrides.yaml`.
3. If the code is only in Sailwave and no defensible English name can be
   sourced, **omit it** from `data/codes.json` and record it in
   `data/unresolved.json` with the reason. This leaves a visible audit
   ledger without polluting the dataset with guessed names.

### 5.5 `data/aliases.json`

For normalising third-party import data only — not for display.

```json
{
  "schemaVersion": "1.0",
  "aliases": {
    "ALPHA-3-OR-OTHER": {
      "canonical": "XYZ",
      "note": "Free-text note describing where this alias has been observed",
      "source": "URL or short citation"
    }
  }
}
```

Each entry must carry a citation — a URL or short reference identifying where
the alternate form was observed in real data — so the alias can be re-justified
or removed later. Aliases are not added speculatively.

## 6. Build pipeline

### 6.1 Language and tooling

Python 3.12+ with `uv` for environment management. Python is the natural fit
for column-aware PDF extraction (`pdfplumber`), HTML scraping (`beautifulsoup4`),
and Wikimedia API access (`requests` + the MediaWiki Action API directly, or
`mwclient` if convenient). Where a Node-only tool is needed (SVGO), the script
shells out to `npx svgo`.

Implementation may also use TypeScript if the implementer prefers a single
toolchain; the output artefacts are language-neutral JSON + SVG, so the choice
does not affect consumers.

### 6.2 Extract from the RRS (`01_extract_rrs.py`)

Input: a path to the RRS PDF, provided via env var. The PDF is not redistributed
in this repo. The script extracts pages 119–121 and emits
`sources/rrs-2025-2028-appendix-g.json`.

**Important:** column-aware extraction is required. Naive `pdftotext -layout`
extraction on the RRS table can misalign adjacent columns and produce records
where a country gets paired with the wrong code. Use `pdfplumber.extract_tables()`
with explicit column boundaries, and verify against a hand-typed reference for
known rows (`Algeria`, `Argentina`, `Pakistan`, `Panama`, `Trinidad & Tobago`,
`Uganda`, `Zimbabwe`) before trusting the output. The extracted data is then
written verbatim — name corrections are not made here. If the RRS itself
contains a typo, that's a separate concern handled in §6.4 with a clearly
cited override.

### 6.3 Fetch World Sailing membership (`02_fetch_world_sailing.py`)

GET the WS membership page, save HTML to `sources/world-sailing-members.html`
with a timestamp, parse to `sources/world-sailing-members.json`. The page
structure may be a table, a list of cards, or rendered client-side via JS;
inspect on first run and use Playwright if static parsing fails. Record
retrieval date in the output.

### 6.4 Scrape Sailwave (`03_extract_sailwave.py`)

GET `https://www.sailwave.com/flags/`, parse `<img src="./big/XXX.jpg">`
patterns into a list of codes. Emit `sources/sailwave-flags.json`. The JPG
assets themselves are not downloaded.

### 6.5 Merge (`04_merge.py`)

Produce `data/codes.json` by joining the three source files on `code`:

1. Codes from RRS get `category: "rrs"`.
2. Codes only in WS get `category: "world-sailing"`.
3. Codes only in Sailwave with a defensible name get `category: "extended"`.
4. Known historical codes (those appearing in Sailwave but representing
   countries that no longer exist, with a clear Wikipedia citation) get
   `category: "historical"`.
5. Codes the implementer cannot defensibly name are written to
   `data/unresolved.json` and excluded from `codes.json`.

`presentIn` records every source the code appears in. `names.en` follows the
convention in §5.3.

The `iso3166Alpha2` and `iso3166Alpha3` fields are set only when both of:

- the code's name resolves to a single, currently-existing ISO 3166 country, **and**
- the flag resolved by §6.6 for this code is the same image as the ISO flag of
  that country in the standard Wikimedia "Flag of \<Country\>" file

If either condition fails, the ISO fields are omitted. This rule is mechanical
and applied uniformly — no per-code editorial judgement.

### 6.6 Resolve and download flags (`05_fetch_flags.py`)

For each code in `data/codes.json`, resolve a Wikimedia Commons file and
download it to `flags/<CODE>.svg`. Resolution strategy, in order:

1. **Override map.** Consult `sources/flag-overrides.yaml`. Each entry maps
   a code to a Commons file name and **must carry a citation URL** —
   typically a Wikipedia article that displays the flag in question or an
   official federation page. If an entry exists, use it.
2. **Default pattern.** Try `File:Flag of {name}.svg`, where `{name}` is
   `names.en`. Use the Commons API
   (`action=query&prop=imageinfo&iiprop=url|extmetadata`) to check existence
   and fetch the file URL plus licence metadata.
3. **Wikidata fallback.** If neither succeeds, look the code up in Wikidata
   (via the corresponding NOC, MNA, or country entity) and follow the `flag
   image` (P41) or `image` (P18) property. Record the Wikidata entity ID in
   the manifest.
4. **Fail with a clear message** if none resolve. The implementer adds the
   code to `sources/flag-overrides.yaml` with a cited Commons file and re-runs.

Reviewers of `flag-overrides.yaml` verify that each entry's citation
substantiates the chosen Commons file. They are not adjudicating which flag
is "correct" — they are verifying that the upstream source we are deferring
to has been correctly identified and recorded.

Each downloaded file appends a record to `data/flags-manifest.json`:

```json
{
  "code": "IRL",
  "commonsTitle": "File:Flag of Ireland.svg",
  "commonsUrl": "https://commons.wikimedia.org/wiki/File:Flag_of_Ireland.svg",
  "sourceUrl": "https://upload.wikimedia.org/wikipedia/commons/.../Flag_of_Ireland.svg",
  "licence": "Public domain",
  "licenceShortName": "PD",
  "attribution": null,
  "wikidataEntity": null,
  "resolvedVia": "default-pattern",
  "retrievedAt": "2026-05-16T12:00:00Z",
  "sha256": "…"
}
```

`resolvedVia` is one of `"override"`, `"default-pattern"`, or `"wikidata"`,
so the dataset audit trail shows how each flag was located.

### 6.7 Optimise (`06_optimise_flags.py`)

Run SVGO with a conservative config: strip metadata, `<title>`, `<desc>`, and
editor cruft; collapse groups; but **do not** modify `viewBox`, IDs referenced
by `<use>`, or path precision below 3 decimal places (some flags carry fine
geometric detail).

After SVGO, each flag must satisfy:

- Single root `<svg>` element with a `viewBox` attribute
- No embedded raster (`<image>` elements with base64 data)
- No external references (`xlink:href` to URLs)
- No `<script>` elements
- No external font dependencies

These constraints make each file safely inlineable into a downstream HTML
document as a `<symbol>` (see §10) by a trivial string transform.

Target: each flag ≤ 20 KB. Files exceeding 20 KB emit a warning but do not
fail the build — some flags are legitimately complex.

### 6.8 Validate (`07_validate.py`)

CI-blocking checks:

- Every code in `codes.json` has `flags/<CODE>.svg` present and non-empty.
- Every flag file has a corresponding entry in `flags-manifest.json` with a
  non-null `licence`.
- No duplicate codes in `codes.json`.
- Every code matches `^[A-Z]{3}$`.
- Every record has `name` and `names.en`, and they are equal.
- Every record has `category` set to one of the four enum values.
- Every alias in `aliases.json` resolves to a code that exists in `codes.json`.
- Every `sha256` in `codes.json` matches the actual file contents.
- Every flag SVG satisfies the structural constraints in §6.7.

Runs as a GitHub Action on every PR.

## 7. Publishing

### 7.1 Versioning

Semantic versioning, with major versions aligned to RRS editions:

- `v1.0.0` — first release based on RRS 2025–2028
- `v1.x.y` — name corrections, flag refreshes, added extended codes, alias
  additions
- `v2.0.0` — next RRS edition takes effect, breaking changes to the code set

### 7.2 Release artefacts

Each tagged release attaches to its GitHub Release:

- `codes.json` — the bundle for the consumer app
- `aliases.json`
- `flags-manifest.json`
- `flags.tar.gz` — all SVGs

Releases also publish to the GitHub Container Registry / raw download URLs in
a stable form so downstream consumers can pin to a tag without `git clone`.

### 7.3 No npm package in v1

A single consumer (sailscoring) exists at v1. A tagged GitHub Release with a
JSON file is a lower-friction consumption path than an npm package, and the
publishing story can be revisited when a second consumer adopts it.

## 8. How `sailscoring` consumes this

Build-time download of a tagged release tarball. Concretely:

1. Pin the desired tag in `sailscoring/package.json` or a similar manifest:
   ```json
   { "nationalLettersVersion": "v1.0.0" }
   ```
2. A `prebuild` script downloads
   `https://github.com/sailscoring/national-letters/releases/download/v1.0.0/codes.json`
   and `flags.tar.gz`, verifies the SHA against the release notes, and extracts
   into `lib/nationalities/` (gitignored) and `public/flags/` (gitignored).
3. The build generates a typed `lib/nationalities.generated.ts` from
   `codes.json`.
4. Bumping the dataset version is a one-line PR to `sailscoring`.

This keeps the dataset out of `sailscoring`'s git history (no large flag-file
churn) while making the build hermetic and the version explicit.

## 9. How HTML exports embed flags (self-contained pattern)

Sailing results HTML files are commonly downloaded, emailed, archived, and
viewed years later, often in clubs with poor connectivity. Embeds must be
self-contained: no CDN dependency, no external URLs.

The dataset's flag SVGs are designed (§6.7) to be inlined directly into a
host document as `<symbol>` definitions. Each flag appears exactly once in the
document regardless of how many competitors share that nationality.

Recommended pattern for HTML exports:

```html
<!-- Once at the top of the document -->
<svg width="0" height="0" style="position:absolute" aria-hidden="true">
  <symbol id="flag-IRL" viewBox="0 0 1500 1000">…</symbol>
  <symbol id="flag-GBR" viewBox="0 0 60 30">…</symbol>
  <!-- One <symbol> per nationality that appears in this export -->
</svg>

<!-- Per competitor -->
<svg class="flag" viewBox="0 0 1500 1000"><use href="#flag-IRL"/></svg> Ireland
```

The exporter:

1. Collects the set of distinct nationality codes that appear in the export
   (typically 1–10 for a club regatta, up to ~30 for a major event).
2. For each, reads `flags/<CODE>.svg` from the consuming app's vendored copy
   of this dataset, strips the outer `<svg>` to a `<symbol id="flag-<CODE>">`
   shell preserving the `viewBox`, and writes it into the `<defs>` block at
   the top of the document.
3. Per competitor, emits a `<use href="#flag-<CODE>">` reference (~60 bytes
   each).

A 200-competitor regatta with 5 nationalities ends up with ~5 × flag SVG +
~200 × 60 B ≈ 30 KB of flag-related markup, fully self-contained. The
equivalent naive inlining of 200 separate `<img src="data:…">` would be
~800 KB.

Alternative for tools that prefer the CDN path: tagged releases of this
dataset are also fetchable as raw URLs (e.g. via jsDelivr from a GitHub tag).
This is a downstream choice and outside the dataset repo's scope.

## 10. Licensing

- **Dataset** — `codes.json`, `aliases.json`, `flags-manifest.json`,
  `unresolved.json`, all scripts and source files in this repo: **CC0-1.0**.
  Maximally permissive, enables reuse by any sail-racing tool regardless of
  the consumer's own licence.
- **Flag images** in `flags/`: each file retains its original Wikimedia
  Commons licence, recorded per file in `flags-manifest.json`. Most are
  Public Domain; some carry CC-BY-SA or similar terms. Downstream consumers
  must consult `flags-manifest.json` for per-file terms.
- The README directs consumers to surface attribution where any individual
  flag licence requires it.

## 11. Maintenance procedure

- **Each new RRS edition (quadrennial):** point `01_extract_rrs.py` at the new
  PDF, re-run the full pipeline, review the diff, tag a new major version.
- **Annually:** re-fetch the WS membership page (the rebuild workflow can do
  this on a schedule). New members → patch release; demoted members are kept
  with `category: "historical"`, never deleted (legacy event data references
  them).
- **Ad-hoc:** name corrections, flag refreshes (Commons sometimes uploads more
  accurate SVGs), responses to bug reports.

The `.github/workflows/rebuild.yml` workflow runs the full pipeline monthly
against fresh upstream sources and opens a PR if anything diverged. This makes
maintenance noticed-and-reviewed rather than silently forgotten.

## 12. Decisions already made

- Repo name: `sailscoring/national-letters`
- Dataset licence: CC0-1.0
- Consumption model in sailscoring: build-time download of a tagged release
  tarball; verified by SHA
- Codes from Sailwave that cannot be confidently named: omit from `codes.json`,
  record in `unresolved.json`
- Schema language tag for English names: `en` (with documented convention
  per §5.3)
- Build language: Python (with TypeScript as an acceptable alternative)
- HTML export embedding: self-contained via `<symbol>` + `<use>`

## 13. Open decisions for the implementer

- CI host: GitHub Actions is assumed throughout, but any CI works.
- Whether to publish a Python package alongside the JSON release (probably not
  for v1 — wait for a second Python consumer).
- Whether to mirror release artefacts to a CDN proactively. For v1, GitHub
  release URLs are sufficient.
