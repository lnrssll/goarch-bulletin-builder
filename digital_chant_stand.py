from __future__ import annotations
from typing import Dict, List, Optional
from selectolax.parser import HTMLParser
from dataclasses import asdict
from pathlib import Path
import httpx
from datetime import date

from utils import fetch_html, to_alpha, write_yaml
from classes import RowItem, LiturgyVariablesPageData
from get_dismissal_hymns import get_dismissal_hymns
from get_scripture_reading import get_scripture_reading_sections, get_alleluia


def iter_row_items(tree: HTMLParser) -> List[RowItem]:
    items: List[RowItem] = []

    for node in tree.css("tbody > tr > td > *"):
        kind = node.attributes.get("class", "") if node.tag == "p" else "media"
        text = node.text().strip()
        items.append(RowItem(kind=to_alpha(kind), text=text, node=node))

    return items


def group_by_sections(items: List[RowItem]) -> Dict[str, List[RowItem]]:
    out: Dict[str, List[RowItem]] = {}
    current_section: Optional[str] = None
    source: Optional[RowItem] = None

    for it in items:
        if current_section is None:
            current_section = "__preamble__"
            out.setdefault(current_section, []).append(it)
            continue

        # sources preceed titles and must be stashed for the next section
        if it.kind == "source":
            source = it
            continue

        if it.kind == "designation" or (
            it.kind == "mixed" and it.text.startswith("Alleluia")
        ):
            current_section = it.text
            out.setdefault(current_section, []).append(it)
            if source:
                out.setdefault(current_section, []).append(source)
                source = None
            continue

        if it.kind == "mixed" and it.text.startswith("Alleluia"):
            current_section = it.text
            out.setdefault(current_section, []).append(it)
            if source:
                out.setdefault(current_section, []).append(source)
                source = None
            continue

        out[current_section].append(it)

    return out


async def process_liturgy_variables_page(tree: HTMLParser) -> LiturgyVariablesPageData:
    dcs_items = iter_row_items(tree)
    dcs_sections = group_by_sections(dcs_items)

    data = LiturgyVariablesPageData()

    data.dismissal_hymns = get_dismissal_hymns(dcs_sections)
    scripture_reading_sections = get_scripture_reading_sections(dcs_sections)
    data.alleluia = get_alleluia(scripture_reading_sections.alleluia_section)

    return data


async def run(run_date: date, out_dir: Path) -> None:
    slash_formatted_date = f"{run_date.year}/{run_date.month:02d}/{run_date.day:02d}"
    url = f"https://dcs.goarch.org/goa/dcs/h/s/{slash_formatted_date}/li2/en/"

    timeout = httpx.Timeout(20.0, connect=10.0)
    headers = {}

    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        tree = await fetch_html(client, url)
        data = await process_liturgy_variables_page(tree)
        await write_yaml(asdict(data), out_dir / "digital_chant_stand.yaml")
