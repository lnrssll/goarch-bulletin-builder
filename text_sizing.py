import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

from yaml_io import read_yaml, write_yaml

BUILD_DIR = Path("build")
LAYOUT_PATH = Path("data/layout.yaml")
METRICS_PATH = Path("data/text_metrics.yaml")

PT_PER_MM = 72 / 25.4
SOLVE_TOLERANCE_PT = 0.05
SIZE_STEP_PT = 0.1
LAYOUT_TIE_TOLERANCE_PT = 0.0  # accept a smaller size (in pt) to keep a preferred layout
SMALL_SIZE_NOTICE_PT = 7.0
VERSE_LABEL = "Verse: "
READING_HEADING = "The Reading is from "

# in order of preference
LAYOUTS = ("split_before_alleluia", "split_before_gospel", "flow")
REQUIRED_FILES = ("epistle.yaml", "gospel.yaml", "digital_chant_stand.yaml", "feed.yaml")


@dataclass
class PageBox:
    width: float
    height: float


@dataclass
class TextMetrics:
    glyph_advance_em: float
    heading_advance_em: float
    wrap_efficiency: float
    line_pitch_em: float
    leading_em: float
    para_spacing_em: float
    verse_spacing_em: float
    indent_em: float
    epistle_fixed_em: float
    alleluia_fixed_em: float
    gospel_fixed_em: float
    flow_slack_em: float
    safety_margin: float


@dataclass
class Block:
    name: str
    paragraphs: list[int]
    fixed_em: float
    spacing_em: float
    heading_chars: int = 0  # a heading's first line is part of fixed_em; wrapped lines are not


@dataclass
class PageConstraint:
    blocks: list[Block]
    height: float


@dataclass
class SizingResult:
    font_size_pt: float
    layout: str
    alleluia_page_break: bool
    gospel_page_break: bool
    page_fill: tuple[float, float]
    candidates: dict[str, float] = field(default_factory=dict)


@dataclass
class Model:
    box: PageBox
    metrics: TextMetrics
    base_size_pt: float


class MissingBuildData(Exception):
    pass


################################################################################
# model
################################################################################


def chars_per_line(
    s: float, box: PageBox, metrics: TextMetrics, advance_em: float | None = None
) -> float:
    advance_em = advance_em or metrics.glyph_advance_em
    return metrics.wrap_efficiency * box.width / (advance_em * s)


def block_height(block: Block, s: float, box: PageBox, metrics: TextMetrics) -> float:
    cpl = chars_per_line(s, box, metrics)
    lines = sum(math.ceil(c / cpl) for c in block.paragraphs)
    if block.heading_chars:
        heading_cpl = chars_per_line(s, box, metrics, metrics.heading_advance_em)
        lines += math.ceil(block.heading_chars / heading_cpl) - 1
    # paragraph spacing takes the place of the leading between two lines
    gaps = max(len(block.paragraphs) - 1, 0)
    return s * (
        metrics.line_pitch_em * lines
        + (block.spacing_em - metrics.leading_em) * gaps
        + block.fixed_em
    )


def blocks_height(blocks: list[Block], s: float, box: PageBox, metrics: TextMetrics) -> float:
    return sum(block_height(b, s, box, metrics) for b in blocks)


def closed_form_size(constraint: PageConstraint, box: PageBox, metrics: TextMetrics) -> float:
    # h(s) = a*s^2 + b*s, taking the expected value c/cpl + 1/2 in place of ceil
    pitch = metrics.line_pitch_em
    usable_width = metrics.wrap_efficiency * box.width
    a = 0.0
    b = 0.0
    for block in constraint.blocks:
        P = len(block.paragraphs)
        a += pitch * metrics.glyph_advance_em * sum(block.paragraphs) / usable_width
        b += (
            pitch * P / 2
            + (block.spacing_em - metrics.leading_em) * max(P - 1, 0)
            + block.fixed_em
        )
        if block.heading_chars:
            a += pitch * metrics.heading_advance_em * block.heading_chars / usable_width
            b -= pitch / 2

    H = constraint.height
    if a == 0:
        return H / b if b > 0 else math.inf
    return (-b + math.sqrt(b * b + 4 * a * H)) / (2 * a)


def round_down(s: float) -> float:
    rounded = math.floor(s / SIZE_STEP_PT + 1e-9) * SIZE_STEP_PT
    return round(rounded, 1) if rounded > 0 else s


