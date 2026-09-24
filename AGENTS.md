# AGENTS.md

Guidance for coding agents working in this repository.

## What this is

A generator for a weekly Sunday Divine Liturgy bulletin (Lake Havasu Orthodox Church mission). A Python scraper collects the liturgical variables for a given Sunday from two Greek Orthodox Archdiocese (GOARCH) sources and writes them as YAML. Typst templates then read that YAML and render a printable PDF. A small web UI (`web.py`) runs the whole thing from one page per Sunday, so someone at the church can make the bulletin without a terminal. The goal is that the church can keep using it for about ten years without technical help, which is why the stack is small and boring (see "Web UI").

### Parish context

Lake Havasu is a mission with no resident priest. A visiting priest serves the Divine Liturgy on **Saturdays**, using the hymns and readings of the *following Sunday*. So:
- Everything is keyed by the Sunday's date (`main.py` requires a Sunday, and `build/`/`archive/` dirs use it). That is the liturgical day, even though the bulletin is handed out the day before.
- In `manual.yaml`, `upcoming_services` dates are Saturdays. The template's next service is `run_date + 6` days on purpose: the Saturday before the next Sunday.
- The visiting priests' contact details in `bulletin_back.typ` are real (see Known quirks).

```
web.py (browser) --+
main.py (CLI) -----+-> sunday.fetch_readings
                   |     +-> digital_chant_stand.py -> build/<date>/digital_chant_stand.yaml
                   |     +-> goarch_xml_feed.py ----> build/<date>/{feed,epistle,gospel}.yaml + icon image
                   |     |     (both fetch through utils.SourceArchive -> archive/<date>/, committed)
                   |     +-> manual.py -------------> build/<date>/manual.yaml   (template; then hand-edited)
                   |     +-> text_sizing.py --------> font size + page breaks into build/<date>/feed.yaml
                   +-> sunday.save_readings / manual.write   (the web forms)
                   +-> render.py (typst-py) --------> build/<date>/{booklet,bulletin}.pdf + preview-N.png

typst CLI (bulletin.typ / booklet.typ) <-- build/<date>/*.yaml --> out/<date>.pdf   (CLI workflow)
```

## Commands

Run everything from the repo root. Both the Python code and Typst use paths relative to the root (`build/`, `assets/`).

```sh
uv sync                                 # install deps (Python >= 3.13)
uv run web.py                           # web UI on http://127.0.0.1:8000 (no password when local)
uv run web.py --port 8080 --host 0.0.0.0  # beyond this computer: needs BULLETIN_PASSWORD set
uv run main.py                          # scrape data for the next upcoming Sunday
uv run main.py 27 9 2026                # scrape a specific Sunday: DAY MONTH YEAR (YEAR may be 2-digit)
uv run main.py 27 9 2026 --refresh      # re-download sources that are already in archive/

uv run text_sizing.py 2026-09-27            # re-size an existing build dir (rewrites the sizing fields in feed.yaml)
uv run text_sizing.py --explain 2026-09-27  # show the sizing model for one date (read-only, offline)
uv run text_sizing.py --report              # sizing for every date in build/ (read-only, offline)
uv run pytest                               # all tests, offline
UPDATE_SNAPSHOTS=1 uv run pytest            # regenerate tests/snapshots/ after an intended output change

# render; the date input selects build/<date>/
typst compile --input date=2026-09-27 booklet.typ out/2026-09-27.pdf    # 2-up A5 booklet for printing
typst compile --input date=2026-09-27 bulletin.typ out/2026-09-27.pdf   # plain A6 pages
typst watch   --input date=2026-09-27 booklet.typ out/2026-09-27.pdf    # live re-render while editing
```

`main.py` prints a ready-to-paste `typst watch` command at the end. It is written for nushell, the user's shell.

