import re
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

from selectolax.parser import HTMLParser, Node

from classes import DismissalHymnData, LiturgyVariablesPageData
from utils import ScrapeError, SourceArchive, to_alpha, to_alphanumeric
from yaml_io import write_yaml


@dataclass
class RowItem:
    kind: str
    text: str
    node: Node


type DcsSections = dict[str, list[RowItem]]


@dataclass
class ScriptureReadingSections:
    epistle_section: list[RowItem] | None = None
    alleluia_section: list[RowItem] | None = None
    gospel_section: list[RowItem] | None = None


@dataclass
class ScriptureReading:
    author: str
    chapverse: str
    reading: str


@dataclass
class ScriptureReadingData:
    prokeimenon: list[str] | None = None
    epistle: ScriptureReading | None = None
    alleluia: list[str] | None = None
    gospel: ScriptureReading | None = None


################################################################################
# page -> sections
################################################################################


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


################################################################################
# dismissal hymns
################################################################################


def dismissal_hymn_sections(sections: DcsSections) -> list[list[RowItem]]:
    found = False
    hymn_sections: list[list[RowItem]] = []
    for title, rows in sections.items():
        if title == "Trisagios Hymn":
            break
        if found:
            hymn_sections.append(rows)
        found = found or title == "Hymns after the Entrance."
    return hymn_sections


def parse_mode(text: str) -> str:
    prefix = "Plagal " if "pl" in text else ""
    match = re.search(r"\d", text)
    return prefix + (match.group() if match else "")


def parse_dismissal_hymn(rows: list[RowItem]) -> DismissalHymnData:
    hymn = DismissalHymnData()
    for row in rows:
        match row.kind:
            case "designation":
                hymn.title = to_alphanumeric(row.text).strip()
            case "source":
                hymn.source = to_alphanumeric(row.text).removeprefix("From").strip()
            case "mode":
                hymn.mode = parse_mode(row.text)
            case "hymn":
                hymn.text = row.node.css_first("span").text()
    return hymn


def get_dismissal_hymns(sections: DcsSections) -> list[DismissalHymnData]:
    return [parse_dismissal_hymn(rows) for rows in dismissal_hymn_sections(sections)]


################################################################################
# scripture readings
################################################################################


def get_scripture_reading_sections(sections: DcsSections) -> ScriptureReadingSections:
    data = ScriptureReadingSections(gospel_section=[])

    found_gospel = False
    for section_title, rows in sections.items():
        if section_title == "The Epistle":
            data.epistle_section = rows
        if section_title.startswith("Alleluia"):
            data.alleluia_section = rows
        found_gospel = found_gospel or section_title == "The Gospel"
        if found_gospel:
            data.gospel_section.extend(rows)
        if section_title == "Hymn to the Theotokos.":
            break

    return data


def get_prokeimenon(rows: list[RowItem]) -> list[str]:
    found = False
    prokeimenon_rows: list[RowItem] = []
    for row in rows:
        if row.kind == "dialog":
            break
        found = found or row.text.startswith("Prokeimenon")
        if found:
            prokeimenon_rows.append(row)
    _title_row, prokeimenon_row, verse_row = prokeimenon_rows

    prokeimenon = prokeimenon_row.node.css_first("span").text()
    verse = verse_row.node.css_first('[data-key*="prokeimenon"]').text()
    return [prokeimenon, verse]


def get_reading(rows: list[RowItem], data_key: str) -> ScriptureReading:
    def first(kind: str) -> RowItem:
        return next(row for row in rows if row.kind == kind)

    selector = f'[data-key*="{data_key}"]'
    return ScriptureReading(
        author=first("dialog").text.rstrip("."),
        chapverse=first("chapverse").node.css_first(selector).text(),
        reading=first("reading").node.css_first(selector).text(),
    )


def get_alleluia_mode(rows: list[RowItem]) -> int | None:
    title = rows[0].text
    if "Grave" in title:
        return 7
    match = re.search(r"Mode (pl\. )?(\d)", title)
    if match is None:
        return None
    plagal, number = match.groups()
    return int(number) + (4 if plagal else 0)


def get_alleluia(rows: list[RowItem]) -> list[str]:
    return [
        row.node.css_first('[data-key*="alleluia"]').text()
        for row in rows
        if row.kind == "verse"
    ]


def get_scripture_reading_data(sections: ScriptureReadingSections) -> ScriptureReadingData:
    return ScriptureReadingData(
        prokeimenon=get_prokeimenon(sections.epistle_section),
        epistle=get_reading(sections.epistle_section, "Epistle"),
        alleluia=get_alleluia(sections.alleluia_section),
        gospel=get_reading(sections.gospel_section, "Gospel"),
    )


################################################################################
# run
################################################################################


def process_liturgy_variables_page(tree: HTMLParser) -> LiturgyVariablesPageData:
    sections = group_by_sections(iter_row_items(tree))

    alleluia_section = get_scripture_reading_sections(sections).alleluia_section
    if not alleluia_section:
        raise ScrapeError("no Alleluia section found")
    alleluia = get_alleluia(alleluia_section)
    if not alleluia:
        raise ScrapeError("no Alleluia verses found")

    try:
        dismissal_hymns = get_dismissal_hymns(sections)
    except Exception as e:
        print(f"warning: dismissal hymns not scraped: {e!r}", file=sys.stderr)
        dismissal_hymns = None

    return LiturgyVariablesPageData(dismissal_hymns=dismissal_hymns, alleluia=alleluia)


async def scrape(run_date: date, archive: SourceArchive) -> LiturgyVariablesPageData:
    url = f"https://dcs.goarch.org/goa/dcs/h/s/{run_date:%Y/%m/%d}/li2/en/"
    tree = await archive.fetch_html(url, "dcs.html")
    try:
        return process_liturgy_variables_page(tree)
    except ScrapeError as e:
        raise ScrapeError(f"Digital Chant Stand {url}: {e}") from e


async def run(run_date: date, out_dir: Path, archive: SourceArchive) -> None:
    data = await scrape(run_date, archive)
    write_yaml(asdict(data), out_dir / "digital_chant_stand.yaml")