def max_size_one(
    constraint: PageConstraint, box: PageBox, metrics: TextMetrics, s_max: float
) -> float:
    def fits(s: float) -> bool:
        return blocks_height(constraint.blocks, s, box, metrics) <= constraint.height

    if fits(s_max):
        return s_max

    lo, hi = 0.0, s_max
    guess = closed_form_size(constraint, box, metrics)
    if 0 < guess < s_max:
        if fits(guess):
            lo = guess
        else:
            hi = guess

    while hi - lo > SOLVE_TOLERANCE_PT:
        mid = (lo + hi) / 2
        if fits(mid):
            lo = mid
        else:
            hi = mid

    # the tolerance is finer than the step, so the next step up may still fit
    s = round_down(lo)
    while s + SIZE_STEP_PT <= hi and fits(round(s + SIZE_STEP_PT, 1)):
        s = round(s + SIZE_STEP_PT, 1)
    return s


def max_size_for(
    page_constraints: list[PageConstraint],
    box: PageBox,
    metrics: TextMetrics,
    s_max: float,
) -> float:
    return min(max_size_one(c, box, metrics, s_max) for c in page_constraints)


def layout_pages(
    layout: str,
    epistle: list[Block],
    alleluia: list[Block],
    gospel: list[Block],
    metrics: TextMetrics,
) -> list[list[Block]]:
    if layout == "split_before_alleluia":
        return [epistle, alleluia + gospel]
    if layout == "split_before_gospel":
        return [epistle + alleluia, gospel]
    if layout == "flow":
        slack = Block("flow_slack", [], metrics.flow_slack_em, 0.0)
        return [epistle + alleluia + gospel + [slack]]

    raise ValueError(f"unknown layout {layout}")


def layout_constraints(
    layout: str,
    epistle: list[Block],
    alleluia: list[Block],
    gospel: list[Block],
    box: PageBox,
    metrics: TextMetrics,
) -> list[PageConstraint]:
    pages = layout_pages(layout, epistle, alleluia, gospel, metrics)
    both_pages_height = 2 * box.height * (1 - metrics.safety_margin)
    return [PageConstraint(blocks, both_pages_height / len(pages)) for blocks in pages]


def page_fill(
    layout: str,
    s: float,
    epistle: list[Block],
    alleluia: list[Block],
    gospel: list[Block],
    box: PageBox,
    metrics: TextMetrics,
) -> tuple[float, float]:
    pages = layout_pages(layout, epistle, alleluia, gospel, metrics)
    heights = [blocks_height(blocks, s, box, metrics) for blocks in pages]
    if len(heights) == 1:
        total = heights[0]
        heights = [min(total, box.height), max(total - box.height, 0.0)]

    first, second = (round(h / box.height, 3) for h in heights)
    return first, second


def choose_layout(
    epistle: list[Block],
    alleluia: list[Block],
    gospel: list[Block],
    box: PageBox,
    metrics: TextMetrics,
    s_max: float,
) -> SizingResult:
    candidates = {
        layout: max_size_for(
            layout_constraints(layout, epistle, alleluia, gospel, box, metrics),
            box,
            metrics,
            s_max,
        )
        for layout in LAYOUTS
    }
    s_best = max(candidates.values())
    layout = next(
        L for L in LAYOUTS if candidates[L] >= s_best - LAYOUT_TIE_TOLERANCE_PT - 1e-9
    )
    s = candidates[layout]

    return SizingResult(
        font_size_pt=s,
        layout=layout,
        alleluia_page_break=layout == "split_before_alleluia",
        gospel_page_break=layout == "split_before_gospel",
        page_fill=page_fill(layout, s, epistle, alleluia, gospel, box, metrics),
        candidates=candidates,
    )


################################################################################
# content -> blocks
################################################################################


def indent_chars(metrics: TextMetrics) -> int:
    return round(metrics.indent_em / metrics.glyph_advance_em)


def epistle_blocks(epistle: dict, metrics: TextMetrics) -> list[Block]:
    extra = indent_chars(metrics)
    verses = [epistle["prokeimenon"], VERSE_LABEL + epistle["verse"]]
    return [
        Block(
            "prokeimenon",
            [len(v) + extra for v in verses],
            metrics.epistle_fixed_em,
            metrics.verse_spacing_em,
        ),
        Block(
            "epistle",
            [len(p) + extra for p in epistle["text"]],
            0.0,
            metrics.para_spacing_em,
            len(READING_HEADING + epistle["book"]),
        ),
    ]


