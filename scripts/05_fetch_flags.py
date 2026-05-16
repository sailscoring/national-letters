"""Resolve and download a Wikimedia Commons flag SVG for every code.

Resolution strategy (spec §6.6), in order:

  1. Override map (sources/flag-overrides.yaml) — takes precedence
  2. Default pattern: "File:Flag of {names.en}.svg"
  3. Wikidata fallback — deferred to a later milestone

Fails loudly with an actionable message for any code that does not resolve,
so the implementer can add an entry to flag-overrides.yaml and re-run.

Outputs:
  flags/<CODE>.svg                  — downloaded file
  data/flags-manifest.json          — provenance + licence per file
  data/codes.json                   — updated with flag.file + flag.sha256
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CODES_PATH = REPO_ROOT / "data" / "codes.json"
MANIFEST_PATH = REPO_ROOT / "data" / "flags-manifest.json"
OVERRIDES_PATH = REPO_ROOT / "sources" / "flag-overrides.yaml"
EXT_NAMES_PATH = REPO_ROOT / "sources" / "extended-names.yaml"
FLAGS_DIR = REPO_ROOT / "flags"

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
USER_AGENT = (
    "national-letters/0.5 "
    "(https://github.com/sailscoring/national-letters; markbmc@gmail.com)"
)
# Wikimedia asks for a small delay between unbatched requests; we batch
# resolves into groups of up to 50 titles per query.
RESOLVE_BATCH_SIZE = 50
# upload.wikimedia.org rate-limits more aggressively than the API. ~1.1s
# keeps us under ~1 req/sec which matches Wikimedia's bot guidance.
DOWNLOAD_DELAY_SEC = 1.1
MAX_RETRIES = 5


def load_overrides() -> dict[str, dict[str, str]]:
    """Merge flag-overrides.yaml with the `commons` fields of extended-names.yaml.

    flag-overrides.yaml entries always take precedence. extended-names.yaml
    is consulted only for `extended:` and `historical:` codes whose curated
    entry carries a `commons` key.
    """
    merged: dict[str, dict[str, str]] = {}
    if EXT_NAMES_PATH.is_file():
        ext = yaml.safe_load(EXT_NAMES_PATH.read_text()) or {}
        for section in ("extended", "historical"):
            for code, entry in (ext.get(section) or {}).items():
                if isinstance(entry, dict) and entry.get("commons"):
                    merged[code] = {
                        "commons": entry["commons"],
                        "citation": entry.get("citation", ""),
                    }
    if OVERRIDES_PATH.is_file():
        data = yaml.safe_load(OVERRIDES_PATH.read_text()) or {}
        if not isinstance(data, dict):
            raise RuntimeError(f"{OVERRIDES_PATH.name}: expected a top-level mapping")
        for code, entry in data.items():
            if not isinstance(entry, dict) or "commons" not in entry or "citation" not in entry:
                raise RuntimeError(
                    f"{OVERRIDES_PATH.name}: entry for {code!r} must have "
                    f"'commons' and 'citation' keys"
                )
            merged[code] = entry
    return merged


def default_title(name: str) -> str:
    return f"File:Flag of {name}.svg"


def resolve_titles(session: requests.Session, titles: list[str]) -> dict[str, dict[str, Any]]:
    """Query Commons imageinfo for many titles at once.

    Returns a mapping from the requested title to its imageinfo dict
    (or to {} if Commons reports the file as missing).
    """
    results: dict[str, dict[str, Any]] = {}
    for i in range(0, len(titles), RESOLVE_BATCH_SIZE):
        batch = titles[i : i + RESOLVE_BATCH_SIZE]
        params = {
            "action": "query",
            "format": "json",
            "prop": "imageinfo",
            "iiprop": "url|extmetadata|sha1",
            "titles": "|".join(batch),
        }
        r = session.get(COMMONS_API, params=params, timeout=30)
        r.raise_for_status()
        payload = r.json()
        # Build {normalized-title -> requested-title} map so we can return
        # results keyed by what the caller asked for.
        normalisation = {n["to"]: n["from"] for n in payload.get("query", {}).get("normalized", [])}
        for page in payload.get("query", {}).get("pages", {}).values():
            title = page.get("title", "")
            requested = normalisation.get(title, title)
            if "missing" in page:
                results[requested] = {}
            else:
                ii = (page.get("imageinfo") or [{}])[0]
                results[requested] = ii
    return results


def extract_licence(info: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Pull (licence, licenceShortName, attribution) from extmetadata."""
    meta = info.get("extmetadata") or {}

    def _get(key: str) -> str | None:
        v = meta.get(key, {}).get("value")
        if isinstance(v, str) and v.strip():
            return v.strip()
        return None

    licence = _get("LicenseShortName") or _get("License") or _get("UsageTerms")
    short = _get("LicenseShortName")
    attribution = _get("Artist") or _get("Credit")
    # Strip simple HTML from attribution (Commons returns rich HTML markup)
    if attribution:
        attribution = re.sub(r"<[^>]+>", "", attribution)
        attribution = re.sub(r"\s+", " ", attribution).strip() or None
    return licence, short, attribution


