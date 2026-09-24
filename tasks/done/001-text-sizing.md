# Plan: area-based text sizing (`text_sizing.py`)

## Goal

Replace `compute_text_size_and_page_breaks` (and the per-reading `text_size_factor` formula) in `goarch_xml_feed.py` with a dedicated module, `text_sizing.py`. The module estimates how much page area the readings content needs as a function of font size. It then solves for the largest single font size, and the page-break arrangement, that fits the two reading pages.

## Decisions

- **One font size for both reading pages.** Pages 2 and 3 always share the same size.
- **The Alleluia stays with the Gospel when that fits.** If breaking before the Alleluia (Alleluia + Gospel on page 3) reaches the same size as the best alternative, use it.
- **No minimum font size.** The content must fit, so the solver shrinks as far as needed. It prints a notice for unusually small results (e.g. under 7pt) so you can look at the PDF, but it never clamps.
- **Pure estimation.** Constants are hand-estimated from the font and the Typst settings. Nothing calls Typst to measure or check at runtime or in validation.

## Why the current approach needs replacing

Current per-reading formula: `f(n) = 100 · (1 − (1 − 1000/n)²)`, capped at 100.

| chars `n` | 400 | 500 | 667 | 800 | 1000 | 1500 | 2000 | 3777 |
|---|---|---|---|---|---|---|---|---|
| `f(n)` | **−125** | **0** | 75 | 94 | 100 | 89 | 75 | 46 |

1. **It isn't monotonic.** The curve peaks at 1000 chars. Shorter readings get *smaller* text, and below ~500 chars the factor is zero or negative. (The `max(1, …)` clamp on the gospel hides the symptom but doesn't fix it; the epistle has no clamp.)
2. **It ignores page geometry.** The page width and height, and the line pitch, never appear. The magic numbers (1000 for the formula; 1000, 1200 and 1400 for the breaks) are only proxies for them.
3. **It measures only part of the content.** The prokeimenon, the Alleluia verses, the headings, the chapter/verse lines and paragraph spacing all take up space, but only the reading bodies are counted. Paragraph count also matters, because each paragraph wastes about half a line on average plus the paragraph spacing. Real data runs from 1 to 5 paragraphs.
4. **The final size doesn't come from a fit.** It's the geometric mean of two independent guesses, so nothing guarantees the chosen size fits the chosen layout.
5. **The page-break rules are separate heuristics.** They don't come from the same model that picks the size.

Observed data range in `build/` (30 Sundays, Feb–Sep 2026): epistle 528–2279 chars, gospel 493–3777 chars, 1–5 paragraphs each.

## The model

### Page geometry (points; 1mm = 2.8346pt)

The A6 standalone pages and each booklet column come out to the same content box:

- A6 page: 105 × 148mm with 1cm margins → **W = 85mm ≈ 240.9pt, H = 128mm ≈ 362.8pt**.
- Booklet: A5 landscape is 210 × 148mm. With 1cm margins and a 2cm gutter, each column is (210 − 20 − 20)/2 = 85mm wide × 128mm tall, which is identical.

The model therefore uses a single box (W, H). The code should still take these values as inputs, not hard-coded constants (see Step 1).

### Content blocks on the reading pages

Everything in `readings()` scales with the chosen size `s`, because headings and spacing are em-relative. The blocks, in order:

| Block | Content |
|---|---|
| `E` epistle section | "The Prokeimenon" heading, prokeimenon + verse (hanging indent), "The Reading is from …" heading, chapverse line, epistle paragraphs |
| `A` alleluia section | heading and 2–3 verses (hanging indent) |
| `G` gospel section | heading, chapverse line, gospel paragraphs |

The prokeimenon, its verse, and each Alleluia verse count as short paragraphs in the model. They use the same line math with their own spacing (`.8em`).

### Height of a block at font size `s`

For a run of paragraphs with character counts `c₁ … c_P`, set in width `W` at size `s`:

```
chars_per_line(s) = η · W / (w̄ · s)          # w̄ = mean glyph advance (em), η = wrap efficiency (<1)
lines_i(s)        = ceil(c_i / chars_per_line(s))
h_text(s)         = s · ( ℓ · Σ lines_i  +  σ · (P − 1) )
h_block(s)        = h_text(s) + s · k_block    # k_block = fixed em-height of the block's headings/labels
```

