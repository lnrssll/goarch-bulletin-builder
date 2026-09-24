import re

from classes import (
    DcsScriptureReadingSections,
    DcsSections,
    RowItem,
    ScriptureReading,
    ScriptureReadingData,
)


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


def get_scripture_reading_sections(sections: DcsSections) -> DcsScriptureReadingSections:
    data = DcsScriptureReadingSections(gospel_section=[])

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


def get_scripture_reading_data(
    sections: DcsScriptureReadingSections,
) -> ScriptureReadingData:
    return ScriptureReadingData(
        prokeimenon=get_prokeimenon(sections.epistle_section),
        epistle=get_reading(sections.epistle_section, "Epistle"),
        alleluia=get_alleluia(sections.alleluia_section),
        gospel=get_reading(sections.gospel_section, "Gospel"),
    )
