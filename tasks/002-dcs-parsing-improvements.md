# Plan: better parsing of the Digital Chant Stand html

## Goal

See if we can improve the robustness of the DCS parsing to start actually using the parsed data in the document, to reduce the burden of the `manual.yaml`

## Known state (2026-09-24)

- The dismissal hymns scrape is incomplete. For 2026-09-27 it misses the Resurrectional Apolytikion, and the kontakion's mode ends up in its title ("Kontakion Mode 2", `mode: null`). See `tests/snapshots/2026-09-27/digital_chant_stand.yaml`.
  - (2026-11-10 audit) The missing Resurrectional Apolytikion is fixed: `group_by_sections` returns a list, so the title's second occurrence isn't hidden, and `test_dismissal_hymns_start_with_the_resurrectional_apolytikion` checks every archived Sunday. The kontakion's mode is still in its title on most Sundays; `commemorations.chant_stand_mode` reads it from there.
- `get_prokeimenon` no longer matches the live DCS markup (no rows start with "Prokeimenon"), so `get_scripture_reading_data` raises. `get_reading` and `get_alleluia_mode` still work.
- Parsing changes can be checked offline: `tests/test_scrapers.py` replays `archive/<date>/dcs.html` and compares against `tests/snapshots/` (see AGENTS.md, Tests).

