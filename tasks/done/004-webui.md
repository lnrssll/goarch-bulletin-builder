# Plan: build a webUI

## Goal

Right now, I run `uv run main.py` and it prints out a bunch of commands that I paste in other terminal panes. That is obviously not a great DX. I would rather have the code run behind a server with a webUI. That way, I can eventually deploy this and have someone else at the church run it. I am partial toward very simple user interfaces and dependable stacks with few dependencies. I would appreciate if you could look at my "stablestack" (`../../stablestack`) template repo as a reference for the simplicity I'm after. My goal for this site is: this church could keep using this code without any technical oversight for 10 years.

## What ten years without oversight asks for

1. **The upstream sites will change.** Over ten years, GOARCH will almost certainly change the DCS HTML or the chapel feed at least once. Task 002 already found `get_prokeimenon` broken by a DCS change. So a volunteer must be able to make a bulletin while the scraper is broken, and a site change on one source shouldn't block the other.
2. **Fewer moving parts rot slower.** Every dependency, build step and service is something that can break or need upgrading. The stack should be what's already here (Python + Typst), plus as little as possible.
3. **Pinned and reproducible.** Once it works, it should build and render the same way years later: pinned versions (`uv.lock`), pinned Typst, and fonts that don't depend on the host.
4. **Plain words for a volunteer.** No YAML, no terminal, no "scrape". Errors say what happened and what to do next.

## Decisions

- **Python, not stablestack's TypeScript.** The scrapers, sizing and Typst glue are Python. A Node server shelling out to Python would mean two toolchains to keep alive.
- **A plain WSGI app on the standard library, not Flask/FastAPI.** The stablestack rule "can this be done with the stdlib or a few lines of code?" applies. Routing, form parsing, cookies and a signed session are ~150 readable lines. WSGI (PEP 3333, 2010) runs unchanged on any Python server, so the server can be swapped with one line.
- **Three new dependencies (four packages):**
  - `jinja2` (+ `markupsafe`): about 300 lines of HTML with loops don't belong in f-strings, and autoescaping removes a whole class of mistakes. It's the most widely known Python template language, and stable since 2008.
  - `waitress`: a production WSGI server, pure Python, with no dependencies of its own. The stdlib servers are documented as not for production.
  - `typst` (typst-py): the Typst compiler as a wheel, pinned in `uv.lock`, so there's no binary to install on the server and dev and prod render with the same version. It uses Typst's embedded fonts only (`ignore_system_fonts=True`), so a font-less Docker image renders exactly like a laptop. Checked: pixel-identical to the typst 0.15.1 CLI on 2026-09-27, 05-17 and 09-20, with and without system fonts. It ships abi3 wheels, so it works on future Pythons. Capped `<0.16`, because `data/text_metrics.yaml` is calibrated against this release's rendering.
- **No database.** The build dirs already are the state, and the CLI reads and writes the same files. A database would be a second copy to keep in sync.
- **No htmx, no client framework, no CSS build.** No page needs partial updates: every action is a form POST and a redirect. `static/app.js` holds about 30 lines of conveniences, and everything works without it. The CSS is hand-written. That's simpler than stablestack, which needs Tailwind's build.
- **One shared password, set with `BULLETIN_PASSWORD`.** There are no accounts. Without a password there's no login, and the server refuses to listen beyond localhost. The session signing key is random per process, so there's no secret to configure; a restart only costs a login.
- **Sources succeed or fail independently.** Each source has its own `SourceArchive`, so a DCS change still lets the chapel readings through, and vice versa. Only what's missing has to be typed in.
- **A readings editor.** It corrects or types in the title, commemoration, prokeimenon, epistle, Alleluia and gospel, and it works when nothing could be fetched. This is the fallback for goal 1.
- **PDFs are a cache.** `render.py` re-renders when any input is newer than the last render. So edits made with the CLI, template changes after a deploy, and web saves all show up without a "rebuild" button.
- **Previews as PNG images, not an embedded PDF.** Every browser, including phones, shows them. Rendering the PNGs also gives the page count, so an overflow onto a third page is caught and shown.
- **The CLI stays.** `main.py` and `typst watch` still work, through the same pipeline (`sunday.fetch_readings`).
- **Deploy like stablestack:** Docker Compose with the app bound to `127.0.0.1`, host nginx and certbot. Data lives in two named volumes (`build`, `archive`), not in the git checkout, so a `git pull` on the server never collides with archived Sundays.

## What was built

