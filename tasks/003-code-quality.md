# Plan: code quality follow-ups from the readability audit

## Goal

Finish the cleanup that was too large or too opinionated to do during the audit. The small fixes already landed (see "Already done"). What's left changes structure, removes features, or needs new test fixtures.

## Already done (audit pass, 2026-09-24)

- `goarch_xml_feed.py`: `xpath_text` helper replaces the repeated `str(tree.xpath(...)[0])`. `pipeline` is now `fetch_and_write`, correctly typed. `process_saint_feast_page` bug fixed (`list.push`). Removed the unused `DISMISSAL_HYMN_CHAR_LIMIT`. The prokeimenon verse used `.lstrip("Verse: ")`, which strips a *character set* and would have eaten the first letter of a verse starting with "V", "e", "r" or "s". It now uses `removeprefix`.
- `digital_chant_stand.py`: removed a duplicate unreachable branch in `group_by_sections`. `process_liturgy_variables_page` is no longer async.
- `get_scripture_reading.py`: `get_alleluia` used to compute an alleluia mode and source it never used, and that computation could raise (the "Grave" mode crash). Those lines are now `get_alleluia_mode`, which nothing calls yet. `get_epistle`/`get_gospel` are merged into `get_reading` and return the `ScriptureReading` dataclass they were annotated with.
- `get_dismissal_hymns.py`: builds `DismissalHymnData` rather than bare dicts. Missing fields are now written as `null` instead of being left out.
- `cli.py` now validates the Sunday rule (`parser.error` rather than a traceback) and returns a `date`. `main.py` lost its commented-out code and exits with its return code.
- `utils.http_client()` replaces the duplicated timeout/headers setup. The whole codebase uses built-in generics (`list[...]`), with no `typing.List`/`Dict`.
- `text_sizing.py`: `layout_pages` is the single place that maps a layout name to page contents. `layout_constraints` and `page_fill` both use it. A `Model` (box, metrics, base size) is loaded once per run, not up to three times.
- Typst: removed the unused `date` imports, `image_path`, and the commented-out cover image. Dropped a redundant `text(size:)` wrapper. The alleluia `set par` moved out of its loop. The rendered PDFs are pixel-identical.
- `pyproject.toml`: real name and description. `ipdb`/`ipython` moved to the dev group, and `pillow` was dropped.

## Remaining work

### 1. Offline parser tests (do this first)

The scrapers have no tests. The audit was checked by re-scraping five Sundays live and diffing the YAML, which is slow and depends on GOARCH not changing anything in the meantime.

- Save fixtures for 2-3 Sundays under `tests/fixtures/<date>/`: the Online Chapel index, epistle and gospel XML, and the DCS `li2/en` HTML. Include 2026-05-17 (long readings) and one Sunday with a Grave-mode alleluia.
- Test `process_daily_feed_page`, `process_epistle_page`, `process_gospel_page`, `group_by_sections`, `get_alleluia`, and `get_dismissal_hymns` against the fixtures, with expected values taken from the current `build/` output.
- This is also the safety net for task 002.

### 2. Decide what to do with the unused scraping code

Dead or half-wired code makes it hard to tell what the pipeline actually depends on:

| Code | Status |
|---|---|
| `get_scripture_reading_data`, `get_prokeimenon`, `get_reading`, `get_alleluia_mode`, `ScriptureReadingData`, `DcsScriptureReadingSections.epistle_section/gospel_section` | Not called. `get_prokeimenon` is **already broken** against the live DCS markup (it finds no prokeimenon rows; `ValueError: not enough values to unpack`). |
| `process_saint_feast_page`, `SaintFeastHymnData` | Not called. Possibly useful for task 002 (hymns of the day). |
| `EpistlePageData.mode` | Written, never read. |
| `download_image` of the icon | Runs on every scrape, but the cover image was removed on 2026-08-02. |
| `LiturgyVariablesPageData.dismissal_hymns` | Written, never rendered (`manual.yaml` is used instead). |

For each one, either wire it in as part of task 002 or delete it. Git history keeps the code. Recommendation: do task 002 first, then delete whatever it didn't use.

### 3. Restructure the DCS modules

`get_dismissal_hymns.py` and `get_scripture_reading.py` are named like functions, and they only make sense next to `digital_chant_stand.py`'s `RowItem`/section grouping. Options:

- Fold both into `digital_chant_stand.py`. After step 2 they should be small.
- Or rename them to `dcs_hymns.py` / `dcs_readings.py`.

Move `RowItem`, `DcsSections` and `DcsScriptureReadingSections` next to the code that uses them. `classes.py` would then hold only the YAML contract dataclasses, which is what the build directory table in AGENTS.md describes.

### 4. Errors that name what broke

When GOARCH changes something, the scrape now fails with a bare `IndexError` from `xpath_text`, a `StopIteration` from `next(...)` (which asyncio turns into a `RuntimeError`), or an unpacking `ValueError`. None of them say which source or field was missing.

- Add a `ScrapeError(source, field, url)` and raise it from `xpath_text` and the DCS lookups.
- Consider making failures in unrendered data (dismissal hymns) non-fatal: log and continue, so a DCS wording change can't block the bulletin.

### 5. Retire the legacy sizing comparison

`text_sizing.legacy_sizing` and `breaks_label` exist only so `--report` can print "old vs new" columns, which were for validating task 001 (done). Drop them and the old columns, and update the `--report` description in AGENTS.md and `docs/text_sizing.md`. Keep this only if the old-formula comparison is still wanted.

### 6. Smaller items

- `write_yaml` exists twice: async in `utils.py` (via `aiofiles`) and sync in `text_sizing.py`. The files are a few KB, so a sync write is fine. Move the sync `read_yaml`/`write_yaml` into a dependency-free `yaml_io.py` that both sides import (text_sizing must not import `utils`, because `utils` pulls in `httpx`). That also removes the `aiofiles` dependency apart from `download_image`, which goes away if step 2 drops the icon download.
- `main.py` runs the DCS and feed scrapes one after the other. They are independent and could be `asyncio.gather`ed.
- `manual_entry_template` sets the next service to `run_date + 6` days (a Saturday). Confirm this is intended.
- `README.md` is two sentences. Add the commands from AGENTS.md, or point to it.

## Validation

- `uv run pytest` passes, including the new fixture tests.
- For a spread of dates (2026-03-01, 2026-05-17, 2026-09-27): re-scrape into a scratch dir and diff the YAML against `build/`, then compile `bulletin.typ` and `booklet.typ` and compare them against the current PDFs.