Deployment (Docker + nginx + certbot, modeled on the user's `stablestack` template) is in `deploy/README.md`. There's no container runtime on the dev machine, so the `Dockerfile` has been checked by rehearsing its steps (clean copy per `.dockerignore`, `uv sync --locked --no-dev`, the same `CMD`), not by building it.

Notes:
- `cli.parse_run_options` rejects dates that aren't Sundays and years before the current year.
- Tests (`tests/`), no linter config or CI. All offline, ~2s:
  - `test_text_sizing.py`: synthetic tests of the sizing model.
  - `test_scrapers.py`: replays every Sunday in `archive/` offline through `sunday.fetch_readings`, then compares the scraped YAML with `tests/snapshots/<date>/`. A snapshot diff after a scraper change is either a regression or an intended change; regenerate the snapshots only for the latter. To add a regression case, commit its `archive/<date>/` and generate its snapshot.
  - `test_source_archive.py`: archive caching, using `httpx.MockTransport`.
  - `test_sunday.py`: the fetch pipeline (one source failing, bot-check pages) and the readings editor's load/save.
  - `test_manual.py`: `manual.yaml` reading, the template and its carry-over from last week, suggestions.
  - `test_render.py`: every snapshot Sunday renders to a 2-page booklet with typst-py; re-render only when an input changes.
  - `test_web.py`: drives the WSGI app directly (no server): the Sunday workflow, forms, login, cross-site and oversized posts.
  - `conftest.py` has the `site` fixture: a temp copy of the repo root (Typst files, `data/`, `assets/`, `templates/`, `static/`) as the working directory, so tests never touch the real `build/`.
- Don't bulk-download past Sundays. GOARCH is behind Cloudflare and serves bot-check pages to scripted traffic, and older DCS pages are gone. Test against what's already in `archive/`.
- The `Makefile` is stale: it references `webscraper/main.py` and is gitignored. Don't use it.
- `build/` and `out/` are gitignored. Everything they hold is generated, except `manual.yaml` (see below).
- Never run the web server or `main.py` against the real `build/` to try something out: it holds the user's hand-edited `manual.yaml` files. Use a scratch copy of the repo.

## Data sources

Every fetch goes through `utils.SourceArchive(root, client, refresh)`, which caches the raw XML and HTML under `archive/<date>/` (`chapel.xml`, `epistle.xml`, `gospel.xml`, `saints/<contentid>.xml`, `icon/<file>.jpg`, `dcs.html`). An archived source is never downloaded again unless `--refresh` (or the web UI's "Download them again") is given. New downloads are held in memory and written by `archive.save()` only after that source's scrape succeeds, so an error page or a Cloudflare challenge never gets archived. With `client=None` the archive is offline and raises `NotArchived` for anything missing; the tests work this way. `archive/` is committed: commit each new Sunday's sources along with any code change. (A deployed server archives into its own Docker volume; nothing there is committed.)

Each source module has `async scrape(run_date, archive)`, which returns dataclasses, and `write(data, out_dir)`, which writes the YAML. A page that doesn't parse raises `utils.ScrapeError`, naming the source, the URL and what was missing.

`sunday.fetch_readings` is the one pipeline, used by `main.py`, the web UI and the snapshot tests. It lists the sources in `sunday.SOURCES` (name, what it provides, the files it writes) and scrapes them concurrently, each with its own `SourceArchive`. A source that fails (`ScrapeError` or `httpx.HTTPError`) archives and writes nothing, and its existing files are kept; the other source is still archived and written. That way a site change on one side leaves only that part to type in by hand. If every source fails, nothing is written at all. Afterwards it writes the `manual.yaml` template if there is none, and runs `text_sizing` once all four readings files exist. It returns a `FetchResult` with the failures. `main.py` prints them and exits 1; the web UI explains them in plain words (`web.explain`).

### GOARCH Online Chapel XML feed (`goarch_xml_feed.py`)
- Index: `https://onlinechapel.goarch.org/daily?date=M/D/YYYY` returns an `<onlinechapel>` XML doc with the lectionary title, formatted date, reading URLs (`reading[type="E"|"G"]`), saint/feast URLs, and the icon URL.
- The epistle and gospel URLs return XML. The English text is under `translation[@xml:lang="en"]`, and the body is an HTML string parsed with selectolax.
- `identify_icon` fetches every saint/feast XML at the same time (all of them are archived) and returns the title of whichever one uses the day's icon. That title becomes `icon_title`, or `''` if it matches the lectionary title.
- XML is parsed with `recover=True` because the feed is sometimes malformed.
- The icon of the day (`icon_src`) is downloaded, archived, and copied into the build dir as `icon_filename`. It is deliberately **not** printed in the bulletin: an icon is holy and must be burned or buried rather than thrown away, and bulletins get thrown away. It's kept so an icon can someday be printed separately. Don't remove the icon code. A failed icon download only warns.

### Digital Chant Stand (`digital_chant_stand.py`)
- URL: `https://dcs.goarch.org/goa/dcs/h/s/YYYY/MM/DD/li2/en/`, the Divine Liturgy service HTML.
- `iter_row_items` flattens `tbody > tr > td > *` into `RowItem(kind, text, node)`. `kind` is the `<p>`'s CSS class with non-letters removed (e.g. `designation`, `source`, `mode`, `hymn`, `dialog`, `chapverse`, `reading`, `verse`, `mixed`), or `media`.
- `group_by_sections` splits the rows into sections keyed by `designation` text or by a `mixed` row starting with "Alleluia". A `source` row comes *before* its title, so it is held back and attached to the next section.
- Extraction depends on exact section titles from the page: `"Hymns after the Entrance."` ... `"Trisagios Hymn"` for dismissal hymns; `"The Epistle"`, `Alleluia*`, `"The Gospel"` ... `"Hymn to the Theotokos."` for readings. Also on `data-key*=` attribute selectors (`alleluia`, `Epistle`, `Gospel`, `prokeimenon`). A missing Alleluia is a `ScrapeError`. A failure in the unrendered dismissal hymns only prints a warning.
- Only `alleluia` from DCS is actually rendered. Epistle and gospel text come from the XML feed. `get_scripture_reading_data`, `get_reading`, `get_prokeimenon` and `get_alleluia_mode` exist but aren't wired in, and `get_prokeimenon` no longer matches the live markup (see `tasks/002`).
- `get_alleluia_mode` numbers modes 1-8: "pl. N" is N+4, and "Grave" is 7.

### Not used
- The GOARCH calendar site is blocked by Cloudflare bot protection, so there is no scraper for it.
- `notes.md` lists possible alternative sources (Orthocal API, Ponomar typicon).

## Build directory contract (`build/<YYYY-MM-DD>/`)

The Python side writes these files and the Typst side reads them. Keep field names in sync on both sides. The dataclasses in `classes.py` are serialized with `asdict` -> `yaml.safe_dump`.

| File | Written by | Key fields used in Typst |
|---|---|---|
| `feed.yaml` | `goarch_xml_feed.write` (`DailyFeedPageData`), then `text_sizing.run` fills in the sizing fields | `lectionary_title`, `formatted_date`, `icon_title`, `text_size_factor` (percent of `base_size_pt`), `alleluia_page_break`, `gospel_page_break`. Diagnostics only: `font_size_pt`, `layout`, `page_fill` |
| `epistle.yaml` | `EpistlePageData` | `book`, `chapverse`, `prokeimenon`, `verse`, `text[]` |
| `gospel.yaml` | `GospelPageData` | `book`, `chapverse`, `text[]` |
| `digital_chant_stand.yaml` | `LiturgyVariablesPageData` | `alleluia[]` (`dismissal_hymns` is scraped but not rendered) |
| `manual.yaml` | `manual.write_template`, then the web form (`manual.write`) or a text editor | `dismissal_hymns[] {title, mode, page}` (`mode` may be null), `upcoming_services[] {date, priest}` |
| `<icon_filename>` (jpg) | `goarch_xml_feed.write` | not printed on purpose (see the icon note above). `feed.yaml` has `icon_filename` and `icon_title` |
| `booklet.pdf`, `bulletin.pdf`, `preview-N.png` | `render.py` | outputs, not read by anything; the booklet's mtime marks the render as current |

The readings files can also be written by the web UI's readings editor (`sunday.save_readings`), which updates only the fields it shows and keeps the rest (URLs, icon, `mode`, `dismissal_hymns`). Saved paragraphs have their whitespace collapsed, which Typst does anyway.

**`manual.yaml` is hand-edited, and its contents can't be regenerated.** `manual.write_template` writes a template only if the file doesn't exist; nothing else writes it except the user saving the web form. Never overwrite or delete an existing one. The user fills in the "Hymns of the Day" list (title, mode, and page in their hymnal) and the upcoming-services list. The template carries the priests over: an entry in the most recent earlier week's list (up to 8 weeks back) dated this Sunday's Saturday becomes "Today", later ones are kept, and next Saturday is added if missing. Placeholders ("Example" hymn, "Fr. X") are flagged by `manual.unfinished`. `manual.read` is tolerant of hand edits (missing keys, string modes). `data/table-of-contents.txt` is a reference index of hymnal page numbers (`title | page | section`); the web UI shows it under "Page numbers in the hymnal".

Re-running `main.py` for a date overwrites every other file in that date's build dir.

## Layout logic

- **Geometry** lives in `data/layout.yaml` (page size, margins, booklet gutter, base font size, leading, paragraph spacings, indents). `bulletin.typ`, `booklet.typ` and `text_sizing.py` all read it, so change page setup there rather than in the `.typ` files.
- **Text size and page breaks** (`text_sizing.py`, summary in `docs/text_sizing.md`, design in `tasks/done/001-text-sizing.md`). One font size is used for both reading pages. The readings are modeled as blocks (epistle with prokeimenon, alleluia, gospel), each with a height that depends on the font size: wrapped lines per paragraph, paragraph spacing, and a fixed em-height for headings and gaps. There are three layout candidates: `split_before_alleluia` (Alleluia goes with the Gospel), `split_before_gospel`, and `flow` (no forced break). The solver finds the largest size, in 0.1pt steps up to `base_size_pt`, at which each layout fits. It picks the layout with the largest size and breaks ties in that order. There is no minimum size, but it prints a notice below 7pt. It reads only the YAML in the build dir, so it can be re-run without re-scraping. It must not import the scraper modules or `httpx`.
- **Model constants** are in `data/text_metrics.yaml`. They were checked against rendered PDFs for all of `build/` (Jan-Sep 2026): no overflow, binding pages ~85-95% full. They are deliberately conservative, most of all below ~8pt. If PDFs come out consistently underfilled or overflowing, adjust `glyph_advance_em` first. After changing a constant, run `--report` and compile a spread of dates (short, typical, 2026-05-17) and check the page count and fill.
- `bulletin.typ` defines content blocks (`front_page`, `readings(sep:)`, `back_page`) *and* a standalone A6 layout. `booklet.typ` imports those blocks and imposes them two-up on A5-landscape sheets (sheet 1: back|front; sheet 2: readings across two columns, with `colbreak` in place of `pagebreak`). Put content changes in `bulletin.typ`, and keep them as reusable blocks so the booklet picks them up. Page setup belongs in each file's layout section.
- `bulletin_back.typ` holds the static welcome text, the contact info for the visiting priests, the logo, and the QR code. It reads `upcoming_services` from `manual.yaml`.
- `build_path.typ` turns `--input date=...` into `build/<date>/`.
- **Rendering in Python** (`render.py`) uses the `typst` package (typst-py), which bundles the compiler, pinned to `<0.16` in `pyproject.toml` because the text metrics are calibrated against this release's rendering. Its output was checked pixel-identical to the typst 0.15.1 CLI. It passes `ignore_system_fonts=True`, so only Typst's embedded fonts are used and the output is the same on any machine (the Docker image has no system fonts). `render.ensure_rendered(date)` re-renders when any input (the build dir's YAML, `*.typ`, `data/layout.yaml`, `assets/`) is newer than `booklet.pdf`, and returns the booklet's page count: 2 is right (outside and inside of one folded sheet), more means the readings overflowed, and the web page warns. A Typst error becomes a `render.RenderError`.

## Web UI (`web.py`)

The stack follows the user's `stablestack` template, translated to Python: few dependencies, server-rendered HTML, nothing that needs a build step.

- **A plain WSGI app on the standard library.** `ROUTES` is a table of `(method, regex, handler)`. Handlers are functions `handler(req, *url_groups) -> Response` and raise `NotFound` for a 404. Helpers: `page` (render a template), `redirect` (303, with an optional one-time message), `plain`. No web framework: WSGI (PEP 3333) runs unchanged on any Python server.
- **`waitress`** serves it (pure Python, no dependencies of its own). **`jinja2`** renders `templates/*.html` with autoescaping and `StrictUndefined`.
- **No database.** The build dirs are the state, the same files the CLI reads and writes.
- **No client-side framework, no JS or CSS build.** Plain forms and full page loads. `static/app.js` only adds conveniences (disables buttons while a form is sent, confirms before re-downloading, warns about unsaved changes); every page works without it. `static/style.css` is hand-written, with a dark mode.

Flow: each change is a form POST that does its work and redirects to the Sunday page. The redirect carries a one-time message (`Flash`) in the `bulletin_flash` cookie. The Sunday page re-renders the PDFs when they're stale. Scrapes, saves and renders take turns on `WORK_LOCK`, since they all rewrite build dirs. The scrape runs inside the request (`asyncio.run`) and takes ~10s, up to a minute, so nginx's timeout is raised in `deploy/`.

| Route | Does |
|---|---|
| `GET /` | next Sunday, a date picker, every Sunday in `build/` with a status |
| `GET /sundays?date=` | opens the Sunday on or after a date (a service Saturday opens its Sunday) |
| `GET /sundays/<date>` | the three steps: readings, hymns and services, print (preview images of both booklet sides) |
| `POST /sundays/<date>/fetch` | `sunday.download_readings`; `refresh=yes` re-downloads |
| `POST /sundays/<date>/details` | writes `manual.yaml` from the form; a row with no title (hymns) or no date and priest (services) is dropped; a bare page number becomes "p. N" |
| `GET`/`POST /sundays/<date>/readings` | the readings editor, which also works when nothing was fetched |
| `GET /sundays/<date>/{booklet,bulletin}.pdf` | `?download=1` for an attachment |

Safety:
- With `BULLETIN_PASSWORD` set, every page but `/login` and `/static/` needs a session: an HMAC-signed expiry in an HttpOnly, SameSite=Lax cookie, marked `Secure` over HTTPS (waitress trusts `X-Forwarded-Proto`; the container is only reachable from the host's nginx). The signing key is random per process, so a restart logs everyone out. Failed logins wait a second. Without a password there's no login, and `main()` refuses to listen beyond localhost.
- POSTs whose `Sec-Fetch-Site` isn't `same-origin` (or `none`) are refused, which blocks cross-site form posts. Bodies over 1 MB are refused. HTML responses carry a strict Content-Security-Policy with no inline scripts, so JS goes in `static/app.js`.
- URL dates must be ISO dates; a non-Sunday redirects to the Sunday on or after it.

Conventions: wording on the pages is for a volunteer, not a developer (no "YAML", "scrape", "render"). Technical details go in a collapsed "Technical details" block. Before adding htmx, a framework, a database or a CSS build, weigh it against one more thing for the church to keep running.

## Code conventions

- The scrapers are async, with one `httpx.AsyncClient` from `utils.http_client()` (20s timeout) shared through the `SourceArchive`s. `sunday.fetch_readings` runs the two sources concurrently. The web server is threaded and sync; it calls the pipeline with `asyncio.run`.
- Parsing: `lxml.etree` + XPath for XML (`utils.xpath_text` for the first text match), `selectolax` (`HTMLParser`, `.css`, `.css_first`, `.text()`) for HTML. Helpers are in `utils.py`.
- Flat module layout with no package. Imports are plain `from utils import ...`. Web templates are in `templates/`, static files in `static/`.
- The YAML contract dataclasses live in `classes.py`, with `| None = None` defaults (the hand-edited `manual.yaml` ones default to `""`, since Typst prints them). Dataclasses used only inside one module (e.g. DCS `RowItem`) stay in that module. YAML is read and written through `yaml_io.py` (sync, no network dependencies, so `text_sizing` can use it).
- Style: 4-space indent, type hints with built-in generics (`list[str]`, `X | None`, not `typing.List`/`Optional`), imports grouped stdlib / third-party / local. Code should read without comments: add one only when the *why* isn't obvious from names. Don't leave commented-out code. Git has the history.

## Known quirks / rough edges

- Several scraped fields and helpers aren't rendered yet: saint/feast hymns (`process_saint_feast_page`), DCS readings and prokeimenon, and `EpistlePageData.mode`. Task 002 decides whether to wire them in or delete them. The icon is different: it's unrendered on purpose and stays.
- `ipdb`/`ipython` are in the dev dependency group for debugging.
- Contact info and parish details in `bulletin_back.typ` are real and specific to this parish. Change them only when asked. Because they live in a Typst file, changing them needs a code edit and a redeploy; task 004 lists moving them into editable data as a follow-up.
- A server in a datacenter may get Cloudflare bot checks from goarch.org more often than a home connection. The web UI reports that plainly, and the readings editor is the fallback.
