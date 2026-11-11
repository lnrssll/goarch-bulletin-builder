import asyncio
import re
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from lxml import etree
from selectolax.parser import HTMLParser

from classes import (
    CommemorationData,
    DailyFeedPageData,
    EpistlePageData,
    GospelPageData,
    SaintFeastHymnData,
)
from utils import NotArchived, ScrapeError, SourceArchive, xpath_text
from yaml_io import write_yaml

COMMEMORATIONS_FILE = "commemorations.yaml"


def optional_text(tree: etree._Element, path: str) -> str:
    matches = tree.xpath(path)
    return str(matches[0]) if matches else ""


def paragraphs(body_html: str) -> list[str]:
    return [p.text() for p in HTMLParser(body_html).css("p")]


def process_daily_feed_page(tree: etree._Element) -> DailyFeedPageData:
    data = DailyFeedPageData()

    data.lectionary_title = xpath_text(tree, "/onlinechapel/lectionarytitle/text()")
    _weekday, _, formatted_date = xpath_text(
        tree, "/onlinechapel/formatteddate/text()"
    ).partition(" ")
    # "November 08, 2026" as "November 8, 2026", like sunday.long_date
    data.formatted_date = re.sub(r" 0(\d),", r" \1,", formatted_date)
    data.epistle_page_url = xpath_text(
        tree, '/onlinechapel/readings/reading[type="E"]/url/text()'
    )
    data.gospel_page_url = xpath_text(
        tree, '/onlinechapel/readings/reading[type="G"]/url/text()'
    )
    data.saint_and_feast_urls = [
        str(url)
        for url in tree.xpath("/onlinechapel/saintsfeasts/saintfeast/url/text()")
    ]
    data.icon_src = xpath_text(tree, "/onlinechapel/icon/text()")
    data.icon_filename = Path(urlparse(data.icon_src).path).name

    return data


def process_commemorations(tree: etree._Element) -> list[CommemorationData]:
    return [
        CommemorationData(
            title=optional_text(item, "title/text()"),
            url=optional_text(item, "url/text()"),
            public_url=optional_text(item, "publicurl/text()"),
        )
        for item in tree.xpath("/onlinechapel/saintsfeasts/saintfeast")
    ]


def process_chapel_page(
    tree: etree._Element,
) -> tuple[DailyFeedPageData, list[CommemorationData]]:
    return process_daily_feed_page(tree), process_commemorations(tree)


async def fetch_saint_feast_page(
    archive: SourceArchive, url: str
) -> etree._Element | None:
    content_id = parse_qs(urlparse(url).query).get("contentid")
    if not content_id:
        return None
    name = f"saints/{content_id[0]}.xml"
    try:
        tree = await archive.fetch_xml(url, name)
    except (httpx.HTTPError, NotArchived, ScrapeError):
        return None
    if tree is None or tree.tag != "saintfeast":
        # a bot-check page, which must not be archived
        archive.discard(name)
        return None
    return tree


async def fetch_commemorations(
    archive: SourceArchive, commemorations: list[CommemorationData]
) -> list[etree._Element | None]:
    pages = await asyncio.gather(
        *(fetch_saint_feast_page(archive, c.url) for c in commemorations)
    )
    for commemoration, page in zip(commemorations, pages, strict=True):
        commemoration.hymns = None if page is None else process_saint_feast_page(page)
    return pages


def identify_icon(icon_src: str, saint_feast_pages: list[etree._Element | None]) -> str:
    for page in saint_feast_pages:
        if page is not None and optional_text(page, "/saintfeast/icons/icon/url/text()") == icon_src:
            return optional_text(page, "/saintfeast/title/text()")
    return ""


def process_epistle_page(tree: etree._Element) -> EpistlePageData:
    data = EpistlePageData()

    tree = tree.xpath('/onlinechapel/translation[@xml:lang="en"]')[0]

    title = xpath_text(tree, "title/text()")
    first_digit = re.search(r"\d", title).start()
    data.book = title[:first_digit].rstrip()
    data.chapverse = title[first_digit:].lstrip()

    data.prokeimenon = xpath_text(tree, "prokprokeimenon/text()")
    data.verse = xpath_text(tree, "prokverse/text()").removeprefix("Verse: ")
    data.mode = int(xpath_text(tree, "prokmode/text()"))
    data.text = paragraphs(xpath_text(tree, "body/text()"))

    return data


