# Plan: parish settings, and the follow-ups from the web UI

## Goal

> editable pages for all of the priest contact info, back cover, etc. basically every field editable, but that should be buried in the ui very deeply in settings or something. And of course anything else you found as a follow up.

This carries on task 004 (`tasks/done/004-webui.md`), toward the same goal: the church keeps using this for ten years without technical help. Today, a new visiting priest, a new phone number or a new website means a code edit and a redeploy, so a developer is needed. Part 1 fixes that. Part 2 lists everything else task 004 turned up.

## Part 1: parish settings

### Everything fixed in the printed bulletin today

| Where | What | Proposal |
|---|---|---|
| `bulletin_back.typ:7-13` | "Welcome" heading and its three paragraphs | editable |
| `bulletin_back.typ:25-45` | "Contact Information": two priests, each name, church, city, email, phone | editable, as a list (add, remove, reorder) |
| `bulletin_back.typ:56-57` | QR code image (`assets/lhoc-qr.png`) and the website printed next to it, broken by hand into "lakehavasu / orthodox / church.org" | editable: website address, plus the printed text one line per row |
| `bulletin.typ:26`, `bulletin_back.typ:51` | logo (`assets/logo.webp`), front and back | editable: upload a new image |
| `bulletin.typ:32` | "On {date}, we commemorate" | editable (advanced) |
| `bulletin.typ:44`, `:60`, `:74`, `:83`, `:90`; `bulletin_back.typ:15`, `:25` | headings: "Hymns of the Day", "The Reading is from", "The Prokeimenon", "Verse:", "The Alleluia", "Upcoming Services", "Contact Information" | editable (advanced) |
| `manual.py:25` | the Liturgy is on the Saturday before the Sunday (the next service is `run_date + 6`) | editable: "Saturday before" or "Sunday". If the mission gets a resident priest, this is wrong for every week. |
| `manual.py:105`, `:11` | "Today" label in the upcoming services, "Fr. X" placeholder | "Today" editable (advanced); the placeholder stays |
| `data/table-of-contents.txt` | the hymnal's page index | editable (advanced): paste a new index, for a new hymnal edition |
| `templates/base.html:7,14` | "Bulletin Builder" in the web page header (not printed) | editable: parish name |
| `data/layout.yaml`, `data/text_metrics.yaml` | page size, margins, base font size; the sizing model's calibration | **not** editable (see below) |
| `BULLETIN_PASSWORD`, `TZ` | password and time zone, in `/etc/bulletin.env` and `docker-compose.yml` | not editable: server config |

Why not the layout numbers: `text_metrics.yaml` is calibrated against these exact page sizes and fonts (task 001). A wrong margin or base size would overflow or shrink every Sunday, and a volunteer can't see why or undo it. Changing them is a developer job: re-run `--report` and check a spread of dates.

### Where the settings live

- **Defaults committed in `data/parish.yaml`**: today's values, moved out of the `.typ` files. A fresh checkout renders exactly as today.
- **The church's own copy in `settings/`** at the repo root: `parish.yaml`, plus uploaded images. It's gitignored, and in Docker it's a new named volume (`settings:/app/settings`), so a redeploy or `git pull` never overwrites it. It must be under the repo root because Typst only reads files under its root.
- **Typst can't test whether a file exists**, and `yaml()` on a missing file is an error. So one Python function makes sure `settings/parish.yaml` exists and is complete before anything renders:
  - it copies the defaults on first use;
  - it fills in fields added by later code versions with their defaults;
  - it runs in `render.py`, and in `main.py` for the CLI `typst compile` workflow.
  - Typst then reads only `settings/parish.yaml`.
- **Uploaded images are named by content hash** (`settings/images/<hash>.webp`), and `parish.yaml` refers to them by path. Old versions stay valid, so undo works for images too. Accept PNG, JPEG and WebP only, checked by their first bytes. Try a render before switching over, and if Typst can't read the image, refuse it and keep the old one.
- **Render cache**: add `settings/` to `render.inputs`, so every Sunday re-renders after a change.
- **Alternative: `build/settings/`.** One volume and one backup instead of two, but `build/` means "one folder per Sunday", and `manual.suggestions` and anything else that iterates it would have to skip it. Not recommended.

### Buried in the UI

