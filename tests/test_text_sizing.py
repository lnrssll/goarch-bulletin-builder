from pathlib import Path

import pytest

from text_sizing import (
    LAYOUTS,
    Block,
    PageConstraint,
    alleluia_blocks,
    block_height,
    blocks_height,
    choose_layout,
    closed_form_size,
    epistle_blocks,
    gospel_blocks,
    layout_constraints,
    load_layout,
    load_metrics,
    max_size_one,
    page_box,
)

ROOT = Path(__file__).resolve().parent.parent
S_MAX = 10.0

WORDS = "and the Lord said to them that the kingdom of God is at hand "


def text(chars: int) -> str:
    return (WORDS * (chars // len(WORDS) + 1))[:chars]


@pytest.fixture(scope="module")
def layout():
    return load_layout(ROOT / "data/layout.yaml")


@pytest.fixture(scope="module")
def metrics(layout):
    return load_metrics(layout, ROOT / "data/text_metrics.yaml")


@pytest.fixture(scope="module")
def box(layout):
    return page_box(layout)


def sections(metrics, epistle_chars=900, gospel_chars=1100, paragraphs=1):
    epistle = {
        "book": "St. Paul's Letter to the Galatians",
        "prokeimenon": "The Lord will give strength to his people.",
        "verse": "Bring to the Lord, O sons of God, bring to the Lord honor and glory.",
        "text": [text(epistle_chars // paragraphs)] * paragraphs,
    }
    gospel = {
        "book": "The Holy Gospel According to St. Luke",
        "text": [text(gospel_chars // paragraphs)] * paragraphs,
    }
    alleluia = [
        "It is good to give thanks to the Lord and to sing to Your name, O Most High.",
        "To proclaim Your mercy in the morning and Your truth at night.",
    ]
    return (
        epistle_blocks(epistle, metrics),
        alleluia_blocks(alleluia, metrics),
        gospel_blocks(gospel, metrics),
    )


def size_for(metrics, box, **kwargs):
    return choose_layout(*sections(metrics, **kwargs), box, metrics, S_MAX)


def test_block_height_never_decreases(metrics, box):
    block = Block("gospel", [1200, 400, 30], metrics.gospel_fixed_em, metrics.para_spacing_em, 60)
    sizes = [2 + 0.01 * i for i in range(801)]
    heights = [block_height(block, s, box, metrics) for s in sizes]
    assert all(b >= a for a, b in zip(heights, heights[1:]))


@pytest.mark.parametrize("chars", [300, 1000, 2500, 6000])
@pytest.mark.parametrize("paragraphs", [1, 3, 5])
def test_closed_form_agrees_with_bisection(metrics, box, chars, paragraphs):
    block = Block("gospel", [chars // paragraphs] * paragraphs, metrics.gospel_fixed_em, metrics.para_spacing_em)
    constraint = PageConstraint([block], box.height)
    closed = closed_form_size(constraint, box, metrics)
    exact = max_size_one(constraint, box, metrics, s_max=100.0)

    # within one line (plus the final round-down) of each other
    line_height = metrics.line_pitch_em * exact
    height_at_closed = blocks_height([block], closed, box, metrics)
    assert abs(height_at_closed - box.height) <= line_height * paragraphs
    assert abs(closed - exact) < 0.1 * exact + 0.1


@pytest.mark.parametrize("fixed", ["epistle", "gospel"])
def test_size_never_increases_with_more_chars(metrics, box, fixed):
    previous = S_MAX
    for chars in range(200, 6001, 100):
        kwargs = {"epistle_chars": 900, "gospel_chars": 900}
        kwargs["gospel_chars" if fixed == "epistle" else "epistle_chars"] = chars
        size = size_for(metrics, box, **kwargs).font_size_pt
        assert size <= previous
        previous = size


def test_tiny_readings_get_max_size(metrics, box):
    result = size_for(metrics, box, epistle_chars=100, gospel_chars=100)
    assert result.font_size_pt == S_MAX
    assert result.layout == "split_before_alleluia"


def test_huge_readings_still_fit(metrics, box):
    epistle, alleluia, gospel = sections(metrics, epistle_chars=20_000, gospel_chars=30_000, paragraphs=4)
    result = choose_layout(epistle, alleluia, gospel, box, metrics, S_MAX)
    assert 0 < result.font_size_pt < 5
    for constraint in layout_constraints(result.layout, epistle, alleluia, gospel, box, metrics):
        assert blocks_height(constraint.blocks, result.font_size_pt, box, metrics) <= constraint.height


def test_result_fits_its_layout(metrics, box):
    for epistle_chars, gospel_chars in [(600, 700), (1400, 700), (900, 1800), (2300, 3800)]:
        epistle, alleluia, gospel = sections(metrics, epistle_chars=epistle_chars, gospel_chars=gospel_chars)
        result = choose_layout(epistle, alleluia, gospel, box, metrics, S_MAX)
        assert result.alleluia_page_break == (result.layout == "split_before_alleluia")
        assert result.gospel_page_break == (result.layout == "split_before_gospel")
        for constraint in layout_constraints(result.layout, epistle, alleluia, gospel, box, metrics):
            assert blocks_height(constraint.blocks, result.font_size_pt, box, metrics) <= constraint.height


def test_layout_is_best_and_first_in_preference_order(metrics, box):
    seen = set()
    for epistle_chars in range(300, 3001, 150):
        for gospel_chars in range(300, 4001, 150):
            result = size_for(metrics, box, epistle_chars=epistle_chars, gospel_chars=gospel_chars)
            best = max(result.candidates.values())
            assert result.font_size_pt == best
            preferred = [L for L in LAYOUTS if result.candidates[L] == best][0]
            assert result.layout == preferred
            seen.add(result.layout)
    assert seen == set(LAYOUTS)


def test_short_epistle_long_gospel_puts_alleluia_with_epistle(metrics, box):
    result = size_for(metrics, box, epistle_chars=700, gospel_chars=1500)
    assert result.candidates["split_before_gospel"] >= result.candidates["split_before_alleluia"]
