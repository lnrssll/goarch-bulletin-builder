# Plan: use the Digital Chant Stand to fill in the Hymns of the Day

- Status: planning (owner's answers in; for review before implementation)
- Branch: none open. This plan and the downloaded pages were merged into master on 2026-11-11, and the planning branch and its worktree closed; start a new branch to implement it.

## Goal

Originally:

> See if we can improve the robustness of the DCS parsing to start actually using the parsed data in the document, to reduce the burden of the `manual.yaml`

The owner, 2026-10-05:

> we don't really use the data we pull from the digital chant stand in our app to help the human user determine which hymns are of the day today. The crux of the issue is that the naming of the hymns is not consistent between the DCS and our church's hymn book, and the translations of the actual hymn are different too. so I think we need to record the full text of the hymn so we can keep track of matches/labels for the actual hymn book we use. we also should have a way of showing the user in the web ui what the results of the dcs scrape were, so they can inform on what hymns we might be writing in.

So every week, the Sunday page should show which hymns the Digital Chant Stand (DCS) lists after the Entrance. It should start the "Hymns of the Day" table from them:
- **Filled in** when the parish's name and page are known for sure.
- **Hinted** when they're only guessed: the day's saint from the GOARCH feed, the last name used, or DCS's own words.

When the volunteer names a hymn, the app learns that name for the next time it comes around.

## Decisions (owner, 2026-10-05)

1. **Fetch the rest of 2026's DCS pages**, spaced out so it doesn't look like bot traffic. **Done:** one page at a time, 45-120 s apart, dcs.goarch.org only, into `archive/<date>/dcs.html`.
   - Every Sunday from 2026-01-04 to 10-04 is archived (36 Sundays, 3.2 MB), except the four pre-Lent Sundays (02-01, 02-08, 02-15, 02-22).
   - Those four come back from DCS as empty pages (200, 5-7 KB, the page frame with no hymns), although the scraper got their hymns in February. A known-good page fetched in between came back complete, so this isn't blocking. For those four Sundays, only the old scrapes in `state/` remain (texts, no IDs).
   - Committed on 2026-11-11. Those folders have only `dcs.html`, so the snapshot tests skip them; `test_scrapers.py` checks each page's Alleluia and Resurrectional Apolytikion.
2. **A name that's only a guess is a hint, not filled in.**

   > maybe we could print the generic name as a hint that is acceptable but not autofilled, since it will usually be wrong i think. it helps though, like if it's "for the fathers" on the sunday of the fathers of the 7th council, then I can guess pretty easily which hymn that is in our book.

3. **Delete the unused DCS readings code.**
4. **No feast-day extras.** Only the hymns after the Entrance: no Hypakoe, megalynarion or special Communion hymn.
5. **Keep matching by text** as a fallback (as a hint, see Part 2).
6. **The mission has no parish apolytikion.** DCS's "The Apolytikion of the parish church is sung." rubric is ignored.
7. **Explore the saint/feast XML for exact matches.** Done for the three archived Sundays, and it works (see "The saint and feast XML" below). It becomes Part 3.

## What the data shows (2026-10-05)

### The DCS list is the parish's list

In all three archived Sundays, the hymns DCS lists after the Entrance line up one-to-one, and in order, with the rows the parish printed. Only the names differ:

| Sunday | DCS (title, mode) | Printed (title, mode, page) |
|---|---|---|
| 09-13 | Resurrectional Apolytikion, pl. 2 | Resurrectional Apolytikion, 6, p. 119 |
| | For the Forefeast, 2 | Apoytikion for the Forefeast, 2, Choir |
| | For the Consecration, 4 | *(not printed)* |
| | Kontakion, 4 | Kontakion for the Consecration, 4, Choir |
| 09-20 | Resurrectional Apolytikion, grave | Resurrectional Apolytikion, 7, p. 123 |
| | Apolytikion. For the Cross, 1 | Apolytikion For the Cross, 1, p. 181 |
| | For the Saints, 4 | Apolytikion For the Saints, 4, Choir |
| | Kontakion, 4 | Kontakion For the Cross, 4, p. 233 |
| 09-27 | Resurrectional Apolytikion, pl. 4 | Resurrectional Apolytikion, 8, p. 127 |
| | For the Martyrs, 4 | Apol. of Martyr Callistratus & Companions, 4, choir |
| | Kontakion, 2 | Ordinary Kontakion, 2, p. 225 |

(09-13 left one apolytikion out. The parish doesn't always sing everything listed, so the volunteer has the last word.)

### Every DCS hymn has a stable ID

The DCS page marks every hymn's text with a `data-key` from the liturgical text database it's generated from:

```html
<p class="hymn"><span class="kvp" data-key="ho.ho07_en_US_dedes|hoTY.Key0408.text">O Protection of Christians that never falls, …</span> …
```

- **It names the hymn, not the wording.** The part before `_en_US_…` is the book and day:
  - `oc.m8.d1`: Octoechos, mode 8, day 1
  - `me.m09.d14`: Menaion, September 14
  - `ho.ho07`: Horologion
  - `he.ga`: the common hymns of the General Menaion
  - `he.a.m4`: the model melodies of mode 4

  The part after `|` is the hymn. The `_en_US_dedes` / `_goa` / `_goadedes` part is the translation, and it varies. With the translation removed (`ho.ho07|hoTY.Key0408.text`), the ID is the same hymn every year.
- **The mode has an ID too**: `misc.Mode8` for "Mode pl. 4.", `misc.Mode7` for "Grave Mode.". That's the parish's 1-8 numbering, with no text parsing.
- **One hymn can have several IDs.** The mode 6 Resurrectional Apolytikion is `he.a.m6|heAU.AngelikaiDynameis.text`, while modes 7 and 8 are `oc.m7.d1|ocVE.Apolytikion.text` and `oc.m8.d1|…`.
- **Generic hymns.** `he.ga|heGA.OiMartyresSouKyrie.text` ("Your Martyrs, O Lord…") was "For the Saints" on 09-20 and "For the Martyrs" on 09-27. The parish named it after the day's saint, so last time's name is only a hint.

### The saint and feast XML names the hymn

The GOARCH feed links each day's commemorations (`saints/<id>.xml`). These are already downloaded every week, to find the icon, and archived. Many of them carry the saint's or feast's apolytikion and kontakion: type, tone, a `shorttitle`, and the text in another translation (mostly Holy Transfiguration Monastery):

> **XML** (Callistratus, Fourth Tone): *Thy Martyrs, O Lord, in their courageous contest for Thee received as the prize the crowns of incorruption…*
> **DCS** (For the Martyrs, Mode 4): *Your Martyrs, O Lord, were worthily awarded by You the crowns of incorruption…*

The parish's 09-27 title, "Apol. of Martyr Callistratus & Companions", is that XML's `shorttitle` ("Apolytikion of Martyr Callistratus & his Companions"), shortened by hand.

A prototype matched each DCS hymn to the day's XML hymns. A candidate has to be the same kind (apolytikion or kontakion) and the same mode. The score is the word overlap of the two texts: `thy` counts as `your` and `thou` as `you`, words are cut to a 6-letter stem, and common words are ignored. The results:

| Sunday | DCS hymn | Best XML match (score) | Best wrong candidate of the same kind and mode |
|---|---|---|---|
| 09-13 | For the Forefeast, 2 | Apol. of Forefeast of the Exaltation (0.39) | none |
| | For the Consecration, 4 | Apol. of Temple of the Resurrection (0.43) | none |
| | Kontakion, 4 | Kont. of Temple of the Resurrection (0.26) | Kont. of Hieromartyr Cornelius (0.06) |
| 09-20 | Apolytikion. For the Cross, 1 | Apol. of Afterfeast of the Holy Cross (0.62) | none |
| | For the Saints, 4 | Apol. of Martyr Eustathius and His Companions (0.33) | none |
| | Kontakion, 4 | Kont. of Sun. after Holy Cross (0.29) | none |
| 09-27 | For the Martyrs, 4 | Apol. of Martyr Callistratus & his Companions (0.33) | none |
| | Kontakion, 2 (Mother of God) | *(none, correctly: not a saint's hymn)* | Kont. of Callistratus (0.04) |
| all | Resurrectional Apolytikion | *(none, correctly)* | different mode |

All 11 are right. True matches score 0.26 to 0.62, and wrong ones score 0.06 at most. That's three Sundays, so check it across the year before trusting a threshold (Question A).

The XML names are more specific than what the parish printed (09-20 says "Martyr Eustathius and His Companions" where the parish printed "For the Saints"). That's why they're hints, not filled in.

### Why today's scrape misses hymns

- **Sections are keyed by title** (`group_by_sections` returns a dict). "Resurrectional Apolytikion." is also sung after the Third Antiphon, so the second one is appended to the first section's key, before "Hymns after the Entrance.", and skipped. Every Sunday is missing it.
- **The kontakion's mode is inside its title** (`<span class="mode">` in the `designation`), so the scrape gives "Kontakion Mode 2" with no mode.
- **The list ends at "Trisagios Hymn"**, which Pascha, Pentecost and the other baptismal feasts replace. The old scrapes in `state/` have 12 "hymns" for 2026-04-12 (Pascha) and 11 for 2026-05-31 (Pentecost).
- **The mode is a string** ("Plagal 4") while `manual.yaml` uses 1-8.
- **Unused readings code:** `get_prokeimenon` no longer matches the markup, so `get_scripture_reading_data` raises. Only the Alleluia verses are used from DCS.

### What history there is

- `state/sundays/` (the owner's real data) has 37 Sundays of printed hymns, 2026-01-11 to 09-27. 34 of them have an old `digital_chant_stand.yaml`, with the bugs above and no IDs.
- `archive/` had DCS pages and saint XML for only three Sundays. The rest of 2026's DCS pages are being fetched (decision 1). The saint XML for those Sundays isn't archived (Question A).

## Part 1: parse the DCS hymns properly (`digital_chant_stand.py`)

- **Sections as a list, not a dict.** `group_by_sections` returns `list[Section(title, rows)]` in page order, so a repeated title is its own section. `get_scripture_reading_sections` and `dismissal_hymn_sections` walk the list. The Alleluia keeps working.
- **Where the list ends.** It starts after "Hymns after the Entrance." and ends at "Trisagios Hymn", or "Instead of Holy God" on Pascha and Pentecost (checked on the 2026 pages). Better still, match the Trisagion's IDs (`hoLI.TrisagiosHymn`, `psLI.trisagionbaptized`). "The first section without a hymn" won't do, since the Trisagion section has one.
- **Cases from the 2026 pages:**
  - On Pascha the first hymn ("Christ is risen", `pe.d071|peMA.Troparion.text`) sits directly under "Hymns after the Entrance." with no title of its own.
  - Pascha's list includes the Hypakoe. The parish printed it (2026-04-12, "Hypakoe, 4, handout"), and it's inside this list, so decision 4 doesn't exclude it.
  - The Sunday of Orthodoxy (03-01) has "Kontakion." with no text or ID. The entry is kept, with only its title and mode, and gets only DCS-word hints.
  - Palm Sunday has "Apolytikion." then "Another.". "Another" takes the kind of the hymn before it.
- **Each hymn** becomes a `DismissalHymnData` (in `classes.py`, part of the YAML contract):

  ```yaml
  - key: oc.m8.d1|ocVE.Apolytikion.text   # data-key without the translation
    kind: apolytikion                      # or kontakion
    title: Resurrectional Apolytikion      # DCS's designation, trailing period removed
    mode: 8                                # from misc.ModeN; int 1-8, like manual.yaml
    melody: null                           # "Come quickly." when it has one
    source: Octoechos                      # from the "From … - - -" row, when there is one
    text: You descended from on high, …    # full English text
  ```

  - `kind` is `kontakion` for the hymn whose designation starts "Kontakion", and `apolytikion` for those before it. It's needed for matching against the XML (Part 3).
  - `mode` changes from a string to an int. The old "pl. N" / "Grave" mapping is the fallback when there's no `misc.ModeN` ID.
- **Rubrics are skipped** (decision 6).
- **Remove the unused readings code** (decision 3):
  - remove `get_scripture_reading_data`, `get_prokeimenon`, `get_reading` and the `ScriptureReading*` dataclasses;
  - fold `get_alleluia_mode` into the mode parser.
- **A failure stays a warning.** If the hymns don't parse, the Alleluia is still written and the hymns are `null`.

## Part 2: from a DCS hymn to a row

### Where the matches live

There are two places, the same pattern as the parish settings: committed defaults plus what the church has done.

1. **The catalog (`data/hymns.yaml`, committed).** A catalog hymn gets a `dcs` list of the IDs that are that hymn:

   ```yaml
   - title: Kontakion for the Mother of God
     also: [Ordinary Kontakion]
     mode: 2
     page: 225
     dcs: [ho.ho07|hoTY.Key0408.text]
   - title: Resurrectional Apolytikion
     pages_by_mode: {1: 99, …, 8: 127}
     dcs: [he.a.m6|heAU.AngelikaiDynameis.text, oc.m7.d1|ocVE.Apolytikion.text, oc.m8.d1|ocVE.Apolytikion.text]
   ```

   A test checks that no ID is in two entries. It's seeded from 2026 (Part 6).
2. **The history (`state/sundays/*/manual.yaml`).** A hymn row gets an optional `dcs_key` (`ManualHymnData.dcs_key: str = ""`).
   - Rows started from DCS carry it, and it survives the volunteer typing a title, so the saved row is the label: this DCS hymn is "Apol. of Martyr Callistratus & Companions", Choir.
   - Typst ignores the field.
   - There's nothing new to back up, and it works on the deployed server, where nothing is committed.

### Filled in, or only hinted (`manual.match`)

**Filled in** (title, mode and page in the row), only when it's certain:
1. **The catalog, by ID.** Title from the catalog, mode from DCS, page from `page` or `pages_by_mode[mode]`.
2. **The history, by ID, for a hymn tied to one day**: the most recent saved row with that `dcs_key`, from all of `state/sundays/`, since feasts come once a year. This excludes **generic hymns** (IDs under `he.ga|`), whose last name belonged to another saint.

**Hinted**, when nothing above applies. The row gets DCS's mode, an empty title and an empty page. The hints, best first:
1. **The saint/feast XML match** (Part 3): "Apolytikion of Martyr Callistratus & his Companions".
2. **The last name used for this ID** (generic hymns): "last time: Apolytikion For the Saints".
3. **The last name used for the same text** (decision 5): the same normalized DCS text in an older Sunday's `digital_chant_stand.yaml`, and the row that Sunday printed in the same position. This covers Sundays saved before IDs, and DCS renumbering its IDs.
4. **DCS's own words**, made into a title: "For the Fathers" before the kontakion becomes "Apolytikion for the Fathers", and "Apolytikion. For the Cross" becomes "Apolytikion for the Cross".

A hint that's a catalog title or alias brings its page and mode along when picked.

### How the hints show

- **In the empty title box**, the best hint is the grey placeholder text. Without JS, that's all there is, and the volunteer types the name.
- **In the suggestion box** (`app.js`): focusing an empty title lists that row's hints first, then the catalog. So Tab or Down then Enter takes a hint in one keystroke, but nothing is filled in unasked. The hints go on the row as `data-hints` (JSON). The CSP allows data attributes.
- **In the DCS list** above the table (Part 4).

### Saving, and rows the volunteer leaves alone

- **A row with no title is dropped on save**, as today. For a DCS row, that means "we don't sing this one" (09-13 left one out). The DCS list then shows it as "not in the bulletin".
- **The template's unnamed rows** (before the first save) are `manual.unfinished`: "Hymn 2 has no title yet (the Chant Stand calls it “For the Martyrs”)."
- **An empty page** on a titled row is `unfinished`: "Hymn “…” has no page. Write the page number, or Choir or Handout."
- **The template's "Fr. X"** is still there, so step 2 gets opened every week anyway.

## Part 3: the saint and feast hymns (`goarch_xml_feed.py`)

Most of task 006's "start using saints and feast xml parsing", for the part that names hymns.

- **Write `saints.yaml`** to the Sunday's folder: each commemoration in the feed's order, with its hymns. `process_saint_feast_page` already parses them. It's wired into `scrape` and adds no requests, since `identify_icon` already fetches every XML. It has to be written to the Sunday's folder, because a Railway deployment doesn't keep `archive/`.

  ```yaml
  - title: Kallistratos the Martyr & his 49 Companions
    hymns:
    - kind: apolytikion
      title: Apolytikion of Martyr Callistratus & his Companions   # the shorttitle
      mode: 4                                                      # "Fourth Tone"
      text: Thy Martyrs, O Lord, in their courageous contest …
  ```

  - Tones are converted to the parish's 1-8 numbering. Check the full set of tone names against the year's XML ("Plagal of the First Tone"? "Grave Tone"?).
  - `SaintFeastHymnData` gets `mode`, and `kind` instead of `type`.
- **Matching** (`hymn_match.py`, no network imports, so `manual` and `web` can use it):
  - A DCS hymn's candidates are the day's XML hymns of the same `kind` and `mode`.
  - The score is the word overlap from the prototype: archaic forms mapped (`thy` → `your`, `thou` → `you`, `hath` → `has`, `-est`/`-eth` endings), 6-letter stems, stop-words ignored.
  - The best candidate above a threshold is the hint. Start at 0.15 and set it from the year's data (Question A).
  - Each XML hymn is used at most once per Sunday.
- **The feed is the other source.** If the feed failed and DCS didn't, there's no XML hint, and the other hints still work. If DCS failed, there are no DCS rows: the page shows the day's commemorations and their hymn names as plain suggestions, so the volunteer can still type them.

## Part 4: start the hymns from DCS

- **The template.** `manual.template` gets the DCS hymns and `saints.yaml`; `fetch_readings` writes both before the template. It writes one row per DCS hymn, filled in or hinted as in Part 2, each with its `dcs_key`. The "Example" row is used only when DCS failed or listed nothing. Over the history, that would have filled in the whole Resurrectional Apolytikion row every ordinary Sunday, and the Kontakion for the Mother of God most of the summer.
- **Never overwrite `manual.yaml`.** It's still written only when missing.
- **When DCS arrives later.** If the first download failed for DCS, the template already has "Example". While the hymn list is still exactly that placeholder, the Sunday page offers the DCS rows in the form (not the file), and saving writes them. A list the volunteer has touched is never replaced.
- **The form** keeps each row's `dcs_key` in a hidden input. A row added by hand has none.
- **The CLI** gets the same template.

## Part 5: show the DCS list on the Sunday page

In step 2, above the "Hymns of the Day" table: **"The Chant Stand lists these hymns after the Entrance"**:

```
1. Resurrectional Apolytikion · Mode pl. 4 (8) · Octoechos      → Resurrectional Apolytikion, p. 127
2. For the Martyrs · Mode 4, “Come quickly” · common hymn        → not named yet
   Today's saint: Apolytikion of Martyr Callistratus & his Companions
   ▸ Read the hymn
3. Kontakion · Mode 2                                           → Kontakion for the Mother of God, p. 225
   ▸ Read the hymn
```

- DCS's words, the mode both ways (the volunteer may know "pl. 4" from the book), and where it's from.
- What the row is now ("→ … p. 127"), or "not named yet" with the hints, or "not in the bulletin".
- The full text in a collapsed `<details>`, which is what identifies a generic or unfamiliar hymn. When there's an XML match, its text goes beside DCS's, since it may be closer to the hymnal's translation.
- A link: "Open this Sunday on the Chant Stand" (the DCS URL).
- If DCS failed or listed nothing: one line saying so, plus the day's commemorations (Part 3), and the form works as today.
- Plain words, no IDs or scores; those go in "Technical details". Server-rendered, no JS needed. It wraps to one hymn per block on a phone.

## Part 6: seed and check against 2026 (developer, one-off)

- **A script, run once** (a throwaway in the scratchpad; it doesn't need to live in the repo). For every 2026 Sunday with a DCS page and a printed `manual.yaml`, it pairs the DCS hymns with the printed rows (in order, same mode). It reports:
  - for each catalog hymn, the DCS IDs it was printed for: these become the `dcs:` lists, after the owner reviews them;
  - for each XML hint (if the XML is fetched, Question A), whether it matched what was printed, and the scores, to set the threshold;
  - anything ambiguous, for a person to decide.
- **Regression cases.** Add snapshots (AGENTS.md, Tests) for Pascha (04-12), Pentecost (05-31), Palm Sunday (04-05), the Sunday of Orthodoxy (03-01, no kontakion text) and a Sunday of the Fathers. They need the feed too (`test_scrapers.py` replays both sources), so only Sundays whose Online Chapel files are archived can be snapshot cases (Question A).
- **Commit all the year's DCS pages anyway** (3.2 MB). They can't be fetched again after 2026-12-31, and Part 6 and future parser changes need them.

## Storage: files, not SQLite (yet)

The owner asked whether it's time for SQLite, for the data people won't touch, like this matching. Not yet:
- **The matches aren't stored data, they're computed.** The inputs are the catalog (committed, reviewed in git), the saved rows (the church's), and the scraped files. A database would hold a copy that goes stale on a hand edit, a restore from the backup zip, or a settings undo. With the files as the only truth, there's nothing to keep in sync.
- **It's small.** About 52 Sundays a year of a few small YAML files: ten years is ~2,000 files, a scan of well under a second. It can be cached in memory against file times if that ever matters, as the render cache does.
- **Typst reads YAML**, not SQLite, so moving "all of it" would mean writing YAML for Typst anyway.
- **Plain files are part of the ten-year goal**: a successor opens them in any editor, and a catalog change is a readable git diff.
- **`sqlite3` is in the standard library**, so the cost isn't a dependency. It's a second source of truth, a schema to migrate, and live-database backups.
- **When to revisit:** data that isn't per-Sunday and is written often (say, a log of every match decision), several people editing at once, or a scan that's measurably slow. Even then, a disposable cache under `state/` that rebuilds itself when deleted, never the source of truth.

## Tests

- **`test_scrapers.py` snapshots** change for every archived Sunday: the Resurrectional Apolytikion appears, the kontakion has mode 2, modes are ints, `key`/`kind`/`melody` are added, and `saints.yaml` is new. Regenerate them after checking the diff (`UPDATE_SNAPSHOTS=1`).
- **DCS parsing:**
  - 2026-09-27 gives three hymns: Resurrectional 8, For the Martyrs 4 (melody "Come quickly."), Kontakion 2, with IDs and kinds;
  - a repeated section title is its own section;
  - the list ends at the Trisagion and at its replacement (Pascha, Pentecost);
  - an ID loses its translation part.
- **`hymn_match`:** each of the 11 cases in the table above. Also: kind or mode disagreeing means no match, an XML hymn is used once, and the word normalization (`Thy Martyrs` ~ `Your Martyrs`).
- **`test_manual.py`:**
  - filled in only from the catalog or a non-generic history ID;
  - otherwise an empty title with hints, in order;
  - `pages_by_mode` with DCS's mode;
  - the template writes DCS rows with `dcs_key`, and "Example" only without DCS;
  - unnamed and page-less rows are `unfinished`;
  - no ID is in two catalog entries;
  - `dcs_key` survives `read`/`write`, and older files without it still read.
- **`test_web.py`:**
  - the DCS list with matches, hints and texts;
  - `data-hints` on the rows;
  - saving keeps `dcs_key` and drops an untitled row;
  - a placeholder-only list is offered the DCS rows, and a touched list isn't;
  - the page works without a DCS file and without `saints.yaml`.
- **`test_render.py`:** previews unchanged (nothing new is printed).
- **By hand in the browser:** an empty title shows the hint, and Tab takes it. A hint that's a catalog hymn brings its page.

## Questions for the owner

A. **Fetch the Online Chapel feed and saint XML for 2026's past Sundays too?** That's needed to check the XML matching across the year (Pascha, Theophany, the Sundays of the Fathers) and to set its threshold. It's the Cloudflare-protected site, ~34 index pages plus ~5 saints each, about 200 requests. Spaced like the DCS run (45-120 s, stopping at the first bot-check page), that's about 4-5 hours, in the background. The feed seems to keep past dates, so this isn't urgent like the DCS pages. **Recommended: yes, after the DCS run, at the same spacing.** If it gets a bot check, stop, and set the threshold from what's there.

B. **Task 006**: this plan does its hymn-naming part (Part 3). Close 006 as merged into 002, or keep it for anything else about the saints (showing the commemorations, a printed "Saints of the Day")?

## Out of scope

- Printing anything new in the bulletin.
- Transcribing the hymnal's own texts. Matching is by DCS ID, or by DCS ↔ XML text, to the parish's title and page.
- Feast-day extras (decision 4).

## Done when

- The 2026-09-27 scrape gives the three hymns with IDs, kinds and modes 8, 4, 2, and Pascha's list stops before the Trisagion's replacement.
- A new Sunday's hymn table starts from DCS:
  - the Resurrectional Apolytikion and other catalog hymns filled in with their pages;
  - everything else with its mode, an empty title and a hint (the day's saint first).
- The Sunday page shows the DCS list, what each became or its hints, and each hymn's text.
- A name typed for a DCS hymn is filled in the next time that hymn comes around (unless it's generic, when it's the hint).
- All of 2026's DCS pages are in `archive/`, and the catalog has its `dcs:` IDs.
- `uv run pytest` passes, with snapshots checked by eye.
