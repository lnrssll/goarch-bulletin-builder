from datetime import date
from pathlib import Path

import pytest

import manual
import parish
from classes import ManualData, ManualHymnData, UpcomingServiceData

ROOT = Path(__file__).resolve().parent.parent
SUNDAY = date(2026, 9, 27)
SETTINGS = parish.original()
CATALOG = manual.HymnCatalog(
    hymns=[
        manual.HymnSuggestion("Resurrectional Apolytikion", pages_by_mode={1: "99", 8: "127"}),
        manual.HymnSuggestion("Kontakion for the Mother of God", 2, "225", also=["Ordinary Kontakion"]),
        manual.HymnSuggestion("Apolytikion of the Sunday of Orthodoxy", 2, "129"),
    ],
    abbreviations={"Apolytikion": "Apol.", "Kontakion": "Kont.", "Sunday": "Sun."},
)


def services(*pairs: tuple[str, str]) -> list[UpcomingServiceData]:
    return [UpcomingServiceData(when, priest) for when, priest in pairs]


def hymns(*rows: tuple[str, int | None, str]) -> list[ManualHymnData]:
    return [ManualHymnData(*row) for row in rows]


def test_template_carries_the_priests_over_from_last_week():
    last_week = ManualData(
        upcoming_services=services(
            ("Today", "Fr. Timothy"),
            ("09/26/2026", "Fr. Joshua"),
            ("10/10/2026", "Fr. Jacob"),
        )
    )
    assert manual.template(SUNDAY, last_week, SETTINGS).upcoming_services == services(
        ("Today", "Fr. Joshua"),
        ("10/03/2026", manual.UNKNOWN_PRIEST),
        ("10/10/2026", "Fr. Jacob"),
    )


def test_template_without_history():
    data = manual.template(SUNDAY, None, SETTINGS)
    assert data.upcoming_services == services(
        ("Today", manual.UNKNOWN_PRIEST),
        ("10/03/2026", manual.UNKNOWN_PRIEST),
    )
    assert [hymn.title for hymn in data.dismissal_hymns] == [manual.EXAMPLE_HYMN_TITLE]
    assert len(manual.unfinished(data)) == 2


def test_template_follows_a_sunday_liturgy():
    settings = parish.Settings(liturgy_day=parish.SUNDAY, today="This Sunday")
    last_week = ManualData(upcoming_services=services(("09/27/2026", "Fr. Joshua"), ("09/26/2026", "Fr. Jacob")))
    assert manual.template(SUNDAY, last_week, settings).upcoming_services == services(
        ("This Sunday", "Fr. Joshua"),
        ("10/04/2026", manual.UNKNOWN_PRIEST),
    )


def test_write_template_follows_the_settings(site, tmp_path):
    parish.save({"liturgy_day": parish.SUNDAY})
    manual.write_template(SUNDAY, tmp_path / "2026-09-27")
    assert manual.read(tmp_path / "2026-09-27").upcoming_services[1].date == "10/04/2026"


def test_hymnal_index_refuses_malformed_lines():
    with pytest.raises(ValueError, match="Line 2"):
        manual.hymnal_index("Ordinary Kontakion | 225 | Kontakia\nOnly a title\n")


def test_write_template_looks_back_past_skipped_weeks(site, tmp_path):
    manual.write(ManualData(upcoming_services=services(("09/26/2026", "Fr. Joshua"))), tmp_path / "2026-09-13")
    manual.write_template(SUNDAY, tmp_path / "2026-09-27")
    assert manual.read(tmp_path / "2026-09-27").upcoming_services[0] == UpcomingServiceData("Today", "Fr. Joshua")


def test_write_template_never_overwrites(site, tmp_path):
    mine = ManualData([ManualHymnData("Ordinary Kontakion", 2, "p. 225")], services(("Today", "Fr. Joshua")))
    manual.write(mine, tmp_path)
    manual.write_template(SUNDAY, tmp_path)
    assert manual.read(tmp_path) == mine


def test_read_tolerates_hand_edits(tmp_path):
    (tmp_path / "manual.yaml").write_text(
        "dismissal_hymns:\n"
        "- {title: Ordinary Kontakion, mode: '2', page: 225}\n"
        "- {title: Odd one, mode: pl. 4}\n"
        "upcoming_services:\n"
    )
    assert manual.read(tmp_path) == ManualData(
        [ManualHymnData("Ordinary Kontakion", 2, "225"), ManualHymnData("Odd one", None, "")],
        [],
    )
    assert manual.read(tmp_path / "nowhere") is None


@pytest.mark.parametrize("typed", ["127", "p.127", "p 127", "P. 127", "pg 127", "page 127", " 127 "])
def test_page_label_adds_one_prefix(typed):
    assert manual.page_label(typed) == "p. 127"
    assert manual.page_number(manual.page_label(typed)) == "127"


@pytest.mark.parametrize(
    ("typed", "label"),
    [
        ("handout", "Handout"),
        ("HANDOUT", "Handout"),
        ("choir", "Choir"),
        ("Sung by the choir", "Sung by the choir"),
        ("209, 211", "p. 209, 211"),
        ("", ""),
    ],
)
def test_page_label_keeps_words(typed, label):
    assert manual.page_label(typed) == label


@pytest.mark.parametrize(
    "typed", ["Joshua", "Fr. Joshua", "fr Joshua", "Fr.Joshua", "FR. Joshua", "Father Joshua", " Joshua "]
)
def test_priest_label_adds_one_prefix(typed):
    assert manual.priest_label(typed) == "Fr. Joshua"
    assert manual.priest_name(manual.priest_label(typed)) == "Joshua"


