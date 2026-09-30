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
    out_dir = site / "state" / "sundays" / DAY.isoformat()

    fetched = fetch(out_dir, archive_root)

    assert [source.name for source in fetched.failures] == ["Digital Chant Stand"]
    assert fetched.sizing is None
    assert (out_dir / "gospel.yaml").exists()
    assert (out_dir / manual.FILENAME).exists()
    assert not (out_dir / "digital_chant_stand.yaml").exists()
    assert [source.name for source in sunday.missing_sources(out_dir)] == ["Digital Chant Stand"]


def test_bot_check_pages_are_never_archived_or_written(tmp_path):
    out_dir = tmp_path / "state" / "sundays" / DAY.isoformat()
    archive_root = tmp_path / "archive" / DAY.isoformat()

    fetched = fetch(out_dir, archive_root, bot_check_client())

    assert len(fetched.failures) == len(sunday.SOURCES)
    assert not out_dir.exists()
    assert not archive_root.exists()


def test_what_a_failed_download_sent_is_kept_for_a_developer(tmp_path):
    def answer(request: httpx.Request) -> httpx.Response:
        if "dcs.goarch.org" in str(request.url):
            return httpx.Response(503, text=BOT_CHECK)
        return httpx.Response(200, text="<onlinechapel>changed</onlinechapel>")

    archive_root = tmp_path / "archive" / DAY.isoformat()
    failed_root = tmp_path / "failed"
    client = httpx.AsyncClient(transport=httpx.MockTransport(answer))
    fetched = asyncio.run(
        sunday.fetch_readings(DAY, tmp_path / "out", archive_root, client, failed_root=failed_root)
    )

    assert len(fetched.failures) == len(sunday.SOURCES)
    assert not archive_root.exists()
    saved = {source.name: path for source, path in fetched.saved.items()}
    assert (saved["Digital Chant Stand"] / "dcs.html").read_text() == BOT_CHECK
    assert (saved["Online Chapel"] / "chapel.xml").read_text() == "<onlinechapel>changed</onlinechapel>"
    assert saved["Online Chapel"].parent.parent == failed_root
    assert saved["Online Chapel"].parent.name.endswith(f"_for_{DAY.isoformat()}")


def test_only_the_latest_failures_are_kept(tmp_path):
    for n in range(5):
        (tmp_path / f"2026-09-0{n + 1}_12-00-00_for_2026-09-27").mkdir()
    sunday.prune(tmp_path, 3)
    assert sorted(p.name[:10] for p in tmp_path.iterdir()) == ["2026-09-03", "2026-09-04", "2026-09-05"]


def test_readings_start_from_the_date_when_nothing_was_fetched(tmp_path):
    readings = sunday.load_readings(DAY, tmp_path)
    assert readings == sunday.Readings(formatted_date="September 27, 2026")


def test_saved_readings_load_back_and_keep_the_rest(site):
    archive_root = ROOT / "archive" / DAY.isoformat()
    out_dir = site / "state" / "sundays" / DAY.isoformat()
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
