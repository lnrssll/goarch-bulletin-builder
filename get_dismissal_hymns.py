from typing import Dict, List
import re

from utils import to_alphanumeric
from classes import DismissalHymnData, RowItem


def get_dismissal_hymns(sections: Dict[str, List[RowItem]]) -> List[DismissalHymnData]:
    found = False
    dismissal_hymn_sections: List[List[RowItem]] = []
    for section_title, rows in sections.items():
        if section_title == "Hymns after the Entrance.":
            found = True
            continue
        if section_title == "Trisagios Hymn":
            break
        if found:
            dismissal_hymn_sections.append(rows)

    dismissal_hymns = []
    for hymn_section in dismissal_hymn_sections:

        hymn_data = {}
        for row in hymn_section:
            match row.kind:
                case "designation":
                    hymn_data["title"] = to_alphanumeric(row.text).strip()
                case "source":
                    hymn_data["source"] = to_alphanumeric(row.text).removeprefix("From").strip()
                case "mode":
                    mode_number = re.search(r"\d", row.text).group()
                    prefix = "Plagal " if "pl" in row.text else ""
                    hymn_data["mode"] = prefix + mode_number
                case "hymn":
                    hymn_data["text"] = row.node.css_first("span").text()

        dismissal_hymns.append(hymn_data)

    return dismissal_hymns