- `w̄`: average advance width per character, in em, for the body font (Libertinus Serif, Typst's default).
- `η`: greedy line-breaking wastes about half a word at the end of each line. Folding that into an efficiency factor keeps the formula simple.
- `ℓ`: line pitch in em, which is glyph box plus `par.leading`.
- `σ`: paragraph spacing in em. It's `0.65em` in `reading_block` and `.8em` for the prokeimenon and alleluia.
- `k_block`: every fixed-height piece (headings, their spacing above and below, the chapverse line) as one em-constant per block type.
- The first-line indent (`1em`) and hanging indent (`1em`) each take about 2 chars of width from one line per paragraph. Add 2 to each `c_i`.

### Estimated constants

These are starting estimates, stored in `data/text_metrics.yaml` so they can be tuned without code changes:

| Constant | Estimate | Reasoning |
|---|---|---|
| `w̄` | 0.46 em | Typical for a book serif like Libertinus on English prose, spaces included |
| `η` | 0.95 | About half a ~5.5-char word lost per ~50-char line |
| `ℓ` | 1.30 em | Typst default `top-edge: cap-height` (~0.65em) + `leading: 0.65em` |
| `σ` body / verse | 0.65 / 0.80 em | Taken straight from `bulletin.typ` |
| heading (`===`) | ≈ 2.5 em each | ~1 line of bold text plus Typst's default block spacing above and below |
| `k_E` | ≈ 2 headings + 1 chapverse line ≈ 6.5 em | |
| `k_A` | ≈ 1 heading ≈ 2.5 em | |
| `k_G` | ≈ 1 heading + 1 chapverse line ≈ 4 em | |
| `flow_slack` | ≈ 1 line + 1 heading ≈ 4 em | Space lost at a free page break (partial line, heading pushed to next page) |

**Sanity check** with these values at 10pt: about 50 chars/line and about 27 lines/page, which is roughly 1350 chars/page before headings. That's consistent with the hand-tuned 1000–1400 thresholds in the current code, which suggests the estimates are in the right range.

**Rounding toward safety.** Estimates can be off. Solve against `H · (1 − margin)` with `margin = 0.03` (also in `text_metrics.yaml`) so small errors don't cause an overflow. If PDFs come out consistently underfilled or overflowing, adjust `w̄` first, since it has the largest effect.

### Closed form: the "area" formulation

If `ceil` is replaced by its expected value (`lines_i ≈ c_i/cpl + ½`), the height becomes a quadratic in `s`:

```
h(s) = a·s² + b·s

a = ℓ · w̄ · C / (η · W)                   # C = total chars  →  the text's *area* term  (area/W)
b = ℓ · P/2 + σ · (P − 1) + k             # per-paragraph and fixed overhead (linear in s)
```

This is the rigorous version of the original idea. `a·s²·W` is the ink area of the text at size `s`, and `b·s` is the overhead that doesn't scale with the character count. Fitting a region of height `H`:

```
a·s² + b·s ≤ H   ⇒   s* = (−b + √(b² + 4aH)) / (2a)
```

The closed form gives a fast, explainable first estimate. It's also a good starting bracket for the exact solve below.

### Exact solve

`h_block(s)` with real `ceil` is a step function that never decreases, so the largest `s` with `h(s) ≤ H` can be found by **bisection** on `(0, s_max]`, with `s_max = 10pt`. Use a 0.05pt tolerance and start from the closed-form estimate. Round down to 0.1pt at the end, so the result errs toward fitting. There is no lower bound, because a small enough `s` always fits.

### Layout candidates

There are always exactly two reading pages: pages 2–3 of the 4-page booklet. There are three ways to arrange the content across them. They map onto the existing `feed.yaml` flags:

| Layout | Page 2 | Page 3 | Constraint | `alleluia_page_break` | `gospel_page_break` |
|---|---|---|---|---|---|
| `split_before_alleluia` | E | A + G | `h_E ≤ H` and `h_A + h_G ≤ H` | true | false |
| `split_before_gospel` | E + A | G | `h_E + h_A ≤ H` and `h_G ≤ H` | false | true |
| `flow` | E, A, G flowing freely | (continued) | `h_E + h_A + h_G ≤ 2H − slack` | false | false |

For each layout, solve for `s*_L` as the largest `s` that satisfies **all** of its constraints (the minimum over the constraints' individual solutions). Let `s_best = max_L s*_L`. Then take the first layout in this order that reaches `s_best`:

1. `split_before_alleluia`, which keeps the Alleluia with the Gospel.
2. `split_before_gospel`.
3. `flow`.

"Reaches" means equal after rounding down to 0.1pt. The tolerance is a named constant. It can be raised later (e.g. accept up to 0.2pt smaller text to keep a clean break) if `flow` wins too often.

All three layouts must be solved; none can be skipped. Sundays that fit at 10pt either way resolve to `split_before_alleluia`. Very long Sundays (e.g. 2026-05-17, 2279 + 3777 chars) will likely end up in `flow`, because only free flow can balance the text across both pages.

## Module design: `text_sizing.py`

```python
@dataclass
class PageBox:            # content box, in pt
    width: float
    height: float

@dataclass
class TextMetrics:        # loaded from data/text_metrics.yaml
    glyph_advance_em: float     # w̄
    wrap_efficiency: float      # η
    line_pitch_em: float        # ℓ
    para_spacing_em: float      # σ (reading bodies)
    verse_spacing_em: float     # σ (prokeimenon / alleluia)
    epistle_fixed_em: float     # k_E
    alleluia_fixed_em: float    # k_A
    gospel_fixed_em: float      # k_G
    flow_slack_em: float
    safety_margin: float

@dataclass
class Block:
    name: str
    paragraphs: List[int]       # char count per paragraph
    fixed_em: float
    spacing_em: float

@dataclass
class SizingResult:
    font_size_pt: float
    layout: str                 # "split_before_alleluia" | "split_before_gospel" | "flow"
    alleluia_page_break: bool
    gospel_page_break: bool
    page_fill: Tuple[float, float]  # estimated fraction of H used on pages 2 and 3

def block_height(block, s, box, metrics) -> float
def max_size_for(page_constraints, box, metrics, s_max) -> float   # closed form → bisection
def choose_layout(epistle, alleluia, gospel, box, metrics, s_max) -> SizingResult
```

The functions are pure: they take no I/O, so they're easy to unit test. The CLI lives under `if __name__ == "__main__":`:
- `uv run text_sizing.py <date>` re-sizes one build dir and rewrites the sizing fields in `feed.yaml`.
- `uv run text_sizing.py --explain <date>` prints each block's chars, paragraphs and heights, every layout's `s*`, and the choice.
- `uv run text_sizing.py --report` prints the table for all of `build/`.

`--explain` and `--report` are **read-only and offline**. They only read YAML files already in `build/<date>/` (`epistle.yaml`, `gospel.yaml`, `digital_chant_stand.yaml`, `feed.yaml`). They make no network calls and write nothing. `text_sizing.py` must not import the scraper modules or `httpx`. A date missing any of those files is skipped with a note, not fetched.

The "old" column in `--report` doesn't read `text_size_factor` from `feed.yaml`. That value may have been written by an earlier version of the formula, and once this is integrated it gets overwritten with the new size. Instead, the report recomputes the old result with a verbatim copy of the old formula (`legacy_sizing()`, used only by the report) applied to the reading text in `epistle.yaml`/`gospel.yaml`. Step 6 deletes `text_char_count` from the YAML, which is fine because counts are derived from `text[]`.

## Implementation steps

1. **Single source of truth for geometry.** Add `data/layout.yaml` with page size, margins, base font size, and paragraph spacings. `bulletin.typ` and `booklet.typ` read it with `yaml(...)`, and `text_sizing.py` reads it too. That keeps the Python model and the Typst layout from drifting apart.
2. **Write `data/text_metrics.yaml`** with the estimated constants above.
3. **Write `text_sizing.py`**: the model, the closed-form and bisection solvers, layout selection, and the CLI.
4. **Integrate as its own step in `main.py`.** Run it after both scrapers. It reads `epistle.yaml`, `gospel.yaml` and `digital_chant_stand.yaml` (for the Alleluia verses), then updates `feed.yaml`. The scrapers stay free of layout logic, and sizing can be re-run without re-scraping.
5. **Keep the `feed.yaml` contract.** Keep writing `text_size_factor` (percent of 10pt), `alleluia_page_break` and `gospel_page_break`, so the Typst side needs no change in this step. Also add `font_size_pt`, `layout` and `page_fill` for diagnostics. Once everything else is stable, `bulletin.typ` can switch to `font_size_pt`.
6. **Remove the old code.** Delete `text_size_factor`/`text_char_count` from `EpistlePageData`/`GospelPageData`, plus `compute_text_size_and_page_breaks` and the `max(1, …)` clamp.
7. **Update `AGENTS.md`** (the Layout logic section and the build-contract table).

## Validation

- **Unit tests** (`tests/test_text_sizing.py`, `pytest` as a dev dependency). They check that:
  - `block_height` never decreases as `s` grows.
  - The closed form agrees with bisection within one line.
  - Size never increases when chars increase with all else equal, so the old non-monotonic behavior can't come back.
  - Tiny readings get `s_max`.
  - Huge readings still return a size that fits the model, however small.
  - The layout preference order and tie-breaking work as specified.
- **Report over existing builds.** `--report` prints date, chars, old size and breaks → new size and layout, and estimated fill for all 30 dates. Short readings (e.g. 2026-09-13, gospel 493 chars) should come out at 10pt.
- **Spot-check PDFs by eye.** Compile a handful of dates across the range (short, typical, and the 2026-05-17 extreme) and check for overflow or large gaps. Tune `text_metrics.yaml` if they're off.

## Future (not now)

- Measure the constants with Typst (`measure()` + `typst query`) across all builds and fit them by least squares instead of estimating.
- A Typst-backed `--check` that asserts page count and section start pages for every build.

## Out of scope

- Front page and back page sizing (fixed content, fixed sizes).
- Hyphenation and justification. Turning on `par(justify: true)` or hyphenation would change `η`, so the constants would need re-tuning.
- Adding more pages to the booklet for very long readings.
