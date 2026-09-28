# Plan: hymn and priest suggestions that fill in the rest of the row

## Goal

> building out a local database of hymns (title and may or may not include page number/"choir" and mode), so that when i start typing them, I can get suggestions? for example, we have a "Resurrectional Apolytikion" in one of the 8 modes every week. It would be cool if I went "Res" and it showed "Resurrectional Apolytikion" with tab complete and then when I chose a mode it filled in the page number (this one is actual in the data/table-of-contents.txt file, for example). Similarly, for ones where there is only one name (e.g. "Ordinary Kontakion"), I'd love for _both_ the mode and page number to autofill. Last, I'd like to do the same thing for Priests, where we keep a list of previous values so that we can just click a dropdown or start typing. There are only four or five options.

The owner's follow-up:

> The p. 225 hymn should be "Kontakion for the Mother of God" […] for pages in the service book, they are always on odd pages because the even pages are greek. […] build a custom suggestion box, hymn list does not need to be editable. Last, all the priests will be called "Fr. ..." so we really should be able to skip that part and have "Fr." in front of the input box (and prefix removed as a precaution) to simplify things. For the hymns, they sometimes are too long, and I abbreviate "Apolytikion" as "Apol." or "Kontakion" as "Kont.". It would be nice if we checked the max length of the text box and automatically made those substitutions when the hymn name is too long. That would probably mean storing both a real name and a shortened name for each hymn.

> lets do the same thing for "p. " as with "Fr. " with exceptions for choir etc.

Filling in the hymns should take a few keystrokes per row. The page number should come from the hymnal index, not from memory. Titles are typed out in full, and the bulletin shortens one only when it doesn't fit.

## What exists today

- **Title suggestions.** `manual.suggestions` scans the last 52 Sundays in `build/`, and `templates/sunday.html` offers their titles through `<datalist id="hymn-titles">`. The option label shows the mode and page last used, but picking a title fills in only the title.
- **Priest suggestions.** The same scan fills `<datalist id="priests">`, most recently used first.
- **The hymnal index.** `data/table-of-contents.txt` is shown under "Page numbers in the hymnal" for reading. Nothing looks up a page in it.
- **The printed hymns.** `bulletin.typ` prints the Hymns of the Day as a 3-column table (title, mode, page) at 8pt, and a title that's too long wraps.
- **Browser suggestion lists.** Browsers differ in how they match datalist options, and none of them complete on Tab. On a field that already has a value, a datalist shows only the options matching that value, so clicking the Priest box doesn't list all the priests.

The history in `build/` (2026-01-11 to 2026-09-27, 37 Sundays) shows why a curated list is worth having:
- **Page mistakes.** 2026-01-11 has the Resurrectional Apolytikion in mode 7 at "p.119", which is mode 6's page. Mode 7 is p. 123.
- **Different spellings.** "Resurrectional Apolytikion" also appears as "Resurrectional Apolitikion" and "Ressurectional Apolytikion". "Pascha Kontakion" and "Paschal Kontakion" are both used.
- **Two names for one hymn.** The p. 225 hymn (mode 2) is written as "Kontakion for the Mother of God" 7 times and as "Ordinary Kontakion" twice. Its name is **Kontakion for the Mother of God**.
- **Shortened by hand.** For example "Kont. of Forefeast of the Meeting of the Lord", "Sun. of the Myrrh-bearing Women Another Apol." and "Kontakion of Forgiveness (Cheesefare) Sun.".
- **Different page formats.** "p.119" and "p. 119" are both used, and so are "handout", "Handout" and "choir".
- **An even page in the index.** The English hymns are always on odd pages, because the even pages are Greek. `data/table-of-contents.txt:37` has Theophany (Apolytikia from the Menaion) on p. 210. It's p. 209, as on 2026-01-11. It's the only even page in the index.
- **Priests.** Fr. Joshua 18, Fr. Jacob 13, Reader Service 12, Fr. Andrew 11, Fr. Timothy 10, Fr. George 3, Fr. Paul Jannakos 2. "TBD" appears 3 times.

## Decisions

