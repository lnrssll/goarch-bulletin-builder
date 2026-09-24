import asyncio
import os
from datetime import date
from pathlib import Path

import pytest
from selectolax.parser import HTMLParser

import digital_chant_stand
import goarch_xml_feed
import text_sizing
from get_scripture_reading import get_alleluia_mode, get_scripture_reading_sections
from utils import SourceArchive
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
    day = date.fromisoformat(run_date)
    asyncio.run(digital_chant_stand.run(day, tmp_path, offline(run_date)))
    asyncio.run(goarch_xml_feed.run(day, tmp_path, offline(run_date)))
    text_sizing.run(tmp_path)

    snapshot_dir = SNAPSHOTS / run_date
    if os.environ.get("UPDATE_SNAPSHOTS"):
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        for built in tmp_path.glob("*.yaml"):
            (snapshot_dir / built.name).write_text(built.read_text())

    for built in sorted(tmp_path.glob("*.yaml")):
        snapshot = snapshot_dir / built.name
        assert snapshot.exists(), f"no snapshot for {run_date}; run with UPDATE_SNAPSHOTS=1"
        assert read_yaml(built) == read_yaml(snapshot), built.name


def test_feed_fields():
    feed, epistle, gospel = scrape_feed("2026-09-27")

    assert feed.lectionary_title == "1st Sunday of Luke"
    assert feed.formatted_date == "September 27, 2026"
    assert feed.icon_title == ""
    assert epistle.book == "St. Paul's Second Letter to the Corinthians"
    assert epistle.chapverse == "6:16-18; 7:1"
    assert epistle.verse == "God is known in Judah; his name is great in Israel."
    assert gospel.book == "The Holy Gospel According to St. Luke"
    assert gospel.chapverse == "5:1-11"
    assert all(paragraph.strip() for paragraph in epistle.text + gospel.text)


@pytest.mark.parametrize("run_date", ARCHIVED_DATES)
def test_readings_are_complete(run_date):
    _, epistle, gospel = scrape_feed(run_date)
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
    sections = digital_chant_stand.group_by_sections(digital_chant_stand.iter_row_items(tree))
    assert get_alleluia_mode(get_scripture_reading_sections(sections).alleluia_section) == mode

