import asyncio
import re
from collections.abc import Callable
from dataclasses import asdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import httpx
from lxml import etree
from selectolax.parser import HTMLParser

from classes import (
    DailyFeedPageData,
    EpistlePageData,
    GospelPageData,
    SaintFeastHymnData,
)
from utils import download_image, fetch_xml, http_client, write_yaml, xpath_text


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


async def identify_icon(
    client: httpx.AsyncClient, icon_src: str, commemoration_urls: list[str]
) -> str:
    tasks = [asyncio.create_task(fetch_xml(client, url)) for url in commemoration_urls]
    for coro in asyncio.as_completed(tasks):
        try:
            tree = await coro
        except Exception:
            continue

        if xpath_text(tree, "/saintfeast/icons/icon/url/text()") == icon_src:
            for t in tasks:
                t.cancel()
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


async def fetch_and_write[T](
    client: httpx.AsyncClient,
    url: str,
    out_path: Path,
    process: Callable[[etree._Element], T],
) -> T:
    data = process(await fetch_xml(client, url))
    await write_yaml(asdict(data), out_path)
    return data


async def run(run_date: date, out_dir: Path) -> None:
    index_page_url = (
        "https://onlinechapel.goarch.org/daily"
        f"?date={run_date.month}/{run_date.day}/{run_date.year}"
    )

    async with http_client() as client:
        feed_data = process_daily_feed_page(await fetch_xml(client, index_page_url))
        icon_title, *_ = await asyncio.gather(
            identify_icon(client, feed_data.icon_src, feed_data.saint_and_feast_urls),
            fetch_and_write(
                client,
                feed_data.epistle_page_url,
                out_dir / "epistle.yaml",
                process_epistle_page,
            ),
            fetch_and_write(
                client,
                feed_data.gospel_page_url,
                out_dir / "gospel.yaml",
                process_gospel_page,
            ),
            download_image(
                client, feed_data.icon_src, out_dir / feed_data.icon_filename
            ),
        )

        feed_data.icon_title = (
            icon_title if icon_title != feed_data.lectionary_title else ""
        )

        await write_yaml(asdict(feed_data), out_dir / "feed.yaml")