- **A custom suggestion box** in `app.js` (Part 2), not the browser's datalist dropdown.
- **The hymn list is not editable in the web UI.** New hymns come up from the history anyway, and a fix to the list is one edit in `data/hymns.yaml`.
- **The p. 225 hymn is "Kontakion for the Mother of God"**, with "Ordinary Kontakion" as another name that finds it.
- **Hymn titles are stored in full.** A shortened form is printed only when the full one doesn't fit on one line (Part 5).
- **Priests get a fixed "Fr." in front of the box** (Part 3), **and pages a fixed "p."** (Part 4), with exceptions for "Reader Service", "Choir", "Handout" and the like.

## Part 1: the hymn catalog

### `data/hymns.yaml`, committed

This is a curated list of the hymns the parish uses, keyed by the full title:

```yaml
- title: Resurrectional Apolytikion
  also: [Resurrectional Apolitikion, Ressurectional Apolytikion]
  pages_by_mode: {1: 99, 2: 103, 3: 107, 4: 111, 5: 115, 6: 119, 7: 123, 8: 127}
- title: Kontakion for the Mother of God
  also: [Ordinary Kontakion]
  mode: 2
  page: 225
- title: Pascha Kontakion
  also: [Paschal Kontakion]
  mode: 8
  page: 275
- title: Apolytikion of the Sunday of the Myrrh-bearing Women
  short: Myrrh-bearers Apol.
  mode: 2
  page: 159
```

- **Fields.**
  - `title` is the full name. It's printed whenever it fits.
  - `short` is optional. It's printed instead when the full title doesn't fit. Leave it out, and the standard abbreviations are used (Part 5). Set it only where those don't make the title short enough.
  - `also` lists other spellings and names. They're used for matching what's typed, and for merging old entries from the history.
  - `mode` is set when the hymn is always in one mode. Leave it out when the mode varies.
  - `page` is used when there's one page. `pages_by_mode` is used when the page depends on the mode. An entry has one or the other, or neither.
  - A hymnal page is a bare number (`225`), always odd. Anything else is a word from `NOT_A_PAGE` ("Choir", "Handout"; see Part 4).
- **Seeding the catalog.**
  - Add one entry for every line of `data/table-of-contents.txt` that's a hymn the parish sings. The eight "Tone N" lines become the one Resurrectional Apolytikion entry above.
  - Titles are full names in the bulletin's style ("Theophany Kontakion", "Apolytikion of the Sunday of Orthodoxy"), not the index's ("Kontakia: January 6 — Theophany"), and not abbreviated.
  - Take the modes from the history where the history is consistent. For example, Presentation of the Lord Kontakion is mode 1, p. 251, and Theophany Kontakion is mode 4, p. 249.
  - Where the history has nothing, take the mode from the archived DCS page for that feast (`archive/<date>/dcs.html`) or ask the owner. Don't guess.
  - Spell "Apolytikion" the way the bulletin already does, not "Apolitikion" as in the index.
- **Fix the index.** Change `data/table-of-contents.txt:37` to p. 209.
- **Why a separate file from the index.** `table-of-contents.txt` is a transcription of the book, arranged the way the book is. The catalog is what gets printed. A test keeps them consistent (see Tests).
- **Why not a database.** Per AGENTS.md, the state lives in files. This is about 60 short entries that the owner may want to read or edit by hand, so a YAML file is enough.

### Merging in the history

`manual.suggestions` returns the catalog first, then titles from the last 52 Sundays that aren't in the catalog. Those are usually one saint's or one feast's apolytikion, printed from a handout.
- **Same hymn.** A history title counts as a catalog hymn when it matches that hymn's `title` or an `also` entry.
  - The comparison ignores case, spaces and punctuation.
  - It expands the standard abbreviations first, so "Apol. of Sun. of Orthodoxy" matches "Apolytikion of Sunday of Orthodoxy".
  - This hides the misspellings and the hand-shortened titles above.
- **Mode and page from the history.** A history-only title gets a mode or page to fill in only if that value was the same every time the title was used. "Apolytikion of the Feast" changes mode, so it fills in nothing and only completes the title.
- **Order.**
  - Catalog hymns used in the last 52 Sundays come first, most used first, so "Res" puts the Resurrectional Apolytikion first.
  - The rest of the catalog comes next, in file order.
  - History-only titles come last, most recent first. They're shown with the abbreviations expanded.
- **Placeholders.** The "Example" placeholder hymn and anything with mode 9 are still skipped.

