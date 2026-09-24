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
    DailyFeedPageData,
    EpistlePageData,
    GospelPageData,
    SaintFeastHymnData,
)
from utils import NotArchived, ScrapeError, SourceArchive, xpath_text
from yaml_io import write_yaml


def paragraphs(body_html: str) -> list[str]:
    return [p.text() for p in HTMLParser(body_html).css("p")]


def process_daily_feed_page(tree: etree._Element) -> DailyFeedPageData:
    data = DailyFeedPageData()

    data.lectionary_title = xpath_text(tree, "/onlinechapel/lectionarytitle/text()")
    _weekday, _, data.formatted_date = xpath_text(
        tree, "/onlinechapel/formatteddate/text()"
    ).partition(" ")
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


def saint_feast_archive_name(url: str) -> str:
    content_id = parse_qs(urlparse(url).query)["contentid"][0]
    return f"saints/{content_id}.xml"


async def identify_icon(
    archive: SourceArchive, icon_src: str, saint_feast_urls: list[str]
) -> str:
    trees = await asyncio.gather(
        *(archive.fetch_xml(url, saint_feast_archive_name(url)) for url in saint_feast_urls),
        return_exceptions=True,
    )
    for tree in trees:
        if isinstance(tree, Exception):
            continue
        if xpath_text(tree, "/saintfeast/icons/icon/url/text()") == icon_src:
            return xpath_text(tree, "/saintfeast/title/text()")

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
            title=xpath_text(hymn, "title/text()"),
            short_title=xpath_text(hymn, "shorttitle/text()"),
            tone=xpath_text(hymn, "tone/text()"),
            type=xpath_text(hymn, "type/text()"),
            body=xpath_text(hymn, 'translation[@lang="en"]/body/text()'),
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


async def scrape(run_date: date, archive: SourceArchive) -> ChapelData:
    index_page_url = (
        "https://onlinechapel.goarch.org/daily"
        f"?date={run_date.month}/{run_date.day}/{run_date.year}"
    )
    feed = await fetch_and_process(
        archive, index_page_url, "chapel.xml", process_daily_feed_page
    )
    icon_title, epistle, gospel, icon = await asyncio.gather(
        identify_icon(archive, feed.icon_src, feed.saint_and_feast_urls),
        fetch_and_process(
            archive, feed.epistle_page_url, "epistle.xml", process_epistle_page
        ),
        fetch_and_process(
            archive, feed.gospel_page_url, "gospel.xml", process_gospel_page
        ),
        fetch_icon(archive, feed),
    )
    feed.icon_title = icon_title if icon_title != feed.lectionary_title else ""

    return ChapelData(feed, epistle, gospel, icon)


async def run(run_date: date, out_dir: Path, archive: SourceArchive) -> None:
    data = await scrape(run_date, archive)
    write_yaml(asdict(data.feed), out_dir / "feed.yaml")
    write_yaml(asdict(data.epistle), out_dir / "epistle.yaml")
    write_yaml(asdict(data.gospel), out_dir / "gospel.yaml")
    if data.icon:
        (out_dir / data.feed.icon_filename).write_bytes(data.icon)
