import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import parish
from classes import ManualData, ManualHymnData, UpcomingServiceData
from yaml_io import read_yaml, write_yaml

FILENAME = "manual.yaml"
HYMN_CATALOG_PATH = Path("data/hymns.yaml")
EXAMPLE_HYMN_TITLE = "Example"
UNKNOWN_PRIEST = "Fr. X"
PRIEST_PREFIX = "Fr."
PAGE_PREFIX = "p."
READER_SERVICE = "Reader Service"
NO_PRIEST = (READER_SERVICE, "TBD")
NOT_A_PAGE = ("Choir", "Handout")
PRIEST_PREFIX_RE = re.compile(r"^(?:fr\b\.?|father\b)\s*", re.IGNORECASE)
PAGE_PREFIX_RE = re.compile(r"^(?:pages?|pg|pp|p)\.?\s*(?=\d)", re.IGNORECASE)
HYMNAL_PAGE_RE = re.compile(r"^p\. (\d+)")
SERVICE_DATE_FORMAT = "%m/%d/%Y"
MODES = range(1, 9)
LOOKBACK_WEEKS = 8
SUGGESTION_SUNDAYS = 52


@dataclass
class HymnSuggestion:
    title: str
    mode: int | None = None
    page: str = ""
    pages_by_mode: dict[int, str] = field(default_factory=dict)
    also: list[str] = field(default_factory=list)

    @property
    def detail(self) -> str:
        parts = [f"Mode {self.mode}"] if self.mode else []
        if self.pages_by_mode:
            parts.append("page depends on mode")
        elif self.page:
            parts.append(page_label(self.page))
        return ", ".join(parts)


@dataclass
class HymnCatalog:
    hymns: list[HymnSuggestion] = field(default_factory=list)
    abbreviations: dict[str, str] = field(default_factory=dict)


@dataclass
class Suggestions:
    hymns: list[HymnSuggestion] = field(default_factory=list)
    priests: list[str] = field(default_factory=list)
    page_words: tuple[str, ...] = NOT_A_PAGE


def service_day(run_date: date, liturgy_day: str) -> date:
    return run_date - timedelta(days=1) if liturgy_day == parish.SATURDAY else run_date


def parse_service_date(text: str) -> date | None:
    try:
        return datetime.strptime(text.strip(), SERVICE_DATE_FORMAT).date()
    except ValueError:
        return None


def parse_mode(value: object) -> int | None:
    try:
        mode = int(str(value))
    except ValueError:
        return None
    return mode if mode in MODES else None


def standard_spelling(text: str, words: tuple[str, ...]) -> str:
    return next((word for word in words if word.casefold() == text.casefold()), text)


def page_label(text: str) -> str:
    text = page_number(text)
    if text[:1].isdigit():
        return f"{PAGE_PREFIX} {text}"
    return standard_spelling(text, NOT_A_PAGE)


def page_number(page: str) -> str:
    return PAGE_PREFIX_RE.sub("", page.strip())


def priest_label(text: str) -> str:
    name = priest_name(text)
    plain = standard_spelling(name, NO_PRIEST)
    if not name or plain in NO_PRIEST:
        return plain
    return f"{PRIEST_PREFIX} {name}"


def priest_name(priest: str) -> str:
    return PRIEST_PREFIX_RE.sub("", priest.strip())


def expand_abbreviations(title: str, abbreviations: dict[str, str]) -> str:
    for word, short in abbreviations.items():
        title = re.sub(rf"\b{re.escape(short)}", word, title, flags=re.IGNORECASE)
    return title


def hymn_key(title: str, abbreviations: dict[str, str]) -> str:
    return re.sub(r"\W+", "", expand_abbreviations(title, abbreviations).casefold())


def as_text(value: object) -> str:
    return "" if value is None else str(value).strip()


def read(out_dir: Path) -> ManualData | None:
    path = out_dir / FILENAME
    if not path.exists():
        return None
    data = read_yaml(path) or {}
    return ManualData(
        dismissal_hymns=[
            ManualHymnData(
                title=as_text(hymn.get("title")),
                mode=parse_mode(hymn.get("mode")),
                page=as_text(hymn.get("page")),
            )
            for hymn in data.get("dismissal_hymns") or []
        ],
        upcoming_services=[
            UpcomingServiceData(date=as_text(service.get("date")), priest=as_text(service.get("priest")))
            for service in data.get("upcoming_services") or []
        ],
    )


