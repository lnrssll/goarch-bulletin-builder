import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

import digital_chant_stand
import goarch_xml_feed
import manual
import text_sizing
from classes import DailyFeedPageData, EpistlePageData, GospelPageData, LiturgyVariablesPageData
from utils import ARCHIVE_DIR, ScrapeError, SourceArchive, http_client
from yaml_io import read_yaml, write_yaml

STATE_DIR = Path("state")
SUNDAYS_DIR = STATE_DIR / "sundays"
# what goarch.org sent when a download failed, for a developer (see AGENTS.md)
FAILED_DIR = STATE_DIR / "failed-downloads"
FAILED_KEPT = 20
SUNDAY = 6


@dataclass(frozen=True)
class Source:
    name: str
    provides: str
    files: tuple[str, ...]
    scrape: Callable[[date, SourceArchive], Awaitable[Any]]
    write: Callable[[Any, Path], None]


SOURCES = (
    Source(
        "Online Chapel",
        "the title, epistle and gospel",
        ("feed.yaml", "epistle.yaml", "gospel.yaml"),
        goarch_xml_feed.scrape,
        goarch_xml_feed.write,
    ),
    Source(
        "Digital Chant Stand",
        "the Alleluia verses",
        ("digital_chant_stand.yaml",),
        digital_chant_stand.scrape,
        digital_chant_stand.write,
    ),
)


@dataclass
class FetchResult:
    failures: dict[Source, Exception] = field(default_factory=dict)
    # where the pages of a failed source were saved
    saved: dict[Source, Path] = field(default_factory=dict)
    sizing: text_sizing.SizingResult | None = None


@dataclass
class Readings:
    lectionary_title: str = ""
    formatted_date: str = ""
    icon_title: str = ""
    epistle_book: str = ""
    epistle_chapverse: str = ""
    prokeimenon: str = ""
    verse: str = ""
    epistle_text: list[str] = field(default_factory=list)
    alleluia: list[str] = field(default_factory=list)
    gospel_book: str = ""
    gospel_chapverse: str = ""
    gospel_text: list[str] = field(default_factory=list)
    size_override_pt: float | None = None
    layout_override: str = ""


################################################################################
# dates and Sunday folders
################################################################################


def next_sunday(today: date) -> date:
    return today + timedelta(days=(SUNDAY - today.weekday()) or 7)


def sunday_on_or_after(day: date) -> date:
    return day + timedelta(days=(SUNDAY - day.weekday()) % 7)


def long_date(day: date) -> str:
    return f"{day:%B} {day.day}, {day.year}"


def sunday_dir(run_date: date) -> Path:
    return SUNDAYS_DIR / run_date.isoformat()


def saved_dates() -> list[date]:
    if not SUNDAYS_DIR.is_dir():
        return []
    dates = []
    for path in SUNDAYS_DIR.iterdir():
        try:
            day = date.fromisoformat(path.name)
        except ValueError:
            continue
        if path.is_dir() and path.name == day.isoformat():
            dates.append(day)
    return sorted(dates, reverse=True)


def missing_sources(out_dir: Path) -> list[Source]:
    return [s for s in SOURCES if not all((out_dir / name).exists() for name in s.files)]


def has_readings(out_dir: Path) -> bool:
    return not missing_sources(out_dir)


################################################################################
# fetch
################################################################################


async def fetch_readings(
    run_date: date,
    out_dir: Path,
    archive_root: Path,
    client: httpx.AsyncClient | None = None,
    refresh: bool = False,
    failed_root: Path | None = None,
) -> FetchResult:
    # one archive per source, so a source that fails archives nothing and the other still can
    archives = {source: SourceArchive(archive_root, client, refresh) for source in SOURCES}
    results = await asyncio.gather(
        *(source.scrape(run_date, archives[source]) for source in SOURCES),
        return_exceptions=True,
    )

    fetched = FetchResult()
    for source, result in zip(SOURCES, results, strict=True):
        if isinstance(result, (ScrapeError, httpx.HTTPError)):
            fetched.failures[source] = result
        elif isinstance(result, BaseException):
            raise result
    if failed_root is not None:
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        for source in fetched.failures:
            dest = failed_root / f"{stamp}_for_{run_date.isoformat()}" / slug(source.name)
            if archives[source].save_failed(dest):
                fetched.saved[source] = dest
        prune(failed_root, FAILED_KEPT)
    if len(fetched.failures) == len(SOURCES):
        return fetched

    out_dir.mkdir(parents=True, exist_ok=True)
    for source, result in zip(SOURCES, results, strict=True):
        if source not in fetched.failures:
            archives[source].save()
            source.write(result, out_dir)
    manual.write_template(run_date, out_dir)
    if has_readings(out_dir):
        fetched.sizing = text_sizing.run(out_dir)
    return fetched


