import asyncio
import shutil
from datetime import date
from pathlib import Path

import httpx

import manual
import sunday
from yaml_io import read_yaml

ROOT = Path(__file__).resolve().parent.parent
DAY = date(2026, 9, 27)
BOT_CHECK = "<html><body>Just a moment...</body></html>"


def fetch(out_dir: Path, archive_root: Path, client: httpx.AsyncClient | None = None) -> sunday.FetchResult:
    return asyncio.run(sunday.fetch_readings(DAY, out_dir, archive_root, client))


def bot_check_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=BOT_CHECK)))


def test_dates():
    assert sunday.next_sunday(date(2026, 9, 26)) == DAY
    assert sunday.next_sunday(DAY) == date(2026, 10, 4)
    assert sunday.sunday_on_or_after(date(2026, 9, 21)) == DAY
    assert sunday.sunday_on_or_after(DAY) == DAY
    assert sunday.long_date(date(2026, 10, 4)) == "October 4, 2026"


def test_a_failed_source_leaves_the_other_one_written(site):
    archive_root = site / "archive" / DAY.isoformat()
    shutil.copytree(ROOT / "archive" / DAY.isoformat(), archive_root)
    (archive_root / "dcs.html").write_text(BOT_CHECK)
    out_dir = site / "build" / DAY.isoformat()

    fetched = fetch(out_dir, archive_root)

    assert [source.name for source in fetched.failures] == ["Digital Chant Stand"]
    assert fetched.sizing is None
    assert (out_dir / "gospel.yaml").exists()
    assert (out_dir / manual.FILENAME).exists()
    assert not (out_dir / "digital_chant_stand.yaml").exists()
    assert [source.name for source in sunday.missing_sources(out_dir)] == ["Digital Chant Stand"]


def test_bot_check_pages_are_never_archived_or_written(tmp_path):
    out_dir = tmp_path / "build" / DAY.isoformat()
    archive_root = tmp_path / "archive" / DAY.isoformat()

    fetched = fetch(out_dir, archive_root, bot_check_client())

    assert len(fetched.failures) == len(sunday.SOURCES)
    assert not out_dir.exists()
    assert not archive_root.exists()


def test_readings_start_from_the_date_when_nothing_was_fetched(tmp_path):
    readings = sunday.load_readings(DAY, tmp_path)
    assert readings == sunday.Readings(formatted_date="September 27, 2026")


def test_saved_readings_load_back_and_keep_the_rest(site):
    archive_root = ROOT / "archive" / DAY.isoformat()
    out_dir = site / "build" / DAY.isoformat()
    fetch(out_dir, archive_root)

    readings = sunday.load_readings(DAY, out_dir)
    assert readings.lectionary_title == "1st Sunday of Luke"
    readings.lectionary_title = "First Sunday of Luke"
    readings.alleluia = readings.alleluia[:1]
    sizing = sunday.save_readings(DAY, out_dir, readings)

    assert sunday.load_readings(DAY, out_dir) == readings
    feed = read_yaml(out_dir / "feed.yaml")
    assert feed["icon_filename"] == "johntheo.jpg"
    assert feed["font_size_pt"] == sizing.font_size_pt
    assert read_yaml(out_dir / "epistle.yaml")["mode"] == 8
    assert read_yaml(out_dir / "digital_chant_stand.yaml")["dismissal_hymns"]
