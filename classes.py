from dataclasses import dataclass


@dataclass
class DismissalHymnData:
    title: str | None = None
    mode: str | None = None
    source: str | None = None
    text: str | None = None


@dataclass
class LiturgyVariablesPageData:
    dismissal_hymns: list[DismissalHymnData] | None = None
    alleluia: list[str] | None = None


@dataclass
class DailyFeedPageData:
    formatted_date: str | None = None
    lectionary_title: str | None = None
    icon_src: str | None = None
    icon_filename: str | None = None
    icon_title: str | None = None
    epistle_page_url: str | None = None
    gospel_page_url: str | None = None
    saint_and_feast_urls: list[str] | None = None
    text_size_factor: float | None = None
    alleluia_page_break: bool | None = None
    gospel_page_break: bool | None = None
    font_size_pt: float | None = None
    layout: str | None = None
    page_fill: list[float] | None = None


@dataclass
class EpistlePageData:
    book: str | None = None
    chapverse: str | None = None
    prokeimenon: str | None = None
    verse: str | None = None
    mode: int | None = None
    text: list[str] | None = None


@dataclass
class GospelPageData:
    book: str | None = None
    chapverse: str | None = None
    text: list[str] | None = None


@dataclass
class SaintFeastHymnData:
    title: str | None = None
    short_title: str | None = None
    tone: str | None = None
    type: str | None = None
    body: str | None = None
