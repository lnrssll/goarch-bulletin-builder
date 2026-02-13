from typing import Dict, List
import re

from classes import (
    RowItem,
    DcsScriptureReadingSections,
    ScriptureReadingData,
    ScriptureReading,
    DcsSections,
)


def get_reading_rows(rows: List[RowItem]) -> Dict:
    author_row = next(row for row in rows if row.kind == "dialog")
    chapverse_row = next(row for row in rows if row.kind == "chapverse")
    reading_row = next(row for row in rows if row.kind == "reading")

    return {
        "author": author_row,
        "chapverse": chapverse_row,
        "reading": reading_row,
    }


def get_prokeimenon(rows: List[RowItem]) -> List[str]:
    found = False
    prokeimenon_rows: List[RowItem] = []
    for row in rows:
        if row.kind == "dialog":
            break
        if not found and row.text.startswith("Prokeimenon"):
            found = True
        if found:
            prokeimenon_rows.append(row)
    title_row, prokeimenon_row, verse_row = prokeimenon_rows

    mode = next(n for n in title_row.node.css("span") if n.text().startswith("Mode"))
    _mode_number = re.search(r"\d", mode.text()).group()
    _source = title_row.node.css("span")[-1].text().rstrip(".")

    prokeimenon = prokeimenon_row.node.css_first("span").text()
    verse = verse_row.node.css_first('[data-key*="prokeimenon"]').text()
    return [prokeimenon, verse]


def get_epistle(rows: List[RowItem]) -> ScriptureReading:
    rows = get_reading_rows(rows)
    author_row, chapverse_row, reading_row = (
        rows["author"],
        rows["chapverse"],
        rows["reading"],
    )

    author = author_row.text.rstrip(".")
    chapverse = chapverse_row.node.css_first('[data-key*="Epistle"]').text()
    reading = reading_row.node.css_first('[data-key*="Epistle"]').text()
    _translation = reading_row.node.css_first(".versiondesignation").text()

    return {"author": author, "chapverse": chapverse, "reading": reading}


def get_alleluia(rows: List[RowItem]) -> List[str]:
    title_row = rows[0]
    mode = next(n for n in title_row.node.css("span") if n.text().startswith("Mode"))
    _mode_number = re.search(r"\d", mode.text()).group()
    _source = title_row.node.css("span")[-1].text().rstrip(".")

    verse_rows: List[RowItem] = [
        row.node.css_first('[data-key*="alleluia"]').text()
        for row in rows
        if row.kind == "verse"
    ]
    return verse_rows


def get_gospel(rows: List[RowItem]) -> ScriptureReading:
    rows = get_reading_rows(rows)
    author_row, chapverse_row, reading_row = (
        rows["author"],
        rows["chapverse"],
        rows["reading"],
    )

    author = author_row.text.rstrip(".")
    chapverse = chapverse_row.node.css_first('[data-key*="Gospel"]').text()
    reading = reading_row.node.css_first('[data-key*="Gospel"]').text()
    _translation = reading_row.node.css_first(".versiondesignation").text()

    return {"author": author, "chapverse": chapverse, "reading": reading}


def get_scripture_reading_sections(
    sections: DcsSections,
) -> DcsScriptureReadingSections:
    data = DcsScriptureReadingSections()

    gospel_sections: List[List[RowItem]] = []
    found_gospel = False
    for section_title, rows in sections.items():
        if section_title == "The Epistle":
            data.epistle_section = rows
        if section_title.startswith("Alleluia"):
            data.alleluia_section = rows
        if section_title == "The Gospel":
            found_gospel = True
            gospel_sections.append(rows)
            continue
        if found_gospel:
            gospel_sections.append(rows)
        if section_title == "Hymn to the Theotokos.":
            break

    data.gospel_section = sum(gospel_sections, [])

    return data


def get_scripture_reading_data(
    sections: DcsScriptureReadingSections,
) -> ScriptureReadingData:
    data = ScriptureReadingData()

    data.prokeimenon = get_prokeimenon(sections.epistle_section)
    data.epistle = get_epistle(sections.epistle_section)
    data.alleluia = get_alleluia(sections.alleluia_section)
    data.gospel = get_gospel(sections.gospel_section)

    return data
