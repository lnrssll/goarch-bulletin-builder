"""The saints and feasts goarch.org lists for a Sunday, and which of their hymns the Chant Stand uses.

The Chant Stand and goarch.org use different translations of the same hymn ("Your Martyrs, O Lord"
and "Thy Martyrs, O Lord"), so hymns are compared by the words they share. A Chant Stand hymn that
isn't on goarch.org (most often the kontakion) gets the titles it was saved under on past Sundays.
"""

import asyncio
import re
from dataclasses import asdict
from datetime import date
from pathlib import Path

import goarch_xml_feed
import manual
from utils import ARCHIVE_DIR, NotArchived, ScrapeError, SourceArchive
from yaml_io import read_yaml

# Share of the shorter hymn's words that the other has too. In the archived Sundays the same hymn
# shares 0.42 or more, and different hymns 0.31 or less.
SAME_HYMN = 0.4

MODERN = {
    "thy": "your",
    "thine": "your",
    "thou": "you",
    "thee": "you",
    "ye": "you",
    "hast": "have",
    "hath": "has",
    "art": "are",
    "didst": "did",
    "dost": "do",
    "doth": "does",
    "wast": "were",
}
COMMON = set(
    "a an and are as at be by for from has have he her his i in is it its me my o of on our "
    "she that the their this to us was we were which who with you your".split()
)
ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4}
# the Chant Stand's own translation, the same from year to year
SAME_TEXT = 0.8


def load(run_date: date, out_dir: Path) -> list[dict]:
    path = out_dir / goarch_xml_feed.COMMEMORATIONS_FILE
    if path.exists():
        return (read_yaml(path) or {}).get("commemorations") or []
    # a Sunday downloaded before the commemorations were kept
    archive = SourceArchive(ARCHIVE_DIR / run_date.isoformat())
    try:
        found = asyncio.run(goarch_xml_feed.scrape_commemorations(run_date, archive))
    except (NotArchived, ScrapeError):
        return []
    return [asdict(c) for c in found]


def words(text: str) -> set[str]:
    found = set()
    for word in re.findall(r"[a-z]+", text.lower()):
        word = MODERN.get(word, word)
        if len(word) > 5:
            # givest, maketh
            word = re.sub(r"(?:est|eth)$", "", word)
        if word not in COMMON:
            found.add(word)
    return found


def similarity(a: str, b: str) -> float:
    words_a, words_b = words(a), words(b)
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / min(len(words_a), len(words_b))


def mode_number(text: str | None) -> int | None:
    """The bulletin's mode (1-8) from "Plagal 1" (Chant Stand) or "Plagal of the First Tone" (goarch.org)."""
    text = (text or "").lower()
    if "grave" in text:
        return 7
    digit = re.search(r"[1-4]", text)
    ordinal = next((n for name, n in ORDINALS.items() if name in text), None)
    number = int(digit.group()) if digit else ordinal
    if number is None:
        return None
    return number + 4 if "pl" in text else number


def chant_stand_mode(hymn: dict) -> int | None:
    # "Kontakion Mode 2" has its mode in the title
    return mode_number(hymn.get("mode")) or mode_number(hymn.get("title"))


def compare(chant_stand: list[dict], commemorations: list[dict]) -> tuple[list[dict], list[dict]]:
    """Copies of both lists, each hymn with the hymns on the other side that are the same one.

    A Chant Stand hymn gets `on_goarch` (each with the goarch.org hymn and its commemoration's
    title), and a goarch.org hymn gets `in_chant_stand`. Both get `mode_number`.
    """
    chant_stand = [hymn | {"mode_number": chant_stand_mode(hymn), "on_goarch": []} for hymn in chant_stand]
    commemorations = [dict(commemoration) for commemoration in commemorations]
    for commemoration in commemorations:
        if commemoration.get("hymns") is None:
            continue
        commemoration["hymns"] = [
            hymn | {"mode_number": mode_number(hymn.get("tone")), "in_chant_stand": []}
            for hymn in commemoration["hymns"]
        ]
        for hymn in commemoration["hymns"]:
            for chanted in chant_stand:
                if similarity(chanted.get("text") or "", hymn.get("body") or "") >= SAME_HYMN:
                    hymn["in_chant_stand"].append(chanted)
                    chanted["on_goarch"].append({"hymn": hymn, "commemoration": commemoration["title"]})
    return chant_stand, commemorations


def kind(title: str) -> str:
    title = title.casefold()
    if "kont" in title:
        return "kontakion"
    if re.search(r"res+ur+ect", title):
        return "resurrectional"
    return "apolytikion"


def saved_as(chanted: dict, saved: list) -> list[str]:
    """The titles saved that Sunday that could be this Chant Stand hymn: the same kind, and the same mode if known.

    The Chant Stand's list and the saved one don't line up row by row (the parish adds hymns, and
    older downloads missed some), but a Sunday rarely has two hymns of one kind in one mode.
    """
    mode = chant_stand_mode(chanted)
    return [
        hymn.title
        for hymn in saved
        if hymn.title
        and hymn.title != manual.EXAMPLE_HYMN_TITLE
        and kind(hymn.title) == kind(chanted.get("title") or "")
        and (mode is None or hymn.mode is None or hymn.mode == mode)
    ]


def add_past_titles(
    chant_stand: list[dict], run_date: date, sundays_dir: Path, catalog: manual.HymnCatalog | None = None
) -> None:
    """Gives each Chant Stand hymn `used_before`: the titles the same text was saved under, most used first."""
    if catalog is None:
        catalog = manual.hymn_catalog()
    usual = {
        manual.hymn_key(name, catalog.abbreviations): hymn.title for hymn in catalog.hymns for name in (hymn.title, *hymn.also)
    }
    found: list[dict[str, list[date]]] = [{} for _ in chant_stand]
    past_dirs = sorted((p for p in sundays_dir.iterdir() if p.is_dir()), reverse=True) if sundays_dir.is_dir() else []
    for out_dir in past_dirs[: manual.SUGGESTION_SUNDAYS]:
        try:
            day = date.fromisoformat(out_dir.name)
        except ValueError:
            continue
        details = manual.read(out_dir)
        chant_stand_file = out_dir / "digital_chant_stand.yaml"
        if day == run_date or details is None or not chant_stand_file.exists():
            continue
        for earlier in (read_yaml(chant_stand_file) or {}).get("dismissal_hymns") or []:
            for hymn, titles in zip(chant_stand, found, strict=True):
                if similarity(hymn.get("text") or "", earlier.get("text") or "") < SAME_TEXT:
                    continue
                for title in saved_as(earlier, details.dismissal_hymns):
                    key = manual.hymn_key(title, catalog.abbreviations)
                    title = usual.get(key) or manual.expand_abbreviations(title, catalog.abbreviations)
                    dates = titles.setdefault(title, [])
                    if day not in dates:
                        dates.append(day)
    for hymn, titles in zip(chant_stand, found, strict=True):
        ranked = sorted(titles.items(), key=lambda item: (-len(item[1]), -item[1][0].toordinal()))
        hymn["used_before"] = [{"title": title, "when": when(dates, run_date)} for title, dates in ranked]


def when(dates: list[date], today: date, shown: int = 3) -> str:
    def label(day: date) -> str:
        return f"{day:%b} {day.day}" + ("" if day.year == today.year else f", {day.year}")

    more = len(dates) - shown
    return ", ".join(label(day) for day in dates[:shown]) + (f" and {more} more" if more > 0 else "")