- **No header link.** Only a small "Settings" link in the page footer.
- **`/settings`** opens with a warning: "These change every bulletin. Most weeks you don't need anything here." Below it is a list of sections, each on its own page with its own form:
  - Welcome text
  - Contact information
  - Website and QR code
  - Logo
  - When the Liturgy is served
  - Advanced, collapsed: headings and wording, the hymnal index, the parish name
- **One form per page.** Small forms mean a mistake can only touch one thing.
- **Check each save with a picture.** Each save redirects to a preview of the outside of the booklet (back and front) for the next Sunday, or the latest one with readings. If the change pushes the booklet past 2 pages, it says so plainly and offers "Undo".
- **Undo.** Each save first copies the current `parish.yaml` to `settings/history/<timestamp>.yaml`, keeping the last 50. `/settings` has "Undo the last change", and each section has "Put back the original" to restore the committed defaults.
- **Plain text only.** Typst prints YAML strings literally, so a `#`, `@`, `*` or `$` typed by a volunteer can't break the document (that's why the email addresses are written `#("...")` today). Paragraphs are split on blank lines, as in the readings editor (`web.paragraphs`).
- **Contacts are labelled fields** (name, church, city, email, phone). Empty fields aren't printed. Rows are added and removed like the hymn rows. Typst lays out any number of contacts in two columns, and overflow is caught by the preview.
- **Tie-in:** contact names come first in the "Priest" suggestions on the Sunday form.

### The code this touches

- **`bulletin.typ`, `bulletin_back.typ`**: read everything in the table from `settings/parish.yaml`. Images use root-relative paths (`/settings/images/...`).
- **`manual.py`**:
  - `service_day` follows the setting;
  - the "Today" label comes from settings;
  - the date hint in `templates/home.html` ("Picking the Saturday of a service…") follows it too.
  - Existing `manual.yaml` files aren't rewritten.
- **`web.py`: file uploads.** Today it only parses urlencoded forms (`parse_qs`). The stdlib `cgi` module is gone as of Python 3.13. `email.parser.BytesParser(policy=email.policy.HTTP)` over the body, with the `Content-Type` header prepended, parses `multipart/form-data` in about 20 lines, with no new dependency.
- **Upload size.** Raise waitress's global `max_request_body_size` to about 5 MB, and keep the 1 MB check in the app for every other route. nginx `client_max_body_size` changes to match.
- **QR code.** Generate it from the website address with `segno`: pure Python, no dependencies of its own, writes SVG, and Typst renders SVG. The alternative is uploading a QR image made elsewhere, which asks more of a volunteer.
- **Deployment files.**
  - The `settings` volume in `docker-compose.yml`.
  - `mkdir` + `chown settings` in the `Dockerfile`.
  - `settings` in `.gitignore` and `.dockerignore`.
  - The backup and "bringing over" steps in `deploy/README.md`.
- **Docs.** In AGENTS.md:
  - add `parish.yaml` to the build contract;
  - add the settings routes to the Web UI section;
  - remove the "parish details need a code edit" quirk.

### Tests

