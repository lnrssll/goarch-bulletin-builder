import asyncio
import os
import re
import shutil
from datetime import date
from pathlib import Path

import pytest
from selectolax.parser import HTMLParser

import digital_chant_stand
import goarch_xml_feed
import sunday
from utils import ScrapeError, SourceArchive
from yaml_io import read_yaml

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "archive"
SNAPSHOTS = ROOT / "tests" / "snapshots"
ARCHIVED_DATES = sorted(p.name for p in ARCHIVE.iterdir() if p.is_dir())


def offline(run_date: str) -> SourceArchive:
    return SourceArchive(ARCHIVE / run_date)


def scrape_feed(run_date: str):
    return asyncio.run(goarch_xml_feed.scrape(date.fromisoformat(run_date), offline(run_date)))


def scrape_dcs(run_date: str):
    return asyncio.run(digital_chant_stand.scrape(date.fromisoformat(run_date), offline(run_date)))


@pytest.mark.parametrize("run_date", ARCHIVED_DATES)
def test_build_matches_snapshot(run_date, tmp_path, monkeypatch):
    monkeypatch.chdir(ROOT)
    out_dir = tmp_path / run_date
    fetched = asyncio.run(
        sunday.fetch_readings(date.fromisoformat(run_date), out_dir, ARCHIVE / run_date)
    )
    assert fetched.failures == {}
    assert (out_dir / read_yaml(out_dir / "feed.yaml")["icon_filename"]).exists()

    snapshot_dir = SNAPSHOTS / run_date
    scraped = [out_dir / name for source in sunday.SOURCES for name in source.files]
    scraped.append(out_dir / goarch_xml_feed.COMMEMORATIONS_FILE)
    if os.environ.get("UPDATE_SNAPSHOTS"):
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        for built in scraped:
            (snapshot_dir / built.name).write_text(built.read_text())

    for built in scraped:
        snapshot = snapshot_dir / built.name
        assert snapshot.exists(), f"no snapshot for {run_date}; run with UPDATE_SNAPSHOTS=1"
        assert read_yaml(built) == read_yaml(snapshot), built.name


def test_feed_fields():
    data = scrape_feed("2026-09-27")
    feed, epistle, gospel = data.feed, data.epistle, data.gospel

    assert feed.lectionary_title == "1st Sunday of Luke"
    assert feed.formatted_date == "September 27, 2026"
    assert feed.icon_title == ""
    assert feed.icon_filename == "johntheo.jpg"
    assert data.icon.startswith(b"\xff\xd8")
    assert epistle.book == "St. Paul's Second Letter to the Corinthians"
    assert epistle.chapverse == "6:16-18; 7:1"
    assert epistle.verse == "God is known in Judah; his name is great in Israel."
    assert gospel.book == "The Holy Gospel According to St. Luke"
    assert gospel.chapverse == "5:1-11"
    assert all(paragraph.strip() for paragraph in epistle.text + gospel.text)


@pytest.mark.parametrize("run_date", ARCHIVED_DATES)
def test_readings_are_complete(run_date):
    data = scrape_feed(run_date)
    epistle, gospel = data.epistle, data.gospel
    liturgy = scrape_dcs(run_date)

    assert epistle.prokeimenon and epistle.verse
    assert not epistle.verse.startswith("Verse")
    assert epistle.text and gospel.text
    assert 2 <= len(liturgy.alleluia) <= 3


@pytest.mark.parametrize(
    "run_date, mode",
    [("2026-09-13", 1), ("2026-09-20", 7), ("2026-09-27", 8)],
)
def test_alleluia_mode(run_date, mode):
    tree = HTMLParser((ARCHIVE / run_date / "dcs.html").read_text())
    dcs = digital_chant_stand
    sections = dcs.get_scripture_reading_sections(dcs.group_by_sections(dcs.iter_row_items(tree)))
    assert dcs.get_alleluia_mode(sections.alleluia_section) == mode



@pytest.mark.parametrize("run_date", ARCHIVED_DATES)
def test_dismissal_hymns_start_with_the_resurrectional_apolytikion(run_date):
    # its title also comes before the Entrance on most Sundays, which once hid this one
    first = scrape_dcs(run_date).dismissal_hymns[0]
    assert first.title == "Resurrectional Apolytikion"
    assert first.source == "Octoechos"
    assert first.mode


def test_formatted_date_is_not_zero_padded():
    assert scrape_feed("2026-11-08").feed.formatted_date == "November 8, 2026"


def test_grave_mode():
    assert digital_chant_stand.parse_mode("Grave Mode.") == "Grave"
    assert digital_chant_stand.parse_mode("Mode pl. 1.") == "Plagal 1"
    assert digital_chant_stand.parse_mode("Mode 1. Simple melody.") == "1"
def test_bot_check_page_is_a_scrape_error(tmp_path):
    (tmp_path / "dcs.html").write_text("<html><body>Just a moment...</body></html>")
    with pytest.raises(ScrapeError, match="Alleluia"):
        asyncio.run(digital_chant_stand.scrape(date(2026, 9, 27), SourceArchive(tmp_path)))


def test_malformed_feed_is_a_scrape_error(tmp_path):
    (tmp_path / "chapel.xml").write_text("<onlinechapel><formatteddate>x</formatteddate></onlinechapel>")
    with pytest.raises(ScrapeError, match="chapel.xml"):
        asyncio.run(goarch_xml_feed.scrape(date(2026, 9, 27), SourceArchive(tmp_path)))


def test_a_day_without_an_icon_keeps_its_readings(tmp_path):
    shutil.copytree(ARCHIVE / "2026-09-27", tmp_path, dirs_exist_ok=True)
    chapel = tmp_path / "chapel.xml"
    chapel.write_text(re.sub(r"<icon[^>]*>.*?</icon>", "", chapel.read_text(), flags=re.S))

    data = asyncio.run(goarch_xml_feed.scrape(date(2026, 9, 27), SourceArchive(tmp_path)))

    assert data.feed.lectionary_title == "1st Sunday of Luke"
    assert data.feed.icon_src is None and data.icon is None
    assert data.epistle.text and data.gospel.text


@pytest.mark.parametrize("end", ["Trisagios Hymn", "Instead of Holy God", "The Epistle"])
def test_dismissal_hymns_end_before_the_trisagion_or_what_replaces_it(end):
    # on the Sunday of the Cross, Pascha and Pentecost (2026-03-15, 04-12, 05-31) the Chant Stand has
    # "Instead of Holy God" in place of the Trisagion, and the Epistle, Gospel and Dismissal were listed as hymns
    titles = ["Hymns after the Entrance.", "Apolytikion of the Feast.", "Kontakion of the Feast.", end, "The Gospel", "DISMISSAL"]
    sections = [(title, [title]) for title in titles]
    assert digital_chant_stand.dismissal_hymn_sections(sections) == [["Apolytikion of the Feast."], ["Kontakion of the Feast."]]
