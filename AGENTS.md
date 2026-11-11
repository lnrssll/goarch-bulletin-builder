# AGENTS.md

Guidance for coding agents working in this repository.

## What this is

A generator for a weekly Sunday Divine Liturgy bulletin (Lake Havasu Orthodox Church mission). A Python scraper collects the liturgical variables for a given Sunday from two Greek Orthodox Archdiocese (GOARCH) sources and writes them as YAML. Typst templates then read that YAML and render a printable PDF. A small web UI (`web.py`) runs the whole thing from one page per Sunday, so someone at the church can make the bulletin without a terminal. The goal is that the church can keep using it for about ten years without technical help, which is why the stack is small and boring (see "Web UI").

### Parish context

Lake Havasu is a mission with no resident priest. A visiting priest serves the Divine Liturgy on **Saturdays**, using the hymns and readings of the *following Sunday*. So:
- Everything is keyed by the Sunday's date (`main.py` requires a Sunday, and the `state/sundays/` and `archive/` folders use it). That is the liturgical day, even though the bulletin is handed out the day before.
- In `manual.yaml`, `upcoming_services` dates are Saturdays. The template's next service is the Saturday before the next Sunday (`manual.service_day`). This follows the `liturgy_day` setting, which can be switched to "sunday" if the mission gets a resident priest.
- The parish details in `data/parish.yaml` (welcome text, website, contacts) are real (see "Parish settings"). The two contacts are the head priests of the two churches whose priests serve the mission (Assumption, Scottsdale; Saint Katherine, Chandler), not every visiting priest, so the settings have exactly two contact slots (`parish.CONTACTS`), and the contacts aren't mixed into the Priest suggestions.

```
web.py (browser) --+
main.py (CLI) -----+-> sunday.fetch_readings
                   |     +-> digital_chant_stand.py -> state/sundays/<date>/digital_chant_stand.yaml
                   |     +-> goarch_xml_feed.py ----> state/sundays/<date>/{feed,epistle,gospel}.yaml + icon image
                   |     |     (both fetch through utils.SourceArchive -> archive/<date>/, committed)
                   |     +-> manual.py -------------> state/sundays/<date>/manual.yaml   (template; then hand-edited)
                   |     +-> text_sizing.py --------> font size + page breaks into state/sundays/<date>/feed.yaml
                   +-> sunday.save_readings / manual.write   (the web forms)
                   +-> parish.save ---------------> state/settings/parish.yaml   (Settings pages)
                   +-> render.py (typst-py) --------> state/sundays/<date>/{booklet,bulletin}.pdf + preview-N.png

typst CLI (bulletin.typ / booklet.typ) <-- state/sundays/<date>/*.yaml + state/settings/ --> out/<date>.pdf   (CLI workflow)
```

## Commands

Run everything from the repo root. Both the Python code and Typst use paths relative to the root (`state/`, `data/`, `assets/`).

```sh
uv sync                                 # install deps (Python >= 3.13)
uv run web.py                           # web UI on http://127.0.0.1:8000 (no password when local)
uv run web.py --port 8080 --host 0.0.0.0  # beyond this computer: needs BULLETIN_PASSWORD set
uv run main.py                          # scrape data for the next upcoming Sunday
uv run main.py 27 9 2026                # scrape a specific Sunday: DAY MONTH YEAR (YEAR may be 2-digit)
uv run main.py 27 9 2026 --refresh      # re-download sources that are already in archive/

uv run text_sizing.py 2026-09-27            # re-size an existing Sunday (rewrites the sizing fields in feed.yaml)
uv run text_sizing.py --explain 2026-09-27  # show the sizing model for one date (read-only, offline)
uv run text_sizing.py --report              # sizing for every date in state/sundays/ (read-only, offline)
uv run pytest                               # all tests, offline
UPDATE_SNAPSHOTS=1 uv run pytest            # regenerate tests/snapshots/ (scraped YAML, preview hashes) after an intended change

# render; the date input selects state/sundays/<date>/ (main.py first makes sure state/settings/ exists)
typst compile --input date=2026-09-27 booklet.typ out/2026-09-27.pdf    # 2-up A5 booklet for printing
typst compile --input date=2026-09-27 bulletin.typ out/2026-09-27.pdf   # plain A6 pages
typst watch   --input date=2026-09-27 booklet.typ out/2026-09-27.pdf    # live re-render while editing
```

