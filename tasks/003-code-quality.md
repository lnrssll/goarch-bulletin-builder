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

## Follow-up status (2026-09-24)

1. **Offline parser tests: done, with a different design.** Every fetch now goes through `utils.SourceArchive`, which caches raw sources in `archive/<date>/` (committed) and writes them only after a successful scrape. `tests/test_scrapers.py` replays each archived Sunday offline and compares the output with `tests/snapshots/`. Three Sundays are archived: 2026-09-13, 09-20 (Grave mode) and 09-27. New Sundays are archived as they're built. Past dates were deliberately not backfilled: GOARCH serves Cloudflare bot-check pages to scripted traffic, and older DCS pages are gone.
2. **Unused scraping code: partly done.** The icon download and `icon_filename` are gone. The rest (DCS readings and prokeimenon, saint/feast hymns, `EpistlePageData.mode`) is left for task 002 to wire in or delete.
3. **DCS modules: done.** `get_dismissal_hymns.py` and `get_scripture_reading.py` are folded into `digital_chant_stand.py`, along with `RowItem` and the other DCS-only dataclasses.
4. **Errors: done.** `ScrapeError` names the source, the URL and what was missing. A page without an Alleluia (e.g. a bot-check page) is a `ScrapeError`. Dismissal hymn failures only warn. `main.py` exits 1 and archives nothing.
5. **Legacy sizing comparison: done.** Removed from `--report`.
6. **Smaller items: done**, except one question. `yaml_io.py` replaces `aiofiles` and the duplicate `write_yaml`, the scrapes run concurrently, and the README has usage. Still open: `manual_entry_template` sets the next service to `run_date + 6` days (a Saturday). Is that intended?
