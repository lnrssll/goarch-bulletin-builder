import re
import math
from pathlib import Path
from urllib.parse import urlparse
from dataclasses import asdict
from selectolax.parser import HTMLParser
import httpx
import asyncio
from datetime import date
from lxml import etree
from typing import List, Callable, TypeVar

from utils import download_image, fetch_xml, write_yaml
from classes import (
    DailyFeedPageData,
    EpistlePageData,
    GospelPageData,
    SaintFeastHymnData,
)

DISMISSAL_HYMN_CHAR_LIMIT = 45
T = TypeVar("T")


def process_daily_feed_page(tree: etree._Element) -> DailyFeedPageData:
    data = DailyFeedPageData()

    data.lectionary_title = str(tree.xpath("/onlinechapel/lectionarytitle/text()")[0])
    data.formatted_date = " ".join(
        str(tree.xpath("/onlinechapel/formatteddate/text()")[0]).split(" ")[1:]
    )
    data.epistle_page_url = str(
        tree.xpath('/onlinechapel/readings/reading[type="E"]/url/text()')[0]
    )
    data.gospel_page_url = str(
        tree.xpath('/onlinechapel/readings/reading[type="G"]/url/text()')[0]
    )
    data.saint_and_feast_urls = [
        str(url)
        for url in tree.xpath("/onlinechapel/saintsfeasts/saintfeast/url/text()")
    ]
    data.icon_src = str(tree.xpath("/onlinechapel/icon/text()")[0])
    data.icon_filename = Path(urlparse(data.icon_src).path).name

    return data


async def identify_icon(
    client: httpx.AsyncClient, icon_src: str, commemoration_urls: List[str]
):
    tasks = [asyncio.create_task(fetch_xml(client, url)) for url in commemoration_urls]
    for coro in asyncio.as_completed(tasks):
        try:
            tree = await coro
        except Exception:
            continue

        if tree.xpath("/saintfeast/icons/icon/url/text()")[0] == icon_src:
            for t in tasks:
                t.cancel()

            title = tree.xpath("/saintfeast/title/text()")[0]
            # synaxarion = tree.xpath('/saintfeast/readings/translations[@lang="en"]/body/text()')[0]
            return str(title)

    return ""


def process_epistle_page(tree: etree._Element) -> EpistlePageData:
    data = EpistlePageData()

    tree = tree.xpath('/onlinechapel/translation[@xml:lang="en"]')[0]

    title = str(tree.xpath("title/text()")[0])
    split_char = re.search(r"\d", title)
    data.book = title[: split_char.start()].rstrip()
    data.chapverse = title[split_char.start() :].lstrip()

    data.prokeimenon = str(tree.xpath("prokprokeimenon/text()")[0])
    data.verse = str(tree.xpath("prokverse/text()")[0]).lstrip("Verse: ")
    data.mode = int(tree.xpath("prokmode/text()")[0])
    body_html = str(tree.xpath("body/text()")[0])
    data.text = [x.text() for x in HTMLParser(body_html).css("p")]
    data.text_char_count = len(" ".join(data.text))
    data.text_size_factor = min(
        round(100.0 * (1 - (1 - 1000.0 / data.text_char_count) ** 2)), 100
    )

    return data


def process_gospel_page(tree: etree._Element) -> GospelPageData:
    data = GospelPageData()

    tree = tree.xpath('/onlinechapel/translation[@xml:lang="en"]')[0]

    author, _, data.chapverse = str(tree.xpath("title/text()")[0]).partition(" ")
    data.book = "The Holy Gospel According to St. " + author
    body_html = str(tree.xpath("body/text()")[0])
    data.text = [x.text() for x in HTMLParser(body_html).css("p")]
    data.text_char_count = len(" ".join(data.text))
    data.text_size_factor = min(
        round(100.0 * (1 - (1 - 1000.0 / data.text_char_count) ** 2)), 100
    )

    return data


def process_saint_feast_page(tree: etree._Element) -> List[SaintFeastHymnData]:
    data: List[SaintFeastHymnData] = []

    hymns = tree.xpath("/saintfeast/hymns/hymn")

    for tree in hymns:
        hymn_data = SaintFeastHymnData()

        hymn_data.title = str(tree.xpath("title/text()")[0])
        hymn_data.short_title = str(tree.xpath("shorttitle/text()")[0])
        hymn_data.tone = str(tree.xpath("tone/text()")[0])
        hymn_data.type = str(tree.xpath("type/text()")[0])
        hymn_data.body = str(tree.xpath('translation[@lang="en"]/body/text()')[0])

        data.push(hymn_data)

    return data


async def pipeline(
    client: httpx.AsyncClient,
    url: str,
    out_path: Path,
    process: Callable[[etree._Element], T],
) -> None:
    tree = await fetch_xml(client, url)
    data = process(tree)
    if out_path:
        await write_yaml(asdict(data), out_path)
    return data


async def run(run_date: date, out_dir: Path) -> None:
    base_url = "https://onlinechapel.goarch.org/daily"
    params = f"date={run_date.month}/{run_date.day}/{run_date.year}"
    index_page_url = f"{base_url}?{params}"

    timeout = httpx.Timeout(20.0, connect=10.0)
    headers = {}

    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        feed_data: DailyFeedPageData = await pipeline(
            client, index_page_url, None, process_daily_feed_page
        )
        icon_title, epistle_page_data, gospel_page_data, _ = await asyncio.gather(
            identify_icon(client, feed_data.icon_src, feed_data.saint_and_feast_urls),
            pipeline(
                client,
                feed_data.epistle_page_url,
                out_dir / "epistle.yaml",
                process_epistle_page,
            ),
            pipeline(
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

        text_size_factor_decimal = math.sqrt(
            (gospel_page_data.text_size_factor / 100.0)
            * (epistle_page_data.text_size_factor / 100.0)
        )
        feed_data.text_size_factor = 100 * round(text_size_factor_decimal, 2)
        gospel_text_area_units = (
            gospel_page_data.text_char_count * text_size_factor_decimal**2
        )
        feed_data.alleluia_page_break = gospel_text_area_units < 1_200
        feed_data.gospel_page_break = (
            gospel_text_area_units < 1_400 and not feed_data.alleluia_page_break
        )
        await write_yaml(asdict(feed_data), out_dir / "feed.yaml")