def alleluia_blocks(verses: list[str], metrics: TextMetrics) -> list[Block]:
    extra = indent_chars(metrics)
    return [
        Block(
            "alleluia",
            [len(v) + extra for v in verses],
            metrics.alleluia_fixed_em,
            metrics.verse_spacing_em,
        )
    ]


def gospel_blocks(gospel: dict, metrics: TextMetrics) -> list[Block]:
    extra = indent_chars(metrics)
    return [
        Block(
            "gospel",
            [len(p) + extra for p in gospel["text"]],
            metrics.gospel_fixed_em,
            metrics.para_spacing_em,
            len(READING_HEADING + gospel["book"]),
        )
    ]


################################################################################
# config and build dirs
################################################################################


def load_layout(path: Path = LAYOUT_PATH) -> dict:
    return read_yaml(path)


def page_box(layout: dict) -> PageBox:
    page = layout["page"]
    width = page["width_mm"] - 2 * page["margin_mm"]
    booklet_column = (
        2 * page["width_mm"] - 2 * page["margin_mm"] - layout["booklet"]["gutter_mm"]
    ) / 2
    height = page["height_mm"] - 2 * page["margin_mm"]
    return PageBox(min(width, booklet_column) * PT_PER_MM, height * PT_PER_MM)


def load_metrics(layout: dict, path: Path = METRICS_PATH) -> TextMetrics:
    text = layout["text"]
    return TextMetrics(
        **read_yaml(path),
        leading_em=text["leading_em"],
        para_spacing_em=text["para_spacing_em"],
        verse_spacing_em=text["verse_spacing_em"],
        indent_em=text["indent_em"],
    )


def load_model() -> Model:
    layout = load_layout()
    return Model(page_box(layout), load_metrics(layout), layout["text"]["base_size_pt"])


def load_build(out_dir: Path) -> dict[str, dict]:
    missing = [name for name in REQUIRED_FILES if not (out_dir / name).exists()]
    if missing:
        raise MissingBuildData(f"{out_dir} is missing {', '.join(missing)}")
    return {name: read_yaml(out_dir / name) for name in REQUIRED_FILES}


def build_blocks(
    data: dict[str, dict], metrics: TextMetrics
) -> tuple[list[Block], list[Block], list[Block]]:
    return (
        epistle_blocks(data["epistle.yaml"], metrics),
        alleluia_blocks(data["digital_chant_stand.yaml"]["alleluia"] or [], metrics),
        gospel_blocks(data["gospel.yaml"], metrics),
    )


def size_build(
    out_dir: Path, model: Model
) -> tuple[SizingResult, dict[str, dict], tuple[list[Block], list[Block], list[Block]]]:
    data = load_build(out_dir)
    blocks = build_blocks(data, model.metrics)
    result = choose_layout(*blocks, model.box, model.metrics, model.base_size_pt)
    return result, data, blocks


def run(out_dir: Path) -> SizingResult:
    model = load_model()
    result, data, _ = size_build(out_dir, model)

    feed = data["feed.yaml"]
    feed["text_size_factor"] = round(100 * result.font_size_pt / model.base_size_pt, 1)
    feed["alleluia_page_break"] = result.alleluia_page_break
    feed["gospel_page_break"] = result.gospel_page_break
    feed["font_size_pt"] = result.font_size_pt
    feed["layout"] = result.layout
    feed["page_fill"] = list(result.page_fill)
    write_yaml(feed, out_dir / "feed.yaml")

    print(f"readings: {result.font_size_pt}pt, {result.layout}")
    if result.font_size_pt < SMALL_SIZE_NOTICE_PT:
        print(
            f"notice: readings set at {result.font_size_pt}pt, check the PDF",
            file=sys.stderr,
        )

    return result


################################################################################
# diagnostics
################################################################################


