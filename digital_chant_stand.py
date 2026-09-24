from dataclasses import asdict
from datetime import date
from pathlib import Path

from selectolax.parser import HTMLParser

from classes import DcsSections, LiturgyVariablesPageData, RowItem
from get_dismissal_hymns import get_dismissal_hymns
from get_scripture_reading import get_alleluia, get_scripture_reading_sections
from utils import SourceArchive, to_alpha
from yaml_io import write_yaml


def iter_row_items(tree: HTMLParser) -> list[RowItem]:
    items: list[RowItem] = []

    for node in tree.css("tbody > tr > td > *"):
        kind = node.attributes.get("class", "") if node.tag == "p" else "media"
        text = node.text().strip()
        items.append(RowItem(kind=to_alpha(kind), text=text, node=node))

    return items


def is_section_title(item: RowItem) -> bool:
    return item.kind == "designation" or (
        item.kind == "mixed" and item.text.startswith("Alleluia")
    )


def group_by_sections(items: list[RowItem]) -> DcsSections:
    current_section = "__preamble__"
    out: DcsSections = {current_section: []}
    source: RowItem | None = None

    for it in items:
        # a source row comes before the title of the section it belongs to
        if it.kind == "source":
            source = it
            continue

        if is_section_title(it):
            current_section = it.text
            out.setdefault(current_section, []).append(it)
            if source:
                out[current_section].append(source)
                source = None
            continue

        out[current_section].append(it)

    return out


def process_liturgy_variables_page(tree: HTMLParser) -> LiturgyVariablesPageData:
    dcs_sections = group_by_sections(iter_row_items(tree))
    scripture_reading_sections = get_scripture_reading_sections(dcs_sections)

    return LiturgyVariablesPageData(
        dismissal_hymns=get_dismissal_hymns(dcs_sections),
        alleluia=get_alleluia(scripture_reading_sections.alleluia_section),
    )


async def scrape(run_date: date, archive: SourceArchive) -> LiturgyVariablesPageData:
    url = f"https://dcs.goarch.org/goa/dcs/h/s/{run_date:%Y/%m/%d}/li2/en/"
    return process_liturgy_variables_page(await archive.fetch_html(url, "dcs.html"))


async def run(run_date: date, out_dir: Path, archive: SourceArchive) -> None:
    data = await scrape(run_date, archive)
    write_yaml(asdict(data), out_dir / "digital_chant_stand.yaml")
