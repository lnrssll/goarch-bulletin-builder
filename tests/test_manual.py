from datetime import date
from pathlib import Path

import manual
from classes import ManualData, ManualHymnData, UpcomingServiceData

ROOT = Path(__file__).resolve().parent.parent
SUNDAY = date(2026, 9, 27)


def services(*pairs: tuple[str, str]) -> list[UpcomingServiceData]:
    return [UpcomingServiceData(when, priest) for when, priest in pairs]


def test_template_carries_the_priests_over_from_last_week():
    last_week = ManualData(
        upcoming_services=services(
            ("Today", "Fr. Timothy"),
            ("09/26/2026", "Fr. Joshua"),
            ("10/10/2026", "Fr. Jacob"),
        )
    )
    assert manual.template(SUNDAY, last_week).upcoming_services == services(
        ("Today", "Fr. Joshua"),
        ("10/03/2026", manual.UNKNOWN_PRIEST),
        ("10/10/2026", "Fr. Jacob"),
    )


def test_template_without_history():
    data = manual.template(SUNDAY, None)
    assert data.upcoming_services == services(
        ("Today", manual.UNKNOWN_PRIEST),
        ("10/03/2026", manual.UNKNOWN_PRIEST),
    )
    assert [hymn.title for hymn in data.dismissal_hymns] == [manual.EXAMPLE_HYMN_TITLE]
    assert len(manual.unfinished(data)) == 2


def test_write_template_looks_back_past_skipped_weeks(tmp_path):
    manual.write(ManualData(upcoming_services=services(("09/26/2026", "Fr. Joshua"))), tmp_path / "2026-09-13")
    manual.write_template(SUNDAY, tmp_path / "2026-09-27")
    assert manual.read(tmp_path / "2026-09-27").upcoming_services[0] == UpcomingServiceData("Today", "Fr. Joshua")


def test_write_template_never_overwrites(tmp_path):
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


def test_page_label():
    assert manual.page_label("127") == "p. 127"
    assert manual.page_label("p. 127") == "p. 127"
    assert manual.page_label("Choir") == "Choir"
    assert manual.page_label("") == ""


def test_unfinished_is_empty_once_filled_in():
    data = ManualData([ManualHymnData("Ordinary Kontakion", 2, "p. 225")], services(("Today", "Fr. Joshua")))
    assert manual.unfinished(data) == []


def test_suggestions_come_from_the_latest_use(tmp_path):
    manual.write(
        ManualData([ManualHymnData("Ordinary Kontakion", 2, "p. 225")], services(("Today", "Fr. Jacob"))),
        tmp_path / "2026-09-20",
    )
    manual.write(
        ManualData(
            [ManualHymnData("Ordinary Kontakion", 2, "choir"), ManualHymnData("Example", 9, "p. 0")],
            services(("Today", "Fr. Joshua"), ("10/03/2026", "Fr. X")),
        ),
        tmp_path / "2026-09-27",
    )
    found = manual.suggestions(tmp_path)
    assert found.hymns == [ManualHymnData("Ordinary Kontakion", 2, "choir")]
    assert found.priests == ["Fr. Joshua", "Fr. Jacob"]


def test_hymnal_index():
    index = manual.hymnal_index(ROOT / manual.HYMNAL_INDEX_PATH)
    assert ("Ordinary Kontakion", "225") in index["Kontakia"]
    assert index["Sunday Resurrectional Apolitikia"][7] == ("Tone 8", "127")