def write(data: ManualData, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    write_yaml(asdict(data), out_dir / FILENAME)


def previous(run_date: date, sundays_dir: Path) -> ManualData | None:
    for weeks in range(1, LOOKBACK_WEEKS + 1):
        data = read(sundays_dir / (run_date - timedelta(weeks=weeks)).isoformat())
        if data:
            return data
    return None


def template(run_date: date, previous: ManualData | None, settings: parish.Settings) -> ManualData:
    today = service_day(run_date, settings.liturgy_day)
    next_service = service_day(run_date + timedelta(weeks=1), settings.liturgy_day)

    priest_today = UNKNOWN_PRIEST
    later: dict[date, UpcomingServiceData] = {}
    for service in previous.upcoming_services if previous else []:
        day = parse_service_date(service.date)
        if day == today:
            priest_today = service.priest
        elif day and day > today:
            later[day] = service
    later.setdefault(
        next_service,
        UpcomingServiceData(f"{next_service:{SERVICE_DATE_FORMAT}}", UNKNOWN_PRIEST),
    )

    return ManualData(
        dismissal_hymns=[ManualHymnData(EXAMPLE_HYMN_TITLE, 9, "p. 0")],
        upcoming_services=[
            UpcomingServiceData(settings.today, priest_today),
            *(later[day] for day in sorted(later)),
        ],
    )


def write_template(run_date: date, out_dir: Path) -> None:
    if (out_dir / FILENAME).exists():
        return
    write(template(run_date, previous(run_date, out_dir.parent), parish.load()), out_dir)


def unfinished(data: ManualData) -> list[str]:
    notes = []
    if not data.dismissal_hymns:
        notes.append("No Hymns of the Day are listed.")
    if any(hymn.title == EXAMPLE_HYMN_TITLE for hymn in data.dismissal_hymns):
        notes.append(f"The “{EXAMPLE_HYMN_TITLE}” hymn is still listed.")
    if any(service.priest == UNKNOWN_PRIEST for service in data.upcoming_services):
        notes.append(f"An upcoming service still says “{UNKNOWN_PRIEST}”.")
    for hymn in data.dismissal_hymns:
        page = HYMNAL_PAGE_RE.match(hymn.page)
        if hymn.title != EXAMPLE_HYMN_TITLE and page and int(page[1]) % 2 == 0:
            notes.append(
                f"“{hymn.title}” is on p. {page[1]}, an even page. The English is on the odd pages."
            )
    return notes


def hymn_catalog(path: Path = HYMN_CATALOG_PATH) -> HymnCatalog:
    if not path.exists():
        return HymnCatalog()
    data = read_yaml(path) or {}
    return HymnCatalog(
        hymns=[
            catalog_hymn(entry)
            for entry in data.get("hymns") or []
            if isinstance(entry, dict) and as_text(entry.get("title"))
        ],
        abbreviations={
            as_text(word): as_text(short) for word, short in (data.get("abbreviations") or {}).items()
        },
    )


def catalog_hymn(entry: dict) -> HymnSuggestion:
    return HymnSuggestion(
        title=as_text(entry.get("title")),
        mode=parse_mode(entry.get("mode")),
        page=page_number(page_label(as_text(entry.get("page")))),
        pages_by_mode={
            mode: page_number(page_label(as_text(page)))
            for key, page in (entry.get("pages_by_mode") or {}).items()
            if (mode := parse_mode(key))
        },
        also=[as_text(name) for name in entry.get("also") or []],
    )


def recent_details(sundays_dir: Path) -> Iterator[ManualData]:
    if not sundays_dir.is_dir():
        return
    recent = sorted((p for p in sundays_dir.iterdir() if p.is_dir()), reverse=True)
    for out_dir in recent[:SUGGESTION_SUNDAYS]:
        if data := read(out_dir):
            yield data


def suggestions(sundays_dir: Path, catalog: HymnCatalog | None = None) -> Suggestions:
    if catalog is None:
        catalog = hymn_catalog()
    known: dict[str, int] = {}
    for index, hymn in enumerate(catalog.hymns):
        for name in (hymn.title, *hymn.also):
            known.setdefault(hymn_key(name, catalog.abbreviations), index)

    used: Counter[int] = Counter()
    others: dict[str, list[ManualHymnData]] = {}
    priests: Counter[str] = Counter()
    for data in recent_details(sundays_dir):
        for hymn in data.dismissal_hymns:
            if not hymn.title or hymn.title == EXAMPLE_HYMN_TITLE:
                continue
            key = hymn_key(hymn.title, catalog.abbreviations)
            if key in known:
                used[known[key]] += 1
            else:
                others.setdefault(key, []).append(hymn)
        for service in data.upcoming_services:
            label = priest_label(service.priest)
            if label and label != UNKNOWN_PRIEST and label not in NO_PRIEST:
                priests[priest_name(label)] += 1

    by_use = sorted(range(len(catalog.hymns)), key=lambda index: -used[index])
    return Suggestions(
        hymns=[
            *(catalog.hymns[index] for index in by_use),
            *(from_history(uses, catalog.abbreviations) for uses in others.values()),
        ],
        priests=[*(name for name, _ in priests.most_common()), READER_SERVICE],
    )


def from_history(uses: list[ManualHymnData], abbreviations: dict[str, str]) -> HymnSuggestion:
    modes = {hymn.mode for hymn in uses}
    pages = {page_number(page_label(hymn.page)) for hymn in uses}
    return HymnSuggestion(
        title=expand_abbreviations(uses[0].title, abbreviations),
        mode=modes.pop() if len(modes) == 1 else None,
        page=pages.pop() if len(pages) == 1 else "",
    )


def hymnal_index(text: str) -> dict[str, list[tuple[str, str]]]:
    sections: dict[str, list[tuple[str, str]]] = {}
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 3 or not all(parts):
            raise ValueError(f"Line {number} isn't “title | page | section”: {line.strip()}")
        title, page, section = parts
        sections.setdefault(section, []).append((title, page))
    return sections