- Settings round trip.
- A field missing from an old `settings/parish.yaml` gets its default.
- "Put back the original" and undo.
- Renders with:
  - three contacts;
  - one contact;
  - an empty website;
  - Typst-special characters (`# @ * $ < _ \`) in every text field.
- A too-long welcome text is reported as overflow.
- The Sunday service day moves the template's dates.
- Web:
  - settings need a login;
  - uploads: a valid image, a non-image, and one that's too big;
  - multipart parsing, including a filename with quotes and non-ASCII characters.

### Questions for the owner

1. **Layout numbers stay out of the UI.** Recommended, for the reason above. Say so if you do want the base font size or margins editable.
2. **A second password for Settings?** Recommended: no. Burying the page, the preview and undo cover mistakes, and a second secret is one more thing to lose in ten years.
3. **Past Sundays pick up new settings** when they're opened again: a re-print of an old bulletin shows the current priests. Recommended, because it's simple. The alternative is copying the settings into each Sunday's folder at download time, which means an already-prepared Sunday needs a "use the new settings" button.
4. **QR code**: generate it (`segno`, one small dependency) or upload an image? Generating is recommended.

## Part 2: other follow-ups

### First deployment checks (do these first)

Task 004's Docker setup was rehearsed, not built.
- [ ] **Build and run.** `docker compose up --build` works, and the `bulletin` user can write to the named volumes.
- [ ] **Time zone.** Check `docker compose exec app date` shows Arizona time. If the slim image has no time zone database, `TZ=America/Phoenix` silently falls back to UTC. Then after 5pm on a Saturday the home page's "next Sunday" is already the week after. Fix it by installing `tzdata` in the Dockerfile, or with `TZ=MST7`: Arizona has no daylight saving time, and a POSIX TZ string needs no database.
- [ ] **Downloads from the server.** Download one Sunday from the server itself. The live downloads so far ran from a home connection, and goarch.org's Cloudflare may challenge datacenter IPs. If it challenges every time, write down the outcome and pick a workaround: the readings editor, or downloading with `main.py` at home and `docker compose cp` of that build dir.
- [ ] **Bring over `build/`.** Five older build dirs don't render as they are:
  - `2026-01-25` and `2026-02-01` predate the sizing fields: run `uv run text_sizing.py <date>` on each first.
  - `2026-01-11` and `2026-01-18` have no `digital_chant_stand.yaml`, and `2026-04-19` has no readings. The owner decides whether to leave them (they show as missing) or leave them out of the copy.

### Backups a volunteer can see

- **A "Download a backup" button in Settings.** It gives a zip (stdlib `zipfile`) of every `manual.yaml` and the `settings/` folder: all that can't be regenerated. On an unwatched server, a cron job fails silently, but a volunteer who clicks it once a month has a real copy off the machine. The settings page can show when it was last used.
- **Also a host cron job**, for the whole `build` and `settings` volumes: a weekly `tar`, keeping 12 weeks, documented in `deploy/README.md`.

### A handover sheet and a maintenance runbook

Over ten years the likely failures aren't code:
- the domain lapses;
- the server bill goes unpaid;
- the certbot notice email goes to nobody;
- nobody knows the password.
- **A one-page handover for the church** (`deploy/HANDOVER.md`, plain words): where it runs, who pays for the server and the domain and when they renew, where the password is kept, how to make a backup, and what to tell a developer.
- **A developer runbook** (in `deploy/README.md`):
  - **Yearly:** `git pull && docker compose build --pull && docker compose up -d` for base image security fixes.
  - **What expires:**
    - Python 3.13 gets security fixes until about October 2029.
    - Debian 13's security support runs until about 2028, and its LTS until about 2030.
    - After those dates, bump the base image and `requires-python`, then `uv lock --upgrade` and `uv run pytest`.
  - **Upgrading Typst:** typst-py ≥ 0.16 means recalibrating per `tasks/done/001-text-sizing.md`.

### A text-size override

If the sizing model ever misjudges a Sunday, the volunteer's only choice is to print a third page. Add an optional text size (and break choice) to the readings editor. `text_sizing.run` would use it instead of solving, and write it into `feed.yaml` as an override so the model stays model-only (task 001). Done when a Sunday that overflows can be fixed from the web page.

### Keep the page that broke

When goarch.org changes and a scrape fails, nothing is archived (on purpose, so a bot-check page never becomes the cache). But a developer called in years later needs exactly that page.
- **Save failed downloads** to `archive/<date>/failed-<timestamp>/`. They're never read as cache and are reached through a new `SourceArchive.save_failed()`.
- **Say where it is.** "Technical details" gives the saved path.

### Render regression hashes

`test_render.py` only checks the page count. Rendering is deterministic, since only embedded fonts are used.
- **Store a hash** of each snapshot Sunday's preview PNGs in `tests/snapshots/<date>/`, regenerated with `UPDATE_SNAPSHOTS=1`.
- **On a mismatch**, write the new PNG to a temp path so it can be looked at.
- **What it catches:** unintended visual changes from template edits, and from a Typst upgrade.

### Small cleanups

- **AGENTS.md says "older DCS pages are gone"**, but on 2026-09-24 the DCS page for 2026-01-04 downloaded fine. Find out what's actually gone, with a request or two at most, not a bulk download, and correct the wording.
- **`assets/church.webp`** (164 KB) isn't used anywhere. Ask the owner before removing it.
- **Hymns of the Day from DCS** stay in task 002. Once that parsing is reliable, the hook is to pre-fill the hymn rows on the Sunday form.

## Suggested order

1. First deployment checks: they're short, and they test everything task 004 assumed.
2. Part 1, the settings.
3. The backup button and the host cron job.
4. The handover sheet and runbook.
5. The rest, in any order.
