# AGENTS.md

Guidance for coding agents working in this repository.

## What this is

A generator for a weekly Sunday Divine Liturgy bulletin (Lake Havasu Orthodox Church mission). A Python scraper collects the liturgical variables for a given Sunday from two Greek Orthodox Archdiocese (GOARCH) sources and writes them as YAML. Typst templates then read that YAML and render a printable PDF.

```
main.py -+-> digital_chant_stand.py ---> build/<date>/digital_chant_stand.yaml
         +-> goarch_xml_feed.py -------> build/<date>/{feed,epistle,gospel}.yaml + icon image
         +-> manual_entry_template.py -> build/<date>/manual.yaml   (hand-edited)
         +-> text_sizing.py -----------> font size + page breaks into build/<date>/feed.yaml

typst (bulletin.typ / booklet.typ) <-- build/<date>/*.yaml --> out/<date>.pdf
```

## Commands

Run everything from the repo root. Both the Python code and Typst use paths relative to the root (`build/`, `assets/`).

```sh
uv sync                                 # install deps (Python >= 3.13)
uv run main.py                          # scrape data for the next upcoming Sunday
uv run main.py 27 9 2026                # scrape a specific Sunday: DAY MONTH YEAR (YEAR may be 2-digit)

uv run text_sizing.py 2026-09-27            # re-size an existing build dir (rewrites the sizing fields in feed.yaml)
uv run text_sizing.py --explain 2026-09-27  # show the sizing model for one date (read-only, offline)
uv run text_sizing.py --report              # old vs new sizing for every date in build/ (read-only, offline)
uv run pytest                               # unit tests for text_sizing.py

# render; the date input selects build/<date>/
typst compile --input date=2026-09-27 booklet.typ out/2026-09-27.pdf    # 2-up A5 booklet for printing
typst compile --input date=2026-09-27 bulletin.typ out/2026-09-27.pdf   # plain A6 pages
typst watch   --input date=2026-09-27 booklet.typ out/2026-09-27.pdf    # live re-render while editing
```

`main.py` prints a ready-to-paste `typst watch` command at the end. It is written for nushell, the user's shell.

Notes:
- `main.py` raises if the date is not a Sunday. `cli.py` also rejects years before the current year.
- The only tests are for `text_sizing.py` (`tests/`). There's no linter config or CI. To check a scraper change, re-run the scraper for a known Sunday and compile the PDF. Real data lives in `build/`, which has many past dates to compare against.
- The `Makefile` is stale: it references `webscraper/main.py` and is gitignored. Don't use it.
- `build/` and `out/` are gitignored. Everything they hold is generated, except `manual.yaml` (see below).

## Data sources

### GOARCH Online Chapel XML feed (`goarch_xml_feed.py`)
- Index: `https://onlinechapel.goarch.org/daily?date=M/D/YYYY` returns an `<onlinechapel>` XML doc with the lectionary title, formatted date, reading URLs (`reading[type="E"|"G"]`), saint/feast URLs, and the icon URL.
- The epistle and gospel URLs return XML. The English text is under `translation[@xml:lang="en"]`, and the body is an HTML string parsed with selectolax.
- `identify_icon` fetches every saint/feast XML at the same time and returns the title of whichever one uses the day's icon. That title becomes `icon_title`, or `''` if it matches the lectionary title.
- XML is parsed with `recover=True` because the feed is sometimes malformed.

### Digital Chant Stand (`digital_chant_stand.py`, `get_dismissal_hymns.py`, `get_scripture_reading.py`)
- URL: `https://dcs.goarch.org/goa/dcs/h/s/YYYY/MM/DD/li2/en/`, the Divine Liturgy service HTML.
- `iter_row_items` flattens `tbody > tr > td > *` into `RowItem(kind, text, node)`. `kind` is the `<p>`'s CSS class with non-letters removed (e.g. `designation`, `source`, `mode`, `hymn`, `dialog`, `chapverse`, `reading`, `verse`, `mixed`), or `media`.
- `group_by_sections` splits the rows into sections keyed by `designation` text or by a `mixed` row starting with "Alleluia". A `source` row comes *before* its title, so it is held back and attached to the next section.
- Extraction depends on exact section titles from the page: `"Hymns after the Entrance."` ... `"Trisagios Hymn"` for dismissal hymns; `"The Epistle"`, `Alleluia*`, `"The Gospel"` ... `"Hymn to the Theotokos."` for readings. Also on `data-key*=` attribute selectors (`alleluia`, `Epistle`, `Gospel`, `prokeimenon`). If DCS changes its markup or wording, these break silently or with `StopIteration`/`IndexError`.
- Only `alleluia` from DCS is actually rendered. Epistle and gospel text come from the XML feed. `get_scripture_reading_data`, `get_epistle`, `get_gospel`, and `get_prokeimenon` exist but aren't wired in.
- Grave mode appears as "Grave" rather than a number. It maps to mode 7 (see `get_alleluia`).

### Not used
- The GOARCH calendar site is blocked by Cloudflare bot protection (`goarch_calendar` is commented out in `main.py`).
- `notes.md` lists possible alternative sources (Orthocal API, Ponomar typicon).