`main.py` prints a ready-to-paste `typst watch` command at the end. It is written for nushell, the user's shell.

Deployment is in `deploy/README.md`: one Docker image, run with `docker compose` locally or behind nginx + certbot (modeled on the user's `stablestack` template), or on Railway. Settings are environment variables documented in `.env.example`; `.env.local` and `.env.prod` hold the real values and are gitignored (and kept out of the image by `.dockerignore`). `web.py` reads `PORT`, and at startup refuses to run if `state/` isn't writable (a Railway volume needs `RAILWAY_RUN_UID=0`). Everything that can't be regenerated lives under `state/`, so a deployment needs one volume, at `/app/state`. The Docker test run doesn't touch the repo's `state/`: compose uses its own volumes. `deploy/README.md` "Maintenance" is the developer's yearly checklist and what expires when; `deploy/HANDOVER.md` is the church's one-page sheet (plain words, blanks to fill in, no technical terms beyond what they must click).

Notes:
- `cli.parse_run_options` rejects dates that aren't Sundays and years before the current year.
- Tests (`tests/`), no linter config or CI. All offline, ~6s:
  - `test_text_sizing.py`: synthetic tests of the sizing model.
  - `test_scrapers.py`: replays every Sunday in `archive/` offline through `sunday.fetch_readings`, then compares the scraped YAML with `tests/snapshots/<date>/`. A snapshot diff after a scraper change is either a regression or an intended change; regenerate the snapshots only for the latter. To add a regression case, commit its `archive/<date>/` and generate its snapshot.
  - `test_source_archive.py`: archive caching, using `httpx.MockTransport`.
  - `test_commemorations.py`: the saints and feasts from the archive, in order, and which Chant Stand hymn each archived Sunday's goarch.org hymns match (a table checked by hand), mode numbers, reading old Sundays from `archive/`, a bot-checked saint page, and titles saved before (on a made-up history in `tmp_path`).
  - `test_sunday.py`: the fetch pipeline (one source failing, bot-check pages, keeping what a failed download sent) and the readings editor's load/save.
  - `test_backup.py`: what goes into the backup zip, and remembering the last download.
  - `test_parish.py`: parish settings: only changes are stored, defaults fill in missing or unreadable ones, typographic quotes, put back the original, undo, history limit, the QR code and uploaded images.
  - `test_manual.py`: `manual.yaml` reading, the template and its carry-over from last week, the "Fr." and "p." prefixes, suggestions, and that `data/hymns.yaml` agrees with the hymnal index.
  - `test_render.py`: every snapshot Sunday renders to a 2-page booklet with typst-py, and its preview pictures match the hashes in `tests/snapshots/<date>/previews.sha256` (a failure says where the new pictures are; `UPDATE_SNAPSHOTS=1` accepts an intended change, and check the pictures before you do); re-render only when an input changes; long hymn titles print in short form (read back with `typst.query` on the `<hymn-title>` metadata); settings with Typst-special characters, any number of contacts, no website, a new logo, and an overflowing welcome text.
  - `test_web.py`: drives the WSGI app directly (no server): the Sunday workflow, forms, every settings page, logo uploads (multipart, built by the test client), login, cross-site and oversized posts.
  - `conftest.py` has the `site` fixture: a temp copy of the repo root (Typst files, `data/`, `assets/`, `templates/`, `static/`) as the working directory, so tests never touch the real `state/`. Code that reads settings (`parish.load()`, `manual.write_template`) must run under it, or it reads the real `state/settings/`.
- Don't bulk-download past Sundays. GOARCH is behind Cloudflare and serves bot-check pages to scripted traffic, and DCS seems to keep only the current year: in September 2026, 2026-01-04 downloaded, but 2025-01-05 and 2024-01-07 were 404. So a Sunday that isn't in `archive/` by the end of its year can't be fetched again. Test against what's already in `archive/`.
- The `Makefile` is stale: it references `webscraper/main.py` and is gitignored. Don't use it.
- `state/` and `out/` are gitignored. Everything in `out/` is generated. `state/` holds what can't be: each Sunday's `manual.yaml` and all of `state/settings/` (see below).
- Never run the web server or `main.py` against the real `state/` to try something out: it holds the user's hand-edited `manual.yaml` files and settings. Use a scratch copy of the repo.

## Data sources

Every fetch goes through `utils.SourceArchive(root, client, refresh)`, which caches the raw XML and HTML under `archive/<date>/` (`chapel.xml`, `epistle.xml`, `gospel.xml`, `saints/<contentid>.xml`, `icon/<file>.jpg`, `dcs.html`). An archived source is never downloaded again unless `--refresh` (or the web UI's "Download them again") is given. New downloads are held in memory and written by `archive.save()` only after that source's scrape succeeds, so an error page or a Cloudflare challenge never gets archived. Error responses are held apart (`refused`) for the same reason. When a source fails, `download_readings` saves everything it received, error pages included, to `state/failed-downloads/<time>_for_<date>/<source>/` (`SourceArchive.save_failed`; the last 20 are kept). That's the page to look at when goarch.org changes: it's on the server's volume and in the church's backup zip, and the web page's "Technical details" and `main.py` give the path. It isn't under `archive/` because Railway doesn't keep `archive/`. With `client=None` the archive is offline and raises `NotArchived` for anything missing; the tests work this way. `archive/` is committed: commit each new Sunday's sources along with any code change. (A deployed server archives into its own Docker volume; nothing there is committed.)

Each source module has `async scrape(run_date, archive)`, which returns dataclasses, and `write(data, out_dir)`, which writes the YAML. A page that doesn't parse raises `utils.ScrapeError`, naming the source, the URL and what was missing.

`sunday.fetch_readings` is the one pipeline, used by `main.py`, the web UI and the snapshot tests. It lists the sources in `sunday.SOURCES` (name, what it provides, the files it writes, and `page_url(date)`, the page a person can open to compare; the Sunday page links to it under "On goarch.org") and scrapes them concurrently, each with its own `SourceArchive`. A source that fails (`ScrapeError` or `httpx.HTTPError`) archives and writes nothing, and its existing files are kept; the other source is still archived and written. That way a site change on one side leaves only that part to type in by hand. If every source fails, nothing is written at all. Afterwards it writes the `manual.yaml` template if there is none, and runs `text_sizing` once all four readings files exist. It returns a `FetchResult` with the failures. `main.py` prints them and exits 1; the web UI explains them in plain words (`web.explain`).

### GOARCH Online Chapel XML feed (`goarch_xml_feed.py`)
- Index: `https://onlinechapel.goarch.org/daily?date=M/D/YYYY` returns an `<onlinechapel>` XML doc with the lectionary title, formatted date, reading URLs (`reading[type="E"|"G"]`), saint/feast URLs, and the icon URL.
- The epistle and gospel URLs return XML. The English text is under `translation[@xml:lang="en"]`, and the body is an HTML string parsed with selectolax.
- Every saint/feast XML is fetched at the same time and archived (`fetch_commemorations`). Each becomes a commemoration in `commemorations.yaml`, in the feed's order: the feed's title, its XML and public URLs, and its hymns (`process_saint_feast_page`: type, title, short title, tone, English text). A page that fails or isn't a `<saintfeast>` (a bot check, which `SourceArchive.discard` keeps out of the archive) leaves that commemoration's `hymns` null and doesn't fail the source.
- `identify_icon` returns the title of whichever saint/feast page uses the day's icon. That title becomes `icon_title`, or `''` if it matches the lectionary title.
- XML is parsed with `recover=True` because the feed is sometimes malformed.
- The icon of the day (`icon_src`) is downloaded, archived, and copied into the Sunday's folder as `icon_filename`. It is deliberately **not** printed in the bulletin: an icon is holy and must be burned or buried rather than thrown away, and bulletins get thrown away. It's kept so an icon can someday be printed separately. Don't remove the icon code. A failed icon download only warns.

### Digital Chant Stand (`digital_chant_stand.py`)
- URL: `https://dcs.goarch.org/goa/dcs/h/s/YYYY/MM/DD/li2/en/`, the Divine Liturgy service HTML.
- `iter_row_items` flattens `tbody > tr > td > *` into `RowItem(kind, text, node)`. `kind` is the `<p>`'s CSS class with non-letters removed (e.g. `designation`, `source`, `mode`, `hymn`, `dialog`, `chapverse`, `reading`, `verse`, `mixed`), or `media`.
- `group_by_sections` splits the rows into a list of `(title, rows)` sections, in page order, each starting at a `designation` row or a `mixed` row starting with "Alleluia". It's a list because titles repeat: on most Sundays "Resurrectional Apolytikion." comes once before the Entrance and again after it (a dict keyed by title once hid the second one). A `source` row is held back and attached to the next section.
- `parse_mode` gives "4", "Plagal 1" or "Grave".
- Extraction depends on exact section titles from the page: `"Hymns after the Entrance."` ... `"Trisagios Hymn"` for dismissal hymns; `"The Epistle"`, `Alleluia*`, `"The Gospel"` ... `"Hymn to the Theotokos."` for readings. Also on `data-key*=` attribute selectors (`alleluia`, `Epistle`, `Gospel`, `prokeimenon`). A missing Alleluia is a `ScrapeError`. A failure in the unrendered dismissal hymns only prints a warning.
- Only `alleluia` from DCS is actually rendered. Epistle and gospel text come from the XML feed. `get_scripture_reading_data`, `get_reading`, `get_prokeimenon` and `get_alleluia_mode` exist but aren't wired in, and `get_prokeimenon` no longer matches the live markup (see `tasks/002`).
- `get_alleluia_mode` numbers modes 1-8: "pl. N" is N+4, and "Grave" is 7.

### Not used
- The GOARCH calendar site is blocked by Cloudflare bot protection, so there is no scraper for it.
- `notes.md` lists possible alternative sources (Orthocal API, Ponomar typicon).

## Sunday folder contract (`state/sundays/<YYYY-MM-DD>/`)

The Python side writes these files and the Typst side reads them. Keep field names in sync on both sides. The dataclasses in `classes.py` are serialized with `asdict` -> `yaml.safe_dump`.

| File | Written by | Key fields used in Typst |
|---|---|---|
| `feed.yaml` | `goarch_xml_feed.write` (`DailyFeedPageData`), then `text_sizing.run` fills in the sizing fields | `lectionary_title`, `formatted_date`, `icon_title`, `text_size_factor` (percent of `base_size_pt`), `alleluia_page_break`, `gospel_page_break`. Diagnostics only: `font_size_pt`, `layout`, `page_fill`. Read by `text_sizing` only: `size_override_pt`, `layout_override` (chosen by hand in the readings editor; null for automatic) |
| `epistle.yaml` | `EpistlePageData` | `book`, `chapverse`, `prokeimenon`, `verse`, `text[]` |
| `gospel.yaml` | `GospelPageData` | `book`, `chapverse`, `text[]` |
| `digital_chant_stand.yaml` | `LiturgyVariablesPageData` | `alleluia[]` (`dismissal_hymns` isn't printed, but the Sunday page shows them next to the commemorations) |
| `manual.yaml` | `manual.write_template`, then the web form (`manual.write`) or a text editor | `dismissal_hymns[] {title, mode, page}` (`mode` may be null), `upcoming_services[] {date, priest}` |
| `commemorations.yaml` | `goarch_xml_feed.write` | not printed. `commemorations[] {title, url, public_url, hymns[] {type, title, short_title, tone, body}}`; `hymns` is null when the page couldn't be read. Shown on the Sunday page (`commemorations.py`). Not in `Source.files`, so a Sunday without it isn't "missing" anything |
| `<icon_filename>` (jpg) | `goarch_xml_feed.write` | not printed on purpose (see the icon note above). `feed.yaml` has `icon_filename` and `icon_title` |
| `booklet.pdf`, `bulletin.pdf`, `preview-N.png` | `render.py` | outputs, not read by anything; the booklet's mtime marks the render as current |

The readings files can also be written by the web UI's readings editor (`sunday.save_readings`), which updates only the fields it shows and keeps the rest (URLs, icon, `mode`, `dismissal_hymns`). Saved paragraphs have their whitespace collapsed, which Typst does anyway.

**`manual.yaml` is hand-edited, and its contents can't be regenerated.** `manual.write_template` writes a template only if the file doesn't exist; nothing else writes it except the user saving the web form. Never overwrite or delete an existing one. The user fills in the "Hymns of the Day" list (title, mode, and page in their hymnal) and the upcoming-services list. The template carries the priests over: an entry in the most recent earlier week's list (up to 8 weeks back) dated this week's service day becomes the `today` label ("Today"), later ones are kept, and next week's service day is added if missing. Placeholders ("Example" hymn, "Fr. X") are flagged by `manual.unfinished`. `manual.read` is tolerant of hand edits (missing keys, string modes). `data/table-of-contents.txt` is a reference index of hymnal page numbers (`title | page | section`); the web UI shows it under "Page numbers in the hymnal", and the `hymnal_index` setting can replace it. The English hymns are on odd pages (the even ones are Greek), and `manual.unfinished` flags an even one.

**Hymn catalog (`data/hymns.yaml`, `tasks/done/007-hymn-and-priest-suggestions.md`).** A curated list of the hymns the parish sings: full `title`, optional `short` (printed when the title doesn't fit), `also` (other names and old spellings), a fixed `mode`, and `page` or `pages_by_mode` (bare numbers, or Choir/Handout). Its `abbreviations` (Apolytikion → Apol., …) are used both ways: `bulletin.typ` shortens a title with them when it doesn't fit on one line, and saving the form expands typed ones, so titles are stored in full. `manual.suggestions` puts the catalog first (most used in the last 52 Sundays first), merges history titles that match a title or alias (ignoring case, punctuation and abbreviations), then adds the other history titles with any mode or page that never changed. A test checks every page against the hymnal index. Modes come from past bulletins and the archived DCS pages; hymns without a known mode have none, on purpose.

**Prefixes.** The form shows priests without "Fr." and pages without "p."; `manual.priest_label` and `manual.page_label` add them back on save (removing any typed anyway), except for `NO_PRIEST` ("Reader Service", "TBD") and `NOT_A_PAGE` ("Choir", "Handout"). `manual.yaml` keeps the prefixed text, so Typst is unaffected.

Re-running `main.py` for a date overwrites every other file in that date's folder.

**Commemorations (`commemorations.py`).** To help title the Hymns of the Day, the Sunday page shows the Chant Stand's hymns after the Entrance (`dismissal_hymns` in `digital_chant_stand.yaml`) next to goarch.org's saints and feasts, each collapsible to its hymns. `compare` marks a pair as the same hymn when the shorter text shares at least `SAME_HYMN` of its words with the other, after turning "Thy", "hast" and the like into modern English, since the two sites use different translations. In the archived Sundays the same hymn shares 0.42 or more and different hymns 0.31 or less; `test_commemorations.py` holds the expected pairs, so add each new archived Sunday there. `mode_number` turns "Plagal 1" and "Plagal of the First Tone" into the bulletin's 5. A Chant Stand hymn with no goarch.org match (usually the kontakion) gets `used_before` from `add_past_titles`: the titles saved on the last 52 Sundays whose Chant Stand had the same text (`SAME_TEXT`, the Chant Stand's own translation). The saved rows don't line up with the Chant Stand's row by row, so a saved title is paired with a Chant Stand hymn of the same kind (kontakion, resurrectional, other apolytikion) and mode; titles are shown in the hymn list's spelling. Each hymn has an "Add to Hymns of the Day" button (`static/app.js`) that fills the first empty row, or the "Example" one, with the goarch.org title when there's a match, else a title saved before, else the Chant Stand's, and the Chant Stand's mode, which is what the parish prints when the two disagree; the page then fills in from `data/hymns.yaml` as for a picked suggestion. A Sunday downloaded before `commemorations.yaml` existed is read from its `archive/` folder instead (`load`), or shows none.

## Parish settings (`parish.py`, `state/settings/`)

Everything the bulletin prints that isn't the week's readings, hymns or services, plus when the Liturgy is served, the hymnal index, and the church calendar the Sunday page links to (`calendar`, for finding who serves; not printed). Past Sundays pick up the current settings when they're rendered again.

- **Defaults** are committed in `data/parish.yaml` (and `data/table-of-contents.txt` for `hymnal_index`). They are the real Lake Havasu values.
- **The church's changes** are in `state/settings/parish.yaml`, which holds **only the keys that differ** from the defaults: `parish.save` drops a key whose value equals the default. So a corrected default reaches every setting the church hasn't changed. `bulletin.typ` and `bulletin_back.typ` merge the two files the same way (`inputs.typ`: `yaml(defaults) + yaml(changes)`), and `parish.load()` does it in Python, falling back to the default for a missing or unreadable value.
- **Typst can't check whether a file exists**, so `parish.ensure()` writes an empty `{}` settings file and the QR code (`state/settings/qr.svg`, generated with `segno` from `website`) before anything renders: from `render.py`, `main.py` and `web.py`'s startup. Files are only rewritten when their content changes, so the render cache (`render.inputs`, which includes `state/settings/`) isn't invalidated for nothing.
- **Undo:** each save first copies `parish.yaml` to `state/settings/history/<timestamp>.yaml` (the last 50 are kept); `parish.undo` writes the newest back and removes it. It writes rather than renames, so the mtime tells the render cache. "Put back the original" (`parish.put_back`) saves the defaults for a section's keys.
- **Uploaded logos** go to `state/settings/images/<sha256>.<ext>`, named by content so older settings in the history still find theirs. PNG, JPEG and WebP only, by their first bytes, then a trial compile of just the image (`render.check_image`).
- **Plain text:** Typst prints YAML strings literally, so a `#`, `*` or `$` can't break the document. Saving turns straight quotes in printed prose into typographic ones (`parish.typographic`), as Typst markup would; emails, websites and phones are left alone. The defaults use `’` for that reason.
- **Backups** (`backup.py`, `deploy/README.md` "Backups"): the Settings page's download, for a copy off the server kept by the church, plus a weekly host cron job or Railway volume backups.
- **Not settings:** `data/layout.yaml` and `data/text_metrics.yaml` (the text sizing is calibrated to them; a developer job), and the password and time zone (server config).

## Layout logic

- **Geometry** lives in `data/layout.yaml` (page size, margins, booklet gutter, base font size, leading, paragraph spacings, indents). `bulletin.typ`, `booklet.typ` and `text_sizing.py` all read it, so change page setup there rather than in the `.typ` files.
- **Text size and page breaks** (`text_sizing.py`, summary in `docs/text_sizing.md`, design in `tasks/done/001-text-sizing.md`). One font size is used for both reading pages. The readings are modeled as blocks (epistle with prokeimenon, alleluia, gospel), each with a height that depends on the font size: wrapped lines per paragraph, paragraph spacing, and a fixed em-height for headings and gaps. There are three layout candidates: `split_before_alleluia` (Alleluia goes with the Gospel), `split_before_gospel`, and `flow` (no forced break). The solver finds the largest size, in 0.1pt steps up to `base_size_pt`, at which each layout fits. It picks the layout with the largest size and breaks ties in that order. There is no minimum size, but it prints a notice below 7pt. It reads only the YAML in the Sunday's folder, so it can be re-run without re-scraping. A size or page break chosen by hand in the readings editor (`size_override_pt`, `layout_override` in `feed.yaml`) is applied after solving, so the model itself stays automatic; see `docs/text_sizing.md` "Chosen by hand". It must not import the scraper modules or `httpx`.
- **Model constants** are in `data/text_metrics.yaml`. They were checked against rendered PDFs for every Sunday of Jan-Sep 2026: no overflow, binding pages ~85-95% full. They are deliberately conservative, most of all below ~8pt. If PDFs come out consistently underfilled or overflowing, adjust `glyph_advance_em` first. After changing a constant, run `--report` and compile a spread of dates (short, typical, 2026-05-17) and check the page count and fill.
- `bulletin.typ` defines content blocks (`front_page`, `readings(sep:)`, `back_page`) *and* a standalone A6 layout. `booklet.typ` imports those blocks and imposes them two-up on A5-landscape sheets (sheet 1: back|front; sheet 2: readings across two columns, with `colbreak` in place of `pagebreak`). Put content changes in `bulletin.typ`, and keep them as reusable blocks so the booklet picks them up. Page setup belongs in each file's layout section.
- `bulletin_back.typ` lays out the welcome text, upcoming services (from `manual.yaml`), contacts (two per row; empty fields left out), logo, and QR code with the website printed beside it. The text comes from the parish settings.
- `inputs.typ` turns `--input date=...` into `state/sundays/<date>/`, and loads the parish settings (`parish`).
- The front logo is 80% of the page width, or at most 25mm tall, so a square logo doesn't push the page over.
- **Rendering in Python** (`render.py`) uses the `typst` package (typst-py), which bundles the compiler, pinned to `<0.16` in `pyproject.toml` because the text metrics are calibrated against this release's rendering. Its output was checked pixel-identical to the typst 0.15.1 CLI. It passes `ignore_system_fonts=True`, so only Typst's embedded fonts are used and the output is the same on any machine (the Docker image has no system fonts). `render.ensure_rendered(date)` re-renders when any input (the Sunday's YAML, `*.typ`, `data/layout.yaml`, `data/hymns.yaml`, `data/parish.yaml`, `assets/`, the files in `state/settings/`) is newer than `booklet.pdf`, and returns the booklet's page count: 2 is right (outside and inside of one folded sheet), more means something overflowed (the readings, or the back page after a settings change), and the web page warns. A Typst error becomes a `render.RenderError`.

## Web UI (`web.py`)

The stack follows the user's `stablestack` template, translated to Python: few dependencies, server-rendered HTML, nothing that needs a build step.

- **A plain WSGI app on the standard library.** `ROUTES` is a table of `(method, regex, handler)`. Handlers are functions `handler(req, *url_groups) -> Response` and raise `NotFound` for a 404. Helpers: `page` (render a template), `redirect` (303, with an optional one-time message), `plain`. No web framework: WSGI (PEP 3333) runs unchanged on any Python server.
- **`waitress`** serves it (pure Python, no dependencies of its own). **`jinja2`** renders `templates/*.html` with autoescaping and `StrictUndefined`.
- **No database.** The files under `state/` are the state, the same files the CLI reads and writes.
- **No client-side framework, no JS or CSS build.** Plain forms and full page loads. `static/app.js` only adds conveniences (disables buttons while a form is sent, confirms before re-downloading, warns about unsaved changes, and turns each `<input list=…>` into a suggestion box that completes on Tab, lists everything on click, and fills in a hymn row's mode and page without replacing anything typed by hand; a value the page was loaded with, such as a saved hymn's page or the "Example" row's 0, is replaced by a known one but never erased; and shows the "Add to Hymns of the Day" buttons beside the day's hymns, hidden without it); every page works without it, falling back to the plain datalists. It has no automated tests. `static/style.css` is hand-written, with a dark mode.

Flow: each change is a form POST that does its work and redirects to the Sunday page. The redirect carries a one-time message (`Flash`) in the `bulletin_flash` cookie. The Sunday page re-renders the PDFs when they're stale. Scrapes, saves and renders take turns on `WORK_LOCK`, since they all rewrite files under `state/`. The scrape runs inside the request (`asyncio.run`) and takes ~10s, up to a minute, so nginx's timeout is raised in `deploy/`.

| Route | Does |
|---|---|
| `GET /` | next Sunday, a date picker, every Sunday in `state/sundays/` with a status |
| `GET /sundays?date=` | opens the Sunday on or after a date (a service Saturday opens its Sunday) |
| `GET /sundays/<date>` | the three steps: readings, hymns and services, print (preview images of both booklet sides). Step 2 starts with the day's hymns from the Chant Stand next to goarch.org's commemorations (see "Commemorations") |
| `POST /sundays/<date>/fetch` | `sunday.download_readings`; `refresh=yes` re-downloads |
| `POST /sundays/<date>/details` | writes `manual.yaml` from the form; a row with no title (hymns) or no date and priest (services) is dropped; "p." and "Fr." are added, and abbreviations in titles expanded |
| `GET`/`POST /sundays/<date>/readings` | the readings editor, which also works when nothing was fetched |
| `GET /sundays/<date>/{booklet,bulletin}.pdf` | `?download=1` for an attachment |
| `GET /settings` | the settings sections (linked only from the page footer, on purpose), Advanced collapsed, and "Undo the last change" |
| `GET`/`POST /settings/<section>` | one small form per section (`web.SECTIONS`: welcome, contacts, website, calendar, logo, liturgy-day, wording, hymnal), with a picture of the booklet for the next printable Sunday so a change can be checked; a refused form is shown again with what was typed. The logo form is `multipart/form-data` |
| `POST /settings/<section>/original` | puts back the defaults for that section |
| `POST /settings/undo` | undoes the last settings change, then returns to `next` |
| `GET /settings/logo-picture` | the current logo, for the logo page |
| `GET /settings/backup.zip` | `backup.make_zip`: everything under `state/` but the PDFs and preview pictures, paths relative to `state/`; records the time in `state/last-backup.txt`. The home page reminds after 35 days without one |

Safety:
- With `BULLETIN_PASSWORD` set, every page but `/login` and `/static/` needs a session: an HMAC-signed expiry in an HttpOnly, SameSite=Lax cookie, marked `Secure` over HTTPS (waitress trusts `X-Forwarded-Proto`; the container is only reachable from the host's nginx). The signing key is random per process, so a restart logs everyone out. Failed logins wait a second. Without a password there's no login, `main()` refuses to listen beyond localhost, and a request whose `Host` isn't localhost, 127.0.0.1 or ::1 is refused, so a web page can't reach it by pointing its own name at 127.0.0.1 (DNS rebinding).
- POSTs whose `Sec-Fetch-Site` isn't `same-origin` (or `none`) are refused, which blocks cross-site form posts. Bodies over 1 MB are refused, except the logo upload (about 5 MB; waitress's own limit is set above it so the app can explain). Multipart bodies are parsed with `email.parser` (the `cgi` module is gone as of Python 3.13). HTML responses carry a strict Content-Security-Policy with no inline scripts, so JS goes in `static/app.js`.
- URL dates must be ISO dates; a non-Sunday redirects to the Sunday on or after it.

Conventions: wording on the pages is for a volunteer, not a developer (no "YAML", "scrape", "render"). Technical details go in a collapsed "Technical details" block. Before adding htmx, a framework, a database or a CSS build, weigh it against one more thing for the church to keep running.

## Code conventions

- The scrapers are async, with one `httpx.AsyncClient` from `utils.http_client()` (20s timeout) shared through the `SourceArchive`s. `sunday.fetch_readings` runs the two sources concurrently. The web server is threaded and sync; it calls the pipeline with `asyncio.run`.
- Parsing: `lxml.etree` + XPath for XML (`utils.xpath_text` for the first text match), `selectolax` (`HTMLParser`, `.css`, `.css_first`, `.text()`) for HTML. Helpers are in `utils.py`.
- Flat module layout with no package. Imports are plain `from utils import ...`. Web templates are in `templates/`, static files in `static/`.
- The YAML contract dataclasses live in `classes.py`, with `| None = None` defaults (the hand-edited `manual.yaml` ones default to `""`, since Typst prints them). Dataclasses used only inside one module (e.g. DCS `RowItem`) stay in that module. YAML is read and written through `yaml_io.py` (sync, no network dependencies, so `text_sizing` can use it).
- Style: 4-space indent, type hints with built-in generics (`list[str]`, `X | None`, not `typing.List`/`Optional`), imports grouped stdlib / third-party / local. Code should read without comments: add one only when the *why* isn't obvious from names. Don't leave commented-out code. Git has the history.

## Known quirks / rough edges

- Several scraped fields and helpers aren't rendered yet: DCS readings and prokeimenon, and `EpistlePageData.mode`. Task 002 decides whether to wire them in or delete them. The icon is different: it's unrendered on purpose and stays.
- `ipdb`/`ipython` are in the dev dependency group for debugging.
- The defaults in `data/parish.yaml` are real and specific to this parish. Change them only when asked; the church changes its own copy under Settings.
- A server in a datacenter may get Cloudflare bot checks from goarch.org more often than a home connection. The web UI reports that plainly, and the readings editor is the fallback.
