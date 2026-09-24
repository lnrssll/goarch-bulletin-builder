from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from classes import ManualData, ManualHymnData, UpcomingServiceData
from yaml_io import read_yaml, write_yaml

FILENAME = "manual.yaml"
HYMNAL_INDEX_PATH = Path("data/table-of-contents.txt")
EXAMPLE_HYMN_TITLE = "Example"
UNKNOWN_PRIEST = "Fr. X"
SERVICE_DATE_FORMAT = "%m/%d/%Y"
MODES = range(1, 9)
LOOKBACK_WEEKS = 8
SUGGESTION_SUNDAYS = 52


@dataclass
class Suggestions:
    hymns: list[ManualHymnData] = field(default_factory=list)
    priests: list[str] = field(default_factory=list)


def service_day(run_date: date) -> date:
    return run_date - timedelta(days=1)


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


def page_label(text: str) -> str:
    return f"p. {text}" if text.isdigit() else text


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


def previous(run_date: date, build_root: Path) -> ManualData | None:
    for weeks in range(1, LOOKBACK_WEEKS + 1):
        data = read(build_root / (run_date - timedelta(weeks=weeks)).isoformat())
        if data:
            return data
    return None


def template(run_date: date, previous: ManualData | None) -> ManualData:
    today = service_day(run_date)
    next_service = service_day(run_date + timedelta(weeks=1))

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
            UpcomingServiceData("Today", priest_today),
            *(later[day] for day in sorted(later)),
        ],
    )


def write_template(run_date: date, out_dir: Path) -> None:
    if (out_dir / FILENAME).exists():
        return
    write(template(run_date, previous(run_date, out_dir.parent)), out_dir)


def unfinished(data: ManualData) -> list[str]:
    notes = []
    if not data.dismissal_hymns:
        notes.append("No Hymns of the Day are listed.")
    if any(hymn.title == EXAMPLE_HYMN_TITLE for hymn in data.dismissal_hymns):
        notes.append(f"The “{EXAMPLE_HYMN_TITLE}” hymn is still listed.")
    if any(service.priest == UNKNOWN_PRIEST for service in data.upcoming_services):
        notes.append(f"An upcoming service still says “{UNKNOWN_PRIEST}”.")
    return notes


def suggestions(build_root: Path) -> Suggestions:
    found = Suggestions()
    if not build_root.is_dir():
        return found

    titles: set[str] = set()
    recent = sorted((p for p in build_root.iterdir() if p.is_dir()), reverse=True)
    for out_dir in recent[:SUGGESTION_SUNDAYS]:
        data = read(out_dir)
        for hymn in data.dismissal_hymns if data else []:
            if hymn.title and hymn.title != EXAMPLE_HYMN_TITLE and hymn.title not in titles:
                titles.add(hymn.title)
                found.hymns.append(hymn)
        for service in data.upcoming_services if data else []:
            if service.priest and service.priest != UNKNOWN_PRIEST and service.priest not in found.priests:
                found.priests.append(service.priest)
    return found


def hymnal_index(path: Path = HYMNAL_INDEX_PATH) -> dict[str, list[tuple[str, str]]]:
    sections: dict[str, list[tuple[str, str]]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        title, page, section = (part.strip() for part in line.split("|"))
        sections.setdefault(section, []).append((title, page))
    return sections