| File | Role |
|---|---|
| `web.py` | WSGI app: routes, forms, login, flash messages, `main()` on waitress |
| `templates/` | `base`, `home`, `sunday` (the three steps), `readings` (editor), `login`, `error` |
| `static/style.css`, `static/app.js` | hand-written styles (light and dark), small progressive enhancements |
| `sunday.py` | one Sunday's build dir: dates, `fetch_readings` (the pipeline for CLI, web and tests), `load_readings`/`save_readings` |
| `manual.py` | replaces `manual_entry_template.py`: read/write `manual.yaml`, the template (now carrying the priests over from last week), placeholder checks, suggestions, the hymnal index |
| `render.py` | typst-py: `booklet.pdf`, `bulletin.pdf`, `preview-N.png` in the build dir, stale check |
| `classes.py` | + `ManualData`, `ManualHymnData`, `UpcomingServiceData` |
| `goarch_xml_feed.py`, `digital_chant_stand.py` | `run` split into `scrape` (already there) + `write`, so the pipeline writes only what succeeded |
| `bulletin.typ` | a hymn with no mode prints no "Mode" (the form allows leaving it blank) |
| `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `deploy/` | deployment, modeled on stablestack |
| `tests/` | + `test_web.py`, `test_sunday.py`, `test_manual.py`, `test_render.py`, `conftest.py` |

The weekly flow on the Sunday page:
1. **Readings.** "Download the readings". Afterwards the page shows a summary with the text size and layout, plus "Edit the readings" and "Download them again". Failures are explained in plain words ("goarch.org refused the download…", "the page didn't have the expected content…"), with the exception text under "Technical details". A partial failure says what's still missing.
2. **Hymns and services.** A form with fixed rows plus blank ones; clearing a row removes it. Hymn titles and priests are suggested from earlier Sundays (a `<datalist>` showing the mode and page used last time). Modes are a 1–8 menu. A bare page number becomes "p. 127". The hymnal's table of contents sits in a collapsed section. Placeholders ("Example", "Fr. X") are flagged until replaced.
3. **Print.** Previews of both sides of the booklet, "Download the booklet", and single A6 pages. A warning appears if the booklet runs past 2 pages.

## Verification (2026-09-24)

- `uv run pytest`: 76 passed, ~1.5s, all offline. The existing snapshot tests pass unchanged through the new pipeline. `test_render.py` renders every snapshot Sunday to a 2-page booklet.
- The real server (waitress), run from a scratch copy of the repo with a copy of `build/`:
  - Home page and all 37 existing Sundays show as "Ready".
  - 2026-09-27 renders in ~180ms.
  - One live download of 2026-10-04 from goarch.org took 12s and worked. Its `manual.yaml` template carried "Today: Fr. Joshua" over from 09-27's list.
  - Saving hymns via the form wrote the expected YAML.
  - A faked DCS bot-check page gave the partial-failure warning and "Still missing: the Alleluia verses".
  - Password mode: redirect to login, 401 on a wrong password, session cookie `Secure` behind `X-Forwarded-Proto: https`, 403 on a cross-site POST. Without a password, `--host 0.0.0.0` is refused.
  - Screenshots with headless Chromium at desktop and phone width.
- Every existing Sunday rendered with `render.ensure_rendered`, on a copy of `build/`. 32 of 37 come out at exactly 2 pages. The other 5 are old build dirs from before the current pipeline:
  - 01-11 and 01-18 have no `digital_chant_stand.yaml`, and 04-19 has no readings. The page shows them as missing.
  - 01-25 and 02-01 have no sizing fields in `feed.yaml`, so Typst fails and the page shows the error. `uv run text_sizing.py <date>` fixes them.
- **Docker: not built.** There's no container runtime on this machine. The image steps were rehearsed instead: a clean copy filtered by `.dockerignore`, `uv sync --locked --no-dev --no-install-project` with Python downloads off, then the image's `CMD` with a password. Still to check on a machine with Docker: `docker compose up --build`, that the `bulletin` user can write to the named volumes, and that `TZ` takes effect.

## Follow-ups (not done)

These, and the first-deployment checks above, are planned in `tasks/005-settings-and-follow-ups.md`.

- **Parish details as data.** The welcome text and the visiting priests' contact info are hard-coded in `bulletin_back.typ`. Over ten years they will change, and today that needs a code edit and a redeploy. Moving them into a YAML file in the data volume, with a settings page, would remove the last routine reason to call a developer.
- **A text-size override.** If the sizing model ever misjudges a Sunday, the volunteer can only print the extra page. A size field in the readings editor that bypasses the solver would be the escape hatch. Not added because the model hasn't overflowed on any Sunday so far, and task 001 keeps the solver model-only.
- **Hymns of the Day from DCS** (task 002): the form could be pre-filled with the scraped dismissal hymns once that parsing is reliable.
- **Cloudflare from a server IP.** The live download above ran from a home connection. Check it from the real server early on. If goarch.org challenges it every time, the readings editor carries the load until that's solved.
- **Backups** of the `build` volume are a manual command in `deploy/README.md`. A cron job on the server would make them automatic.
