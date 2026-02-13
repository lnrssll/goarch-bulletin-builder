from dataclasses import dataclass
from typing import List, Dict
from selectolax.parser import HTMLParser


@dataclass
class RowItem:
    kind: str
    text: str
    node: HTMLParser


@dataclass
class DismissalHymnData:
    title: str
    mode: str
    source: str
    text: str


@dataclass
class DcsScriptureReadingSections:
    epistle_section: List[RowItem] | None = None
    alleluia_section: List[RowItem] | None = None
    gospel_section: List[RowItem] | None = None


@dataclass
class ScriptureReading:
    author: str
    chapverse: str
    text: List[str]


@dataclass
class ScriptureReadingData:
    prokeimenon: List[str] | None = None
    epistle: ScriptureReading | None = None
    alleluia: List[str] | None = None
    gospel: ScriptureReading | None = None


type DcsSections = Dict[str, List[RowItem]]


@dataclass
class LiturgyVariablesPageData:
    dismissal_hymns: List[DismissalHymnData] | None = None
    alleluia: List[str] | None = None


@dataclass
class DailyFeedPageData:
    formatted_date: str | None = None
    lectionary_title: str | None = None
    icon_src: str | None = None
    icon_filename: str | None = None
    icon_title: str | None = None
    epistle_page_url: str | None = None
    gospel_page_url: str | None = None
    saint_and_feast_urls: List[str] | None = None
    text_size_factor: int | None = None
    alleluia_page_break: bool | None = None
    gospel_page_break: bool | None = None


@dataclass
class EpistlePageData:
    book: str | None = None
    chapverse: str | None = None
    prokeimenon: str | None = None
    verse: str | None = None
    mode: int | None = None
    text: List[str] | None = None
    text_size_factor: int | None = None
    text_char_count: int | None = None


@dataclass
class GospelPageData:
    book: str | None = None
    chapverse: str | None = None
    text: List[str] | None = None
    text_size_factor: int | None = None
    text_char_count: int | None = None


@dataclass
class SaintFeastHymnData:
    title: str | None = None
    short_title: str | None = None
    tone: str | None = None
    type: str | None = None
    body: str | None = None
