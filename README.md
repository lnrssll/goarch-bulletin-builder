# LHC Mission Bulletin Builder

This repo contains a python application and typst files for building a pdf bulletin for a given Sunday liturgy, with all its relevant liturgical variables.

The python application will use the Goarch XML API and the Digital Chant Stand webpage to gather those variables and structure them as a usable data for the typst files to consume.

```sh
uv sync
uv run main.py            # scrape the next Sunday into build/<date>/ (sources cached in archive/<date>/)
# edit build/<date>/manual.yaml (hymns of the day, upcoming services)
typst compile --input date=2026-09-27 booklet.typ out/2026-09-27.pdf
uv run pytest
```

See `AGENTS.md` for how it all fits together.