def process_gospel_page(tree: etree._Element) -> GospelPageData:
    data = GospelPageData()

    tree = tree.xpath('/onlinechapel/translation[@xml:lang="en"]')[0]

    author, _, data.chapverse = xpath_text(tree, "title/text()").partition(" ")
    data.book = "The Holy Gospel According to St. " + author
    data.text = paragraphs(xpath_text(tree, "body/text()"))

    return data


def process_saint_feast_page(tree: etree._Element) -> list[SaintFeastHymnData]:
    return [
        SaintFeastHymnData(
            title=optional_text(hymn, "title/text()"),
            short_title=optional_text(hymn, "shorttitle/text()"),
            tone=optional_text(hymn, "tone/text()"),
            type=optional_text(hymn, "type/text()"),
            body=optional_text(hymn, 'translation[@lang="en"]/body/text()').strip(),
        )
        for hymn in tree.xpath("/saintfeast/hymns/hymn")
    ]


async def fetch_icon(archive: SourceArchive, feed: DailyFeedPageData) -> bytes | None:
    try:
        return await archive.fetch(feed.icon_src, f"icon/{feed.icon_filename}")
    except (httpx.HTTPError, NotArchived) as e:
        print(f"warning: icon not downloaded: {e!r}", file=sys.stderr)
        return None


async def fetch_and_process[T](
    archive: SourceArchive,
    url: str,
    name: str,
    process: Callable[[etree._Element], T],
) -> T:
    tree = await archive.fetch_xml(url, name)
    try:
        return process(tree)
    except (ScrapeError, AttributeError, IndexError, ValueError) as e:
        raise ScrapeError(f"Online Chapel {name} {url}: {e!r}") from e


@dataclass
class ChapelData:
    feed: DailyFeedPageData
    epistle: EpistlePageData
    gospel: GospelPageData
    icon: bytes | None
    commemorations: list[CommemorationData]


def page_url(run_date: date) -> str:
    return (
        "https://onlinechapel.goarch.org/daily"
        f"?date={run_date.month}/{run_date.day}/{run_date.year}"
    )


async def scrape(run_date: date, archive: SourceArchive) -> ChapelData:
    feed, commemorations = await fetch_and_process(
        archive, page_url(run_date), "chapel.xml", process_chapel_page
    )
    saint_feast_pages, epistle, gospel, icon = await asyncio.gather(
        fetch_commemorations(archive, commemorations),
        fetch_and_process(
            archive, feed.epistle_page_url, "epistle.xml", process_epistle_page
        ),
        fetch_and_process(
            archive, feed.gospel_page_url, "gospel.xml", process_gospel_page
        ),
        fetch_icon(archive, feed),
    )
    icon_title = identify_icon(feed.icon_src, saint_feast_pages)
    feed.icon_title = icon_title if icon_title != feed.lectionary_title else ""

    return ChapelData(feed, epistle, gospel, icon, commemorations)


async def scrape_commemorations(
    run_date: date, archive: SourceArchive
) -> list[CommemorationData]:
    _feed, commemorations = await fetch_and_process(
        archive, page_url(run_date), "chapel.xml", process_chapel_page
    )
    await fetch_commemorations(archive, commemorations)
    return commemorations


def write(data: ChapelData, out_dir: Path) -> None:
    write_yaml(asdict(data.feed), out_dir / "feed.yaml")
    write_yaml(asdict(data.epistle), out_dir / "epistle.yaml")
    write_yaml(asdict(data.gospel), out_dir / "gospel.yaml")
    write_yaml(
        {"commemorations": [asdict(c) for c in data.commemorations]},
        out_dir / COMMEMORATIONS_FILE,
    )
    if data.icon:
        (out_dir / data.feed.icon_filename).write_bytes(data.icon)