def legacy_sizing(epistle_text: list[str], gospel_text: list[str]) -> tuple[float, bool, bool]:
    # verbatim copy of the pre-text_sizing formula, used only by --report
    def factor(text: list[str]) -> int:
        n = len(" ".join(text))
        return min(round(100.0 * (1 - (1 - 1000.0 / n) ** 2)), 100)

    epistle_char_count = len(" ".join(epistle_text))
    gospel_char_count = len(" ".join(gospel_text))
    epistle_factor = factor(epistle_text)
    gospel_factor = max(1, factor(gospel_text))

    text_size_factor_decimal = math.sqrt((gospel_factor / 100.0) * (epistle_factor / 100.0))
    text_size_factor = 100 * round(text_size_factor_decimal, 2)

    epistle_text_area_units = epistle_char_count * text_size_factor_decimal**2
    gospel_text_area_units = gospel_char_count * text_size_factor_decimal**2

    alleluia_page_break = max(gospel_text_area_units, epistle_text_area_units) < 1_200
    alleluia_fits_on_epistle_page = epistle_text_area_units < 1_000
    gospel_reading_fits_on_gospel_page = gospel_text_area_units < 1_400
    gospel_page_break = (
        alleluia_fits_on_epistle_page
        and gospel_reading_fits_on_gospel_page
        and not alleluia_page_break
    )

    return text_size_factor, alleluia_page_break, gospel_page_break


def breaks_label(alleluia_page_break: bool, gospel_page_break: bool) -> str:
    if alleluia_page_break:
        return "|A"
    if gospel_page_break:
        return "|G"
    return "flow"


def explain(out_dir: Path) -> None:
    model = load_model()
    box, metrics, base_size = model.box, model.metrics, model.base_size_pt
    result, _, blocks = size_build(out_dir, model)
    s = result.font_size_pt

    print(f"{out_dir}")
    print(f"box: {box.width:.1f} x {box.height:.1f}pt, safety margin {metrics.safety_margin:.0%}")
    print(f"chars/line at {s}pt: {chars_per_line(s, box, metrics):.1f}")
    print()
    print(f"{'block':<12} {'chars':>6} {'paras':>6} {'height@' + str(s):>12} {'@' + str(base_size):>8}")
    for block in [b for section in blocks for b in section]:
        print(
            f"{block.name:<12} {sum(block.paragraphs):>6} {len(block.paragraphs):>6} "
            f"{block_height(block, s, box, metrics):>12.1f} "
            f"{block_height(block, base_size, box, metrics):>8.1f}"
        )
    print()
    for name, size in result.candidates.items():
        marker = "  <-" if name == result.layout else ""
        print(f"{name:<22} {size:>5.1f}pt{marker}")
    print()
    print(f"chosen: {result.layout} at {s}pt, page fill {result.page_fill[0]:.0%} / {result.page_fill[1]:.0%}")


def report(build_dir: Path = BUILD_DIR) -> None:
    model = load_model()
    base_size = model.base_size_pt

    print(
        f"{'date':<11} {'E chars':>7} {'P':>2} {'G chars':>7} {'P':>2} "
        f"{'old pt':>6} {'old':>4}   {'new pt':>6} {'layout':<22} {'fill':>9}"
    )
    for out_dir in sorted(p for p in build_dir.iterdir() if p.is_dir()):
        try:
            result, data, _ = size_build(out_dir, model)
        except MissingBuildData as e:
            print(f"{out_dir.name:<11} skipped: {e}")
            continue

        epistle_text = data["epistle.yaml"]["text"]
        gospel_text = data["gospel.yaml"]["text"]
        try:
            old_factor, old_alleluia, old_gospel = legacy_sizing(epistle_text, gospel_text)
            old = f"{base_size * old_factor / 100:>6.1f} {breaks_label(old_alleluia, old_gospel):>4}"
        except ValueError:
            old = f"{'error':>6} {'':>4}"

        fill = f"{result.page_fill[0]:.0%}/{result.page_fill[1]:.0%}"
        print(
            f"{out_dir.name:<11} {len(' '.join(epistle_text)):>7} {len(epistle_text):>2} "
            f"{len(' '.join(gospel_text)):>7} {len(gospel_text):>2} "
            f"{old}   {result.font_size_pt:>6.1f} {result.layout:<22} {fill:>9}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Size the readings of a build dir to fit the two reading pages"
    )
    parser.add_argument("date", nargs="?", help="build date, YYYY-MM-DD")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--explain", action="store_true", help="print the sizing for DATE, read-only")
    mode.add_argument("--report", action="store_true", help="print the sizing for all of build/, read-only")
    args = parser.parse_args()

    if args.report:
        report()
        return 0

    if args.date is None:
        parser.error("DATE is required unless --report is given")

    out_dir = BUILD_DIR / args.date
    try:
        if args.explain:
            explain(out_dir)
        else:
            run(out_dir)
    except MissingBuildData as e:
        parser.error(str(e))

    return 0


if __name__ == "__main__":
    sys.exit(main())