async def download_readings(run_date: date, refresh: bool = False) -> FetchResult:
    async with http_client() as client:
        return await fetch_readings(
            run_date,
            sunday_dir(run_date),
            ARCHIVE_DIR / run_date.isoformat(),
            client,
            refresh,
            FAILED_DIR,
        )


def slug(name: str) -> str:
    return re.sub(r"\W+", "-", name.lower()).strip("-")


def prune(root: Path, kept: int) -> None:
    if root.is_dir():
        for old in sorted(p for p in root.iterdir() if p.is_dir())[:-kept]:
            shutil.rmtree(old)


################################################################################
# readings typed in or corrected by hand
################################################################################


def read_or_default(path: Path, default: Any) -> dict:
    return (read_yaml(path) or {}) if path.exists() else asdict(default)


def load_readings(run_date: date, out_dir: Path) -> Readings:
    feed = read_or_default(out_dir / "feed.yaml", DailyFeedPageData(formatted_date=long_date(run_date)))
    epistle = read_or_default(out_dir / "epistle.yaml", EpistlePageData())
    gospel = read_or_default(out_dir / "gospel.yaml", GospelPageData())
    liturgy = read_or_default(out_dir / "digital_chant_stand.yaml", LiturgyVariablesPageData())
    return Readings(
        lectionary_title=feed.get("lectionary_title") or "",
        formatted_date=feed.get("formatted_date") or "",
        icon_title=feed.get("icon_title") or "",
        epistle_book=epistle.get("book") or "",
        epistle_chapverse=epistle.get("chapverse") or "",
        prokeimenon=epistle.get("prokeimenon") or "",
        verse=epistle.get("verse") or "",
        epistle_text=epistle.get("text") or [],
        alleluia=liturgy.get("alleluia") or [],
        gospel_book=gospel.get("book") or "",
        gospel_chapverse=gospel.get("chapverse") or "",
        gospel_text=gospel.get("text") or [],
        size_override_pt=feed.get("size_override_pt"),
        layout_override=feed.get("layout_override") or "",
    )


def save_readings(run_date: date, out_dir: Path, readings: Readings) -> text_sizing.SizingResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    feed = read_or_default(out_dir / "feed.yaml", DailyFeedPageData())
    epistle = read_or_default(out_dir / "epistle.yaml", EpistlePageData())
    gospel = read_or_default(out_dir / "gospel.yaml", GospelPageData())
    liturgy = read_or_default(out_dir / "digital_chant_stand.yaml", LiturgyVariablesPageData())

    feed |= {
        "lectionary_title": readings.lectionary_title,
        "formatted_date": readings.formatted_date,
        "icon_title": readings.icon_title,
        "size_override_pt": readings.size_override_pt,
        "layout_override": readings.layout_override or None,
    }
    epistle |= {
        "book": readings.epistle_book,
        "chapverse": readings.epistle_chapverse,
        "prokeimenon": readings.prokeimenon,
        "verse": readings.verse,
        "text": readings.epistle_text,
    }
    gospel |= {
        "book": readings.gospel_book,
        "chapverse": readings.gospel_chapverse,
        "text": readings.gospel_text,
    }
    liturgy |= {"alleluia": readings.alleluia}

    write_yaml(feed, out_dir / "feed.yaml")
    write_yaml(epistle, out_dir / "epistle.yaml")
    write_yaml(gospel, out_dir / "gospel.yaml")
    write_yaml(liturgy, out_dir / "digital_chant_stand.yaml")
    manual.write_template(run_date, out_dir)
    return text_sizing.run(out_dir)