## Build directory contract (`build/<YYYY-MM-DD>/`)

The Python side writes these files and the Typst side reads them. Keep field names in sync on both sides. The dataclasses in `classes.py` are serialized with `asdict` -> `yaml.safe_dump`.

| File | Written by | Key fields used in Typst |
|---|---|---|
| `feed.yaml` | `goarch_xml_feed.run` (`DailyFeedPageData`), then `text_sizing.run` fills in the sizing fields | `lectionary_title`, `formatted_date`, `icon_title`, `icon_filename`, `text_size_factor` (percent of `base_size_pt`), `alleluia_page_break`, `gospel_page_break`. Diagnostics only: `font_size_pt`, `layout`, `page_fill` |
| `epistle.yaml` | `EpistlePageData` | `book`, `chapverse`, `prokeimenon`, `verse`, `text[]` |
| `gospel.yaml` | `GospelPageData` | `book`, `chapverse`, `text[]` |
| `digital_chant_stand.yaml` | `LiturgyVariablesPageData` | `alleluia[]` (`dismissal_hymns` is scraped but not rendered) |
| `manual.yaml` | `manual_entry_template.run` | `dismissal_hymns[] {title, mode, page}`, `upcoming_services[] {date, priest}` |
| `<icon>.jpg` | `download_image` | not rendered right now (cover image removed) |

**`manual.yaml` is hand-edited, and its contents can't be regenerated.** `manual_entry_template.run` writes a placeholder only if the file doesn't exist. Never overwrite or delete an existing one. The user fills in the "Hymns of the Day" list (title, mode, and page in their hymnal) and the upcoming-services list. `data/table-of-contents.txt` is a reference index of hymnal page numbers (`title | page | section`) for filling in `page`. No code reads it.

Re-running `main.py` for a date overwrites every other file in that date's build dir.

## Layout logic

- **Geometry** lives in `data/layout.yaml` (page size, margins, booklet gutter, base font size, leading, paragraph spacings, indents). `bulletin.typ`, `booklet.typ` and `text_sizing.py` all read it, so change page setup there rather than in the `.typ` files.
- **Text size and page breaks** (`text_sizing.py`, design in `tasks/001-text-sizing.md`). One font size is used for both reading pages. The readings are modeled as blocks (epistle with prokeimenon, alleluia, gospel), each with a height that depends on the font size: wrapped lines per paragraph, paragraph spacing, and a fixed em-height for headings and gaps. There are three layout candidates: `split_before_alleluia` (Alleluia goes with the Gospel), `split_before_gospel`, and `flow` (no forced break). The solver finds the largest size, in 0.1pt steps up to `base_size_pt`, at which each layout fits. It picks the layout with the largest size and breaks ties in that order. There is no minimum size, but it prints a notice below 7pt. It reads only the YAML in the build dir, so it can be re-run without re-scraping. It must not import the scraper modules or `httpx`.
- **Model constants** are in `data/text_metrics.yaml`. They were checked against rendered PDFs for all of `build/` (Jan-Sep 2026): no overflow, binding pages ~85-95% full. They are deliberately conservative, most of all below ~8pt. If PDFs come out consistently underfilled or overflowing, adjust `glyph_advance_em` first. After changing a constant, run `--report` and compile a spread of dates (short, typical, 2026-05-17) and check the page count and fill.
- `bulletin.typ` defines content blocks (`front_page`, `readings(sep:)`, `back_page`) *and* a standalone A6 layout. `booklet.typ` imports those blocks and imposes them two-up on A5-landscape sheets (sheet 1: back|front; sheet 2: readings across two columns, with `colbreak` in place of `pagebreak`). Put content changes in `bulletin.typ`, and keep them as reusable blocks so the booklet picks them up. Page setup belongs in each file's layout section.
- `bulletin_back.typ` holds the static welcome text, the contact info for the visiting priests, the logo, and the QR code. It reads `upcoming_services` from `manual.yaml`.
- `build_path.typ` turns `--input date=...` into `build/<date>/`.

## Code conventions

- Async throughout with `httpx.AsyncClient` (20s timeout). Each source module exposes `async def run(run_date: date, out_dir: Path)`, and `main.py` calls them in order.
- Parsing: `lxml.etree` + XPath for XML, `selectolax` (`HTMLParser`, `.css`, `.css_first`, `.text()`) for HTML. Helpers are in `utils.py`.
- Flat module layout with no package. Imports are plain `from utils import ...`.
- Parsed data goes into `@dataclass`es in `classes.py` with `| None = None` defaults.
- Style: 4-space indent, type hints, little commenting. Match the surrounding code.

## Known quirks / rough edges

- `process_saint_feast_page` calls `list.push` (it should be `append`). It's unused right now.
- `DISMISSAL_HYMN_CHAR_LIMIT` in `goarch_xml_feed.py` is unused.
- `pyproject.toml` still says `name = "goarch-web-scraper"` with a placeholder description. `ipdb`/`ipython` are debugging conveniences, and `pillow` isn't imported anywhere.
- Contact info and parish details in `bulletin_back.typ` are real and specific to this parish. Change them only when asked.