### The code

- **`manual.py`.**
  - Add `HYMN_CATALOG_PATH = Path("data/hymns.yaml")` and a `hymn_catalog()` reader, tolerant of hand edits in the same way `manual.read` is.
  - `Suggestions.hymns` becomes a list of `HymnSuggestion(title, short, also, mode, page, pages_by_mode)`. The dataclass stays in `manual.py`, because it isn't part of the build contract.
- **Even pages.** `manual.unfinished` adds a note for an even hymnal page: "Hymn “…” is on p. 210, an even page. The English is on the odd pages."
- **`templates/sunday.html`.**
  - The data the JS needs goes on the `<option>`s as `data-mode`, `data-page`, `data-pages` (JSON, e.g. `{"1": "99", …}`) and `data-also`. The CSP forbids inline scripts, but data attributes are fine.
  - A page there is what goes in the Page box: a bare number, or a word like "Handout" (Part 4).
  - The datalists stay, so the form still works without JS.

## Part 2: filling in the row (`static/app.js`)

### The suggestion box

A small suggestion box in `app.js` is used for both hymn titles and priests (~120 lines of JS plus some CSS).
- **Setup.** It turns an `<input list="…">` into the ARIA combobox pattern. It reads the options from the datalist, then removes the `list` attribute so the browser's own dropdown doesn't show as well.
- **Typing** shows matches. Prefix matches come first ("Res"), then word-prefix matches ("Kont" matches "Kontakion for the Mother of God"). Names under `also` match too, but the `title` is what gets filled in ("Ordinary" gives "Kontakion for the Mother of God").
- **Each suggestion shows its mode and page**, in the smaller grey text used by the hints: "Resurrectional Apolytikion: page depends on mode", "Kontakion for the Mother of God: Mode 2, p. 225".
- **Keys.**
  - **Tab** accepts the top match, then moves on to the Mode box as usual.
  - **Enter** accepts the highlighted match without sending the form.
  - **Arrow keys** move the highlight, and **Escape** closes the list.
  - Clicking or tapping a match picks it.
- **Clicking, tapping or pressing Down arrow** on the field lists every option, even when the field already has a value. That's the dropdown the priests need.
- **If nothing matches**, the list is hidden and the typed text is kept. New names are always allowed.
- **Phones** show the list under the field with full-width rows that are easy to tap.

### Autofill rules

- **Picking a title** fills in its fixed mode and its page. For the Resurrectional Apolytikion it fills in only the page for the mode already chosen, if there is one.
- **Changing the mode** fills in the page when the row's title has `pages_by_mode`. So picking the title and then the mode gives the whole row.
- **A value the volunteer typed or picked is never replaced.** Only an empty field, or a value that was itself filled in automatically, gets filled or refilled.
  - Track this with a `data-autofilled` attribute on the field, cleared when the volunteer edits it.
  - Changing the title from "Pascha Kontakion" to "Kontakion for the Mother of God" updates the mode and page it filled in.
  - A hand-typed "Handout" stays.
- **Unsaved changes.** Autofill counts as a change for the unsaved-changes warning, the same as typing.
- **Priests** have no autofill, only the suggestion box.

## Part 3: priests

### "Fr." in front of the box

- **The form.** The Priest cell shows a fixed "Fr." label, styled as part of the field, then the input. The input holds only the name ("Joshua", "Paul Jannakos").
- **What's stored doesn't change.** `manual.yaml` still says `priest: Fr. Joshua`, so `bulletin_back.typ` and existing files are untouched.
- **Loading the form.** `manual.priest_name(stored)` removes the prefix for the input.
- **Saving the form.** `manual.priest_label(typed)`:
  - removes any prefix the volunteer typed anyway: "Fr.", "Fr", "fr." or "Father", any case, followed by a period or a space;
  - leaves a name like "Francis" or "Frederick" whole;
  - then writes `Fr. <name>`.
- **Services with no priest.** "Reader Service" (12 of the past Sundays) and "TBD" are saved without the prefix. Keep them in a list in `manual.py` (`NO_PRIEST`), matched ignoring case.
  - The suggestion box offers "Reader Service" after the priests.
  - When the box holds a value from that list, JS hides the "Fr." label.
  - Without JS the label stays, but the saved text is still right.
