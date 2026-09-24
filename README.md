# LHC Mission Bulletin Builder

Makes the printed bulletin for a Sunday's Divine Liturgy: the readings, the prokeimenon and the Alleluia from goarch.org, the Hymns of the Day and the upcoming services typed in by hand, laid out by Typst as a folded A6 booklet.

## Web UI

```sh
uv sync
uv run web.py             # open http://127.0.0.1:8000
```

Each Sunday has one page with three steps: download the readings, fill in the hymns and services, then download the booklet PDF. The readings can also be typed in or corrected by hand, for when goarch.org is down or has changed.

To run it on a server for others to use, see [`deploy/README.md`](deploy/README.md).

## Command line

```sh
uv run main.py            # scrape the next Sunday into build/<date>/ (sources cached in archive/<date>/)
# edit build/<date>/manual.yaml (hymns of the day, upcoming services)
typst compile --input date=2026-09-27 booklet.typ out/2026-09-27.pdf
uv run pytest
```

See `AGENTS.md` for how it all fits together.
