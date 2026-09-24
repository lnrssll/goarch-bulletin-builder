import re

from classes import DcsSections, DismissalHymnData, RowItem
from utils import to_alphanumeric


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