- **The template placeholder** stays "Fr. X" in `manual.yaml`. The form shows "X", and `manual.unfinished` still flags it.
- **An empty name** with a date is saved as an empty priest, as today, not as "Fr.".

### The list

- **The list stays the history in `build/`**, names without the prefix. It's ordered by how often each name was used in the last 52 Sundays, most first. Across all of `build/` that's Joshua, Jacob, Andrew, Timothy, George, Paul Jannakos, then Reader Service.
- **Placeholders are left out:** "X" (from "Fr. X") and "TBD".
- **No `data/priests.yaml`.** The names are specific to the parish and change over time. Task 005 moves the priests' contact details into parish settings, and its "Tie-in" puts those contact names first in this list. That's where a curated list of priests belongs.
- **A priest who stops coming** drops off after 52 Sundays. With five or six names, that's fine.

## Part 4: "p." in front of the Page box

This works the same way as "Fr.".
- **The form.** The Page cell shows a fixed "p." label, styled as part of the field, then the input. The input holds only the number ("225").
- **What's stored doesn't change.** `manual.yaml` still says `page: p. 225`, so `bulletin.typ` and existing files are untouched.
- **Loading the form.** `manual.page_number(stored)` removes the prefix for the input.
- **Saving the form.** `manual.page_label(typed)` replaces today's version:
  - removes any prefix typed anyway: "p.", "p", "pg.", "pg", "page", any case, with or without a period or space, so "p.119", "p 119" and "Page 119" all work;
  - a value starting with a digit becomes `p. <value>` ("119" → "p. 119", and "209, 211" → "p. 209, 211");
  - a word from `NOT_A_PAGE` (Choir, Handout) is matched ignoring case and saved in its standard spelling ("handout" → "Handout");
  - anything else is saved as typed, with no prefix;
  - an empty box stays empty.
- **The words.** `NOT_A_PAGE = ["Choir", "Handout"]` in `manual.py`. They're the only ones in the history, and more can be added to the list.
  - The Page box gets the suggestion box too, offering just these words. Clicking the box lists them, and "h", Tab gives "Handout".
  - JS hides the "p." label whenever the box holds something that doesn't start with a digit. Without JS the label stays, but the saved text is still right.
- **Autofill** puts the bare number, or the word, into the box.
- **Even pages.** The warning checks the first number of a saved page. The "Example" template row ("p. 0") is already flagged by its title, so it gets no second note.

## Part 5: shortening long titles in print

### Abbreviations

- **`manual.ABBREVIATIONS`**: Apolytikion → Apol., Kontakion → Kont., Sunday → Sun. They're whole-word, and "Apolytikia" and "Kontakia" are included too. These are the owner's own abbreviations from the history.
- **`manual.short_title(title)`** returns the catalog's `short` for a catalog title. For any other title it applies the abbreviations. If nothing changes, it returns the title itself.
- **Typed abbreviations are expanded on save.** "Apol. for the Devout Woman" is saved as "Apolytikion for the Devout Woman". Then it prints in full whenever it fits, and it matches the same hymn in the suggestions. The volunteer sees the expanded title after saving.

### `manual.yaml`

- **`ManualHymnData` gets `short_title: str = ""`.** `manual.write` fills it in from `short_title(title)` for every hymn, so the web form never shows it and never needs to.
- **`manual.read`** ignores a stored `short_title` and recomputes it. A hand-edited title never keeps a stale short form.
- **Older files** without the field still render. Typst uses `it.at("short_title", default: it.title)`.
- **AGENTS.md** gets the new field in the build contract table.

### Choosing in Typst

- **`bulletin.typ`'s `front_page`** decides per row. It prints the full title if it fits on one line in the space left by the mode and page columns, and `short_title` otherwise.
  - Measure with `layout` and `measure` at the table's 8pt size. The widths of the mode and page columns, and the gutters, come from measuring those cells across all rows.
- **Why Typst, not a character limit in Python.** Typst knows the real width of every letter at the real font size. A character count would shorten some titles that fit and miss some that don't. The preview on the Sunday page shows the result.
- **If the short form doesn't fit either**, it wraps, as long titles do today.
- **The hint under the hymn table in the form** (`templates/sunday.html`) becomes: "Write the page number, or “Choir” or “Handout”. Long titles are shortened in print when they don't fit on one line (Apol., Kont., Sun.). To remove a hymn, clear its title."

