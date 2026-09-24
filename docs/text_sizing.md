# text_sizing.py

Picks one font size for the two reading pages (pages 2–3), and where to break between them, so the readings fill the pages without overflowing. The estimate comes from a model, not from Typst.

## Inputs and outputs

Reads from `build/<date>/`: `epistle.yaml`, `gospel.yaml`, `digital_chant_stand.yaml` (Alleluia verses), `feed.yaml`.
Reads config: `data/layout.yaml` (geometry, shared with Typst) and `data/text_metrics.yaml` (model constants).

Writes to `feed.yaml`:

| Field | Used by | Meaning |
|---|---|---|
| `text_size_factor` | Typst | font size as % of `base_size_pt` |
| `alleluia_page_break`, `gospel_page_break` | Typst | where to force the break |
| `font_size_pt`, `layout`, `page_fill` | diagnostics | chosen size, layout name, estimated fill of pages 2/3 |

## Model

Content box: 85 × 128mm (A6 minus margins; the same as one booklet column).

The readings are three **sections**, each made of **blocks**:

- **E**: prokeimenon + verse, then epistle paragraphs
- **A**: Alleluia verses
- **G**: gospel paragraphs

Height of a block at font size `s`:

```
cpl   = η·W / (w̄·s)                             chars per line
lines = Σ ceil(chars_i / cpl)  (+ wrapped heading lines)
h     = s · (ℓ·lines + (σ − leading)·(P − 1) + k)
```

- `w̄` glyph width, `η` wrap efficiency, `ℓ` line pitch (all in em)
- `σ − leading`: paragraph spacing *replaces* the leading, so body paragraphs (σ = 0.65 = leading) cost nothing extra and verses (0.8) cost 0.15em
- `k`: fixed em-height of the headings, the chapverse line and the gaps
- each paragraph gets +2 chars for its indent

`h` never decreases as `s` grows, which is what makes the solver work.

## Layouts

| Layout | Page 2 | Page 3 | Constraint |
|---|---|---|---|
| `split_before_alleluia` | E | A + G | each page ≤ H |
| `split_before_gospel` | E + A | G | each page ≤ H |
| `flow` | E, A, G run freely | | total + slack ≤ 2H |

`H` = page height × (1 − `safety_margin`).

## Solver

For each layout, the largest `s` ≤ `base_size_pt` that satisfies all its constraints:

1. If `s_max` fits, return it.
2. Start from the closed form. Replacing `ceil` by its average (+½ line) makes `h` quadratic, `a·s² + b·s = H`.
3. Bisect to 0.05pt, then snap to the largest 0.1pt step that fits.

The biggest size wins. On a tie the order is `split_before_alleluia` > `split_before_gospel` > `flow`, so the Alleluia stays with the Gospel when possible. There's no minimum size, but anything under 7pt prints a notice.

## Usage

```sh
uv run text_sizing.py 2026-09-27            # re-size one build dir (writes feed.yaml)
uv run text_sizing.py --explain 2026-09-27  # per-block heights and each layout's size (read-only)
uv run text_sizing.py --report              # sizing for all of build/ (read-only)
uv run pytest                               # unit tests
```

`sunday.fetch_readings` (used by `main.py` and the web UI) runs it after scraping, and the web UI's readings editor runs it after every save.

## Tuning

The constants in `text_metrics.yaml` were measured from rendered PDFs and lean conservative, especially below ~8pt. To tune:

1. If pages overflow or run consistently underfilled, adjust `glyph_advance_em` first.
2. Run `--report`.
3. Compile a spread of dates (short, typical, 2026-05-17) and check that the booklet stays at 2 sheets.