@pytest.mark.parametrize(
    ("typed", "label"),
    [
        ("Francis", "Fr. Francis"),
        ("Frederick", "Fr. Frederick"),
        ("Reader Service", "Reader Service"),
        ("reader service", "Reader Service"),
        ("TBD", "TBD"),
        ("Fr.", ""),
        ("", ""),
    ],
)
def test_priest_label_exceptions(typed, label):
    assert manual.priest_label(typed) == label


def test_expand_abbreviations():
    assert (
        manual.expand_abbreviations("Apol. of Sun. of Orthodoxy", CATALOG.abbreviations)
        == "Apolytikion of Sunday of Orthodoxy"
    )
    assert manual.expand_abbreviations("Kontakion of Sunday", CATALOG.abbreviations) == "Kontakion of Sunday"


def test_even_hymnal_pages_are_unfinished():
    data = ManualData(
        hymns(("Theophany Apolytikion", 1, "p. 210"), ("Example", 9, "p. 0"), ("Other", 1, "Handout")),
        services(("Today", "Fr. Joshua")),
    )
    assert manual.unfinished(data) == [
        f"The “{manual.EXAMPLE_HYMN_TITLE}” hymn is still listed.",
        "“Theophany Apolytikion” is on p. 210, an even page. The English is on the odd pages.",
    ]


def test_unfinished_is_empty_once_filled_in():
    data = ManualData([ManualHymnData("Ordinary Kontakion", 2, "p. 225")], services(("Today", "Fr. Joshua")))
    assert manual.unfinished(data) == []


def test_catalog_hymns_come_first_most_used_first(tmp_path):
    manual.write(ManualData(hymns(("Kontakion for the Mother of God", 2, "p. 225"))), tmp_path / "2026-09-13")
    manual.write(
        ManualData(hymns(("Ordinary kontakion", 2, "p. 225"), ("apol. of the Sun. of Orthodoxy!", 2, "p. 129"))),
        tmp_path / "2026-09-20",
    )
    manual.write(ManualData(hymns(("Example", 9, "p. 0"))), tmp_path / "2026-09-27")
    assert manual.suggestions(tmp_path, CATALOG).hymns == [
        CATALOG.hymns[1],
        CATALOG.hymns[2],
        CATALOG.hymns[0],
    ]


def test_other_hymns_fill_in_only_what_never_changed(tmp_path):
    manual.write(
        ManualData(hymns(("Apolytikion of the Feast", 8, "handout"), ("Apol. for the Saint", 4, "Choir"))),
        tmp_path / "2026-09-20",
    )
    manual.write(ManualData(hymns(("Apolytikion of the Feast", 1, "Handout"))), tmp_path / "2026-09-27")
    assert manual.suggestions(tmp_path, CATALOG).hymns[len(CATALOG.hymns):] == [
        manual.HymnSuggestion("Apolytikion of the Feast", None, "Handout"),
        manual.HymnSuggestion("Apolytikion for the Saint", 4, "Choir"),
    ]


def test_priests_are_suggested_most_used_first(tmp_path):
    manual.write(
        ManualData(upcoming_services=services(("Today", "Fr. Jacob"), ("09/26/2026", "Reader Service"))),
        tmp_path / "2026-09-20",
    )
    manual.write(
        ManualData(
            upcoming_services=services(
                ("Today", "Fr. Joshua"), ("10/03/2026", "Fr. X"), ("10/10/2026", "TBD"), ("10/17/2026", "Fr Jacob")
            )
        ),
        tmp_path / "2026-09-27",
    )
    assert manual.suggestions(tmp_path, CATALOG).priests == ["Jacob", "Joshua", manual.READER_SERVICE]


def test_hymn_suggestion_detail():
    assert CATALOG.hymns[0].detail == "page depends on mode"
    assert CATALOG.hymns[1].detail == "Mode 2, p. 225"
    assert manual.HymnSuggestion("Apolytikion of the Feast", None, "Handout").detail == "Handout"


def test_the_hymn_catalog_agrees_with_the_hymnal_index():
    catalog = manual.hymn_catalog(ROOT / manual.HYMN_CATALOG_PATH)
    index_pages = {
        int(page) for entries in manual.hymnal_index((ROOT / parish.HYMNAL_INDEX_PATH).read_text()).values() for _, page in entries
    }
    assert all(page % 2 == 1 for page in index_pages)

    names = [manual.hymn_key(name, catalog.abbreviations) for hymn in catalog.hymns for name in (hymn.title, *hymn.also)]
    assert len(names) == len(set(names))
    for hymn in catalog.hymns:
        assert not (hymn.page and hymn.pages_by_mode), hymn.title
        for page in (hymn.page, *hymn.pages_by_mode.values()):
            assert page in ("", *manual.NOT_A_PAGE) or int(page) in index_pages, hymn.title

    resurrectional = catalog.hymns[0]
    assert resurrectional.pages_by_mode == {mode: str(99 + 4 * (mode - 1)) for mode in manual.MODES}
    assert manual.HymnSuggestion("Kontakion for the Mother of God", 2, "225", also=["Ordinary Kontakion"]) in catalog.hymns


def test_a_missing_catalog_is_empty(tmp_path):
    assert manual.hymn_catalog(tmp_path / "hymns.yaml") == manual.HymnCatalog()


def test_hymnal_index():
    index = manual.hymnal_index((ROOT / parish.HYMNAL_INDEX_PATH).read_text())
    assert ("Ordinary Kontakion", "225") in index["Kontakia"]
    assert index["Sunday Resurrectional Apolitikia"][7] == ("Tone 8", "127")