## Tests

- **`test_manual.py`.**
  - The catalog loads, and every entry has at most one of `page` and `pages_by_mode`.
  - Every hymnal page in `data/hymns.yaml` appears in `data/table-of-contents.txt`, and every page in both is odd. A typo, a Greek page or a new hymnal edition shows up as a failing test.
  - History titles that differ from a catalog title or alias only in case, punctuation or abbreviations are merged into it.
  - A history-only title with a consistent mode and page gets them. One whose values varied gets none.
  - Order: most-used catalog hymns first, history-only titles last.
  - `page_label`:
    - "127", "p.127", "p 127", "P. 127", "pg 127" and "page 127" all give "p. 127";
    - "handout", "HANDOUT" and "choir" give "Handout", "Handout" and "Choir";
    - "Sung by the choir" is kept as typed;
    - an empty box stays empty.
  - `page_number` reverses it.
  - An even page gets an `unfinished` note.
  - `short_title` uses the catalog's `short` when there is one, the abbreviations otherwise, and the same title when there's nothing to shorten.
  - Abbreviations typed in a title are expanded.
  - `priest_label`:
    - "Joshua", "Fr. Joshua", "fr joshua", "Fr.Joshua" and "Father Joshua" all give "Fr. Joshua" (with the name's case kept);
    - "Francis" gives "Fr. Francis";
    - "Reader Service" and "reader service" stay without the prefix;
    - an empty name stays empty.
  - `priest_name` reverses it.
  - Priests are ordered by how often they were used, without the prefix, with "X" and "TBD" left out.
- **`test_web.py`.**
  - The Sunday page has the Resurrectional Apolytikion option with all eight `data-pages` entries, and "Kontakion for the Mother of God" with `data-mode="2"`.
  - The Priest input shows "Joshua" for a stored "Fr. Joshua". Saving "Joshua" stores "Fr. Joshua", and saving "Reader Service" stores it unchanged.
  - The Page input shows "225" for a stored "p. 225". Saving "225" stores "p. 225", and saving "handout" stores "Handout".
  - Saving still works when the form was filled in by hand, with no JS.
- **`test_render.py`.** A Sunday with a long hymn title prints its short form, and one with a short title prints it in full. Check this with `typst.query` on a `metadata` value the template emits per row, or by extracting the PDF's text. The booklet is still 2 pages.
- **The JS has no automated tests**, so there's no Node dependency. Check it by hand in Firefox and Chrome, and once on a phone:
  - "Res", then Tab, then mode 7 gives "Resurrectional Apolytikion, 7, p. 123".
  - "Kont", then Tab, gives mode 2, p. 225.
  - Typing "Ordinary" suggests "Kontakion for the Mother of God".
  - A typed "Handout" isn't replaced when the mode changes.
  - Clicking a filled-in Priest box lists every priest, and picking "Reader Service" hides the "Fr." label.
  - In the Page box, "h", then Tab gives "Handout" and hides the "p." label.
  - Enter picks a suggestion without sending the form.
  - With JS turned off, the form still works with the plain datalists.

## Later, not in this task

- **Pre-fill the first row.** Every ordinary Sunday starts with the Resurrectional Apolytikion in the mode of the week. `manual.template` could write that row instead of the "Example" placeholder. The mode comes from the DCS dismissal hymns (task 002), or can be worked out from the date of Pascha. With the catalog, the page follows.
- **Name the saint's hymns.** Task 006 (saint and feast XML) proposes naming the day's saint and feast hymns. The names it finds should be matched against this catalog, and any new ones added to it.

## Done when

- **Hymns.** On the Sunday page:
  - "Res", Tab, then a mode fills in the whole Resurrectional Apolytikion row with the right page.
  - "Kont", Tab fills in the Kontakion for the Mother of God with its mode and page.
- **Priests.** Clicking the Priest box lists the parish's priests next to a fixed "Fr.".
- **Pages.** The Page box has a fixed "p." for numbers and offers "Choir" and "Handout".
- **Printing.** A hymn title too long for its line prints with Apol., Kont. or Sun., and one that fits prints in full.
- **Without JS**, the form still works, and `uv run pytest` passes.