def commons_page_url(title: str) -> str:
    return "https://commons.wikimedia.org/wiki/" + title.replace(" ", "_")


def wikidata_flag_lookup(
    session: requests.Session, name: str
) -> tuple[str | None, str | None]:
    """Spec §6.6 step 3: find a Commons flag title via Wikidata.

    Searches Wikidata for an entity matching `name`, then follows the
    flag-image property (P41) — falling back to image (P18) — to a
    Commons file title.

    Returns (entity_id, "File:..." title) or (None, None).
    """
    search = session.get(
        WIKIDATA_API,
        params={
            "action": "wbsearchentities",
            "format": "json",
            "language": "en",
            "uselang": "en",
            "type": "item",
            "limit": 5,
            "search": name,
        },
        timeout=30,
    )
    search.raise_for_status()
    candidates = [hit["id"] for hit in search.json().get("search", []) if hit.get("id")]
    if not candidates:
        return None, None

    entities = session.get(
        WIKIDATA_API,
        params={
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(candidates),
            "props": "claims",
        },
        timeout=30,
    )
    entities.raise_for_status()
    payload = entities.json().get("entities", {})
    for qid in candidates:
        claims = payload.get(qid, {}).get("claims", {})
        for prop in ("P41", "P163", "P18"):
            for c in claims.get(prop, []):
                value = c.get("mainsnak", {}).get("datavalue", {}).get("value")
                if isinstance(value, str) and value.lower().endswith(".svg"):
                    return qid, f"File:{value}"
    return None, None


def _get_with_retry(session: requests.Session, url: str) -> requests.Response:
    """GET with backoff on 429/5xx. Respects the Retry-After header."""
    delay = 2.0
    last: requests.Response | None = None
    for attempt in range(MAX_RETRIES):
        r = session.get(url, timeout=60)
        if r.status_code < 400:
            return r
        if r.status_code in (429, 502, 503, 504):
            retry_after = r.headers.get("Retry-After")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
            print(
                f"  {r.status_code} on {url} — retrying in {wait:.0f}s "
                f"(attempt {attempt + 1}/{MAX_RETRIES})",
                file=sys.stderr,
            )
            time.sleep(wait)
            delay = min(delay * 2, 60)
            last = r
            continue
        r.raise_for_status()
    if last is not None:
        last.raise_for_status()
    raise RuntimeError(f"giving up on {url}")


def download(session: requests.Session, url: str, dest: Path) -> str:
    r = _get_with_retry(session, url)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return hashlib.sha256(r.content).hexdigest()


