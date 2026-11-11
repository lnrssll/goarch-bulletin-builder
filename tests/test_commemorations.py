import asyncio
from dataclasses import asdict
from datetime import date
from pathlib import Path

import httpx
import pytest

import commemorations
import digital_chant_stand
import goarch_xml_feed
from utils import SourceArchive
from yaml_io import write_yaml

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "archive"
ARCHIVED_DATES = sorted(p.name for p in ARCHIVE.iterdir() if p.is_dir())

# Chant Stand title -> the goarch.org hymn it is, checked by hand against both texts
SAME_HYMNS = {
    "2026-09-13": {
        "Resurrectional Apolytikion": [],
        "For the Forefeast": ["Apolytikion of Forefeast of the Exaltation"],
        "For the Consecration": ["Apolytikion of Temple of the Resurrection"],
        "Kontakion": ["Kontakion of Temple of the Resurrection"],
    },
    "2026-09-20": {
        "Resurrectional Apolytikion": [],
        "Apolytikion For the Cross": ["Apolytikion of Afterfeast of the Holy Cross"],
        "For the Saints": ["Apolytikion of Martyr Eustathius and His Companions"],
        "Kontakion": ["Kontakion of Sun. after Holy Cross"],
    },
    "2026-09-27": {
        "Resurrectional Apolytikion": [],
        "For the Martyrs": ["Apolytikion of Martyr Callistratus & his Companions"],
        "Kontakion Mode 2": [],
    },
    "2026-10-11": {
        "Resurrectional Apolytikion": [],
        "For the Fathers": ["Apolytikion of Sun. of the 7th Ecumenical Council"],
        "Kontakion Mode 2": [],
    },
    "2026-10-18": {
        "Resurrectional Apolytikion": [],
        "For the Evangelist": ["Apolytikion of Luke the Evangelist"],
        "Kontakion Mode 2": [],
    },
    "2026-10-25": {
        "Resurrectional Apolytikion": [],
        "For the Saints": ["Apolytikion of Martyrs Marcian and Martyrius"],
        "Kontakion Mode 2": [],
    },
    "2026-11-01": {
        "Resurrectional Apolytikion": [],
        "For the Saints": ["Apolytikion of Unmercenaries Cosmas and Damian"],
        "Kontakion Mode 2": [],
    },
    "2026-11-08": {
        "Resurrectional Apolytikion": [],
        "For the Angels": ["Apolytikion of Synaxis of the Archangels"],
        "Kontakion": [],
    },
    "2026-11-15": {
        "Resurrectional Apolytikion": [],
        "For the Saints": ["Apolytikion of Martyrs Gouria, Shamuna, and Habib"],
        "Kontakion": [],
    },
}


def offline(run_date: str) -> SourceArchive:
    return SourceArchive(ARCHIVE / run_date)


def archived_commemorations(run_date: str) -> list[dict]:
    found = asyncio.run(goarch_xml_feed.scrape_commemorations(date.fromisoformat(run_date), offline(run_date)))
    return [asdict(c) for c in found]


def chant_stand_hymns(run_date: str) -> list[dict]:
    liturgy = asyncio.run(digital_chant_stand.scrape(date.fromisoformat(run_date), offline(run_date)))
    return [asdict(hymn) for hymn in liturgy.dismissal_hymns]


def test_commemorations_in_the_order_goarch_lists_them():
    found = archived_commemorations("2026-11-15")

    assert [c["title"] for c in found] == [
        "8th Sunday of Luke",
        "Nativity Fast Begins",
        "Guria, Shamuna, and Habib, Martyrs and Confessors of Edessa",
        "Thomas II the New, Archbishop of Constantinople",
    ]
    assert found[0]["public_url"].startswith("http://www.goarch.org/chapel/saints?contentid=978")
    assert found[0]["hymns"] == []
    apolytikion, kontakion = found[2]["hymns"]
    assert apolytikion["short_title"] == "Apolytikion of Martyrs Gouria, Shamuna, and Habib"
    assert apolytikion["tone"] == "Plagal of the First Tone"
    assert apolytikion["body"].startswith("Since Thou hast given us the miracles of Thy holy Martyrs")
    assert kontakion["type"] == "kontakion"


def test_every_archived_sunday_is_in_the_table():
    assert sorted(SAME_HYMNS) == ARCHIVED_DATES


@pytest.mark.parametrize("run_date", ARCHIVED_DATES)
def test_chant_stand_hymns_are_matched_to_goarch(run_date):
    chant_stand, _ = commemorations.compare(chant_stand_hymns(run_date), archived_commemorations(run_date))

    matched = {hymn["title"]: [found["hymn"]["short_title"] for found in hymn["on_goarch"]] for hymn in chant_stand}
    assert matched == SAME_HYMNS[run_date]


def test_a_match_is_marked_on_both_sides():
    chant_stand, found = commemorations.compare(chant_stand_hymns("2026-11-15"), archived_commemorations("2026-11-15"))

    martyrs = found[2]
    assert [chanted["title"] for chanted in martyrs["hymns"][0]["in_chant_stand"]] == ["For the Saints"]
    assert martyrs["hymns"][1]["in_chant_stand"] == []
    for_the_saints = chant_stand[1]
    assert for_the_saints["on_goarch"][0]["commemoration"] == martyrs["title"]
    assert for_the_saints["mode_number"] == martyrs["hymns"][0]["mode_number"] == 5