def _atomic_write_manifest(entries: list[dict[str, Any]]) -> None:
    sorted_entries = sorted(entries, key=lambda r: r["code"])
    tmp = MANIFEST_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(sorted_entries, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(MANIFEST_PATH)


def main() -> int:
    if not CODES_PATH.is_file():
        print(f"error: {CODES_PATH.relative_to(REPO_ROOT)} missing", file=sys.stderr)
        return 2

    codes_payload = json.loads(CODES_PATH.read_text())
    codes = codes_payload["codes"]
    overrides = load_overrides()

    # Build the per-code title plan: (code, title, resolved_via)
    plan: list[tuple[str, str, str]] = []
    for record in codes:
        code = record["code"]
        if code in overrides:
            plan.append((code, overrides[code]["commons"], "override"))
        else:
            plan.append((code, default_title(record["names"]["en"]), "default-pattern"))

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    # Resumability: any manifest entries from a prior partial run whose
    # local file still matches the recorded sha256 are reused as-is. This
    # lets a 429-interrupted run pick up where it left off.
    prior: dict[str, dict[str, Any]] = {}
    if MANIFEST_PATH.is_file():
        for entry in json.loads(MANIFEST_PATH.read_text()):
            code = entry.get("code")
            path = REPO_ROOT / "flags" / f"{code}.svg"
            if not path.is_file():
                continue
            if hashlib.sha256(path.read_bytes()).hexdigest() == entry.get("sha256"):
                prior[code] = entry

    # Batch-resolve only the titles we still need.
    titles_to_resolve = [t for code, t, _ in plan if code not in prior]
    if titles_to_resolve:
        print(
            f"resolving {len(titles_to_resolve)} flag titles on Commons "
            f"({len(prior)} reused from prior run) …",
            file=sys.stderr,
        )
        resolved = resolve_titles(session, titles_to_resolve)
    else:
        print("all flags already cached locally — re-validating manifest", file=sys.stderr)
        resolved = {}

    missing: list[tuple[str, str]] = []
    manifest: list[dict[str, Any]] = []
    flag_by_code: dict[str, dict[str, str]] = {}
    timestamp = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    record_by_code = {r["code"]: r for r in codes}

    for code, title, via in plan:
        if code in prior:
            entry = prior[code]
            manifest.append(entry)
            flag_by_code[code] = {
                "file": f"flags/{code}.svg",
                "sha256": entry["sha256"],
            }
            continue

        info = resolved.get(title) or {}
        wikidata_entity: str | None = None

        if not info or "url" not in info:
            # Wikidata fallback (§6.6 step 3).
            qid, wd_title = wikidata_flag_lookup(session, record_by_code[code]["names"]["en"])
            time.sleep(DOWNLOAD_DELAY_SEC)
            if qid and wd_title:
                wd_resolved = resolve_titles(session, [wd_title])
                wd_info = wd_resolved.get(wd_title) or {}
                if wd_info and "url" in wd_info:
                    info = wd_info
                    title = wd_title
                    via = "wikidata"
                    wikidata_entity = qid

        if not info or "url" not in info:
            missing.append((code, title))
            continue

        dest = FLAGS_DIR / f"{code}.svg"
        sha = download(session, info["url"], dest)
        time.sleep(DOWNLOAD_DELAY_SEC)

        licence, short, attribution = extract_licence(info)
        entry = {
            "code": code,
            "commonsTitle": title,
            "commonsUrl": commons_page_url(title),
            "sourceUrl": info["url"],
            "licence": licence,
            "licenceShortName": short,
            "attribution": attribution,
            "wikidataEntity": wikidata_entity,
            "resolvedVia": via,
            "retrievedAt": timestamp,
            "sha256": sha,
        }
        manifest.append(entry)
        flag_by_code[code] = {
            "file": str(dest.relative_to(REPO_ROOT)),
            "sha256": sha,
        }
        # Checkpoint after every successful download so a later 429 still
        # leaves the manifest valid for the work done so far.
        _atomic_write_manifest(manifest)
        print(f"  {code}: {title}  ({via})", file=sys.stderr)

    if missing:
        print("", file=sys.stderr)
        print(f"error: {len(missing)} code(s) did not resolve on Commons:", file=sys.stderr)
        for code, title in missing:
            print(f"  {code}  tried: {title}", file=sys.stderr)
        print("", file=sys.stderr)
        print(
            f"Add overrides to {OVERRIDES_PATH.relative_to(REPO_ROOT)} and re-run.",
            file=sys.stderr,
        )
        return 1

    _atomic_write_manifest(manifest)
    print(f"wrote {len(manifest)} entries to {MANIFEST_PATH.relative_to(REPO_ROOT)}")

    # Stamp flag info into codes.json
    for record in codes:
        record["flag"] = flag_by_code[record["code"]]
    codes_payload["generatedAt"] = timestamp
    CODES_PATH.write_text(json.dumps(codes_payload, indent=2, ensure_ascii=False) + "\n")
    print(f"updated {CODES_PATH.relative_to(REPO_ROOT)} with flag fields")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