@pytest.mark.parametrize(
    "text, number",
    [
        ("4", 4),
        ("Plagal 1", 5),
        ("Plagal 4", 8),
        ("Fourth Tone", 4),
        ("Plagal of the First Tone", 5),
        ("Plagal of the Fourth Tone", 8),
        ("Grave Tone", 7),
        ("", None),
        (None, None),
    ],
)
def test_mode_number(text, number):
    assert commemorations.mode_number(text) == number


def test_old_sundays_are_read_from_the_archive(tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    found = commemorations.load(date(2026, 11, 15), tmp_path)
    assert found == archived_commemorations("2026-11-15")

    monkeypatch.chdir(tmp_path)
    assert commemorations.load(date(2026, 11, 15), tmp_path) == []


def test_a_bot_check_instead_of_a_saint_is_not_archived(tmp_path):
    chapel = (ARCHIVE / "2026-11-15" / "chapel.xml").read_bytes()

    def answer(request: httpx.Request) -> httpx.Response:
        if "saints.asp" in str(request.url):
            return httpx.Response(200, text="<html><body>Just a moment...</body></html>")
        return httpx.Response(200, content=chapel)

    async def scrape() -> list:
        async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
            archive = SourceArchive(tmp_path, client)
            found = await goarch_xml_feed.scrape_commemorations(date(2026, 11, 15), archive)
            archive.save()
            return found

    found = asyncio.run(scrape())
    assert [c.hymns for c in found] == [None] * 4
    assert found[2].title.startswith("Guria")
    assert not (tmp_path / "saints").exists()


ENTRY_KONTAKION = "The Savior’s most pure and immaculate temple, the very precious bridal chamber and Virgin"
PROTECTION = "O Protection of Christians that never falls, intercession with the Creator unfailing"
RESURRECTIONAL = "You destroyed death by Your Cross, You opened Paradise to the Robber."


def past_sunday(sundays: Path, day: str, chant_stand: list[dict], saved: list[dict]) -> None:
    out_dir = sundays / day
    out_dir.mkdir(parents=True)
    write_yaml({"alleluia": [], "dismissal_hymns": chant_stand}, out_dir / "digital_chant_stand.yaml")
    write_yaml({"dismissal_hymns": saved, "upcoming_services": []}, out_dir / "manual.yaml")


def test_titles_saved_before_for_the_same_text(tmp_path):
    past_sunday(
        tmp_path,
        "2026-11-08",
        [
            {"title": "For the Angels", "mode": "4", "text": "O Commanders of the Heavenly Host"},
            {"title": "Kontakion", "mode": "4", "text": ENTRY_KONTAKION},
        ],
        [
            {"title": "Resurrectional Apolytikion", "mode": 6, "page": "p. 119"},
            {"title": "Apolytikion of Synaxis of the Archangels", "mode": 4, "page": "Choir"},
            {"title": "Entry of the Theotokos Kontakion", "mode": 4, "page": "p. 237"},
        ],
    )
    past_sunday(
        tmp_path,
        "2025-11-02",
        [
            {"title": "Resurrectional Apolytikion", "mode": "Plagal 2", "text": "When the angelic powers appeared"},
            {"title": "Kontakion Mode 2", "mode": None, "text": PROTECTION},
        ],
        [
            {"title": "Resurrectional Apolytikion", "mode": 6},
            {"title": "Kont. for the Mother of God", "mode": 2},
            {"title": "Example", "mode": 2},
        ],
    )
    past_sunday(tmp_path, "2026-11-15", [{"title": "Kontakion", "mode": "4", "text": ENTRY_KONTAKION}], [
        {"title": "Wrong: this is the Sunday being made", "mode": 4},
    ])
    hymns = [
        {"title": "Resurrectional Apolytikion", "mode": "Grave", "text": RESURRECTIONAL},
        {"title": "Kontakion", "mode": "4", "text": ENTRY_KONTAKION},
        {"title": "Kontakion Mode 2", "mode": None, "text": PROTECTION},
    ]

    commemorations.add_past_titles(hymns, date(2026, 11, 15), tmp_path)

    assert hymns[0]["used_before"] == []
    assert hymns[1]["used_before"] == [{"title": "Entry of the Theotokos Kontakion", "when": "Nov 8"}]
    # the hymn list's spelling, which the page then fills in from
    assert hymns[2]["used_before"] == [{"title": "Kontakion for the Mother of God", "when": "Nov 2, 2025"}]


def test_when_a_title_was_used():
    days = [date(2026, 11, 1), date(2026, 10, 25), date(2026, 10, 18), date(2026, 9, 27), date(2025, 12, 7)]
    assert commemorations.when(days, date(2026, 11, 15)) == "Nov 1, Oct 25, Oct 18 and 2 more"
    assert commemorations.when(days[-1:], date(2026, 11, 15)) == "Dec 7, 2025"


@pytest.mark.parametrize(
    "title, kind",
    [
        ("Entry of the Theotokos Kontakion", "kontakion"),
        ("Kont. of Forefeast of the Meeting of the Lord", "kontakion"),
        ("Ressurectional Apolytikion", "resurrectional"),
        ("Apol. of Afterfeast of the Presentation", "apolytikion"),
        ("For the Saints", "apolytikion"),
    ],
)
def test_kind(title, kind):
    assert commemorations.kind(title) == kind
