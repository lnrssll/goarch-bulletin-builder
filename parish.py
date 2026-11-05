import hashlib
import io
import re
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import Any

import segno

from yaml_io import read_yaml, write_yaml

DEFAULTS_PATH = Path("data/parish.yaml")
HYMNAL_INDEX_PATH = Path("data/table-of-contents.txt")
SETTINGS_DIR = Path("state/settings")
SETTINGS_PATH = SETTINGS_DIR / "parish.yaml"
HISTORY_DIR = SETTINGS_DIR / "history"
IMAGES_DIR = SETTINGS_DIR / "images"
QR_PATH = SETTINGS_DIR / "qr.svg"
HISTORY_KEPT = 50
# the head priests of the two churches whose priests serve the mission
CONTACTS = 2
SATURDAY = "saturday"
SUNDAY = "sunday"
LITURGY_DAYS = (SATURDAY, SUNDAY)
# printed prose, whose quotes are made typographic on save
PROSE = {
    "welcome_heading", "welcome", "commemorate", "hymns_heading", "reading_heading",
    "prokeimenon_heading", "verse_label", "alleluia_heading", "services_heading", "today",
    "contacts_heading",
}
CONTACT_PROSE = ("name", "church", "city")


@dataclass
class Contact:
    name: str = ""
    church: str = ""
    city: str = ""
    email: str = ""
    phone: str = ""


@dataclass
class Settings:
    site_name: str = ""
    liturgy_day: str = SATURDAY
    welcome_heading: str = ""
    welcome: list[str] = field(default_factory=list)
    contacts: list[Contact] = field(default_factory=list)
    website: str = ""
    website_lines: list[str] = field(default_factory=list)
    calendar: str = ""
    logo: str = ""
    commemorate: str = ""
    hymns_heading: str = ""
    reading_heading: str = ""
    prokeimenon_heading: str = ""
    verse_label: str = ""
    alleluia_heading: str = ""
    services_heading: str = ""
    today: str = ""
    contacts_heading: str = ""
    hymnal_index: str = ""


class NotAnImage(Exception):
    pass


################################################################################
# reading
################################################################################


def defaults() -> dict[str, Any]:
    data = read_yaml(DEFAULTS_PATH) or {}
    data["hymnal_index"] = tidy_lines(HYMNAL_INDEX_PATH.read_text(encoding="utf-8"))
    return data


def changes() -> dict[str, Any]:
    if not SETTINGS_PATH.exists():
        return {}
    data = read_yaml(SETTINGS_PATH)
    return data if isinstance(data, dict) else {}


def load() -> Settings:
    return parse(defaults(), changes())


def original() -> Settings:
    return parse(defaults(), {})


def parse(defaults: dict[str, Any], changes: dict[str, Any]) -> Settings:
    """Each setting from the church's changes, or the default when it's missing or unreadable."""
    values = {}
    for setting in fields(Settings):
        for source in (changes, defaults):
            value = convert(setting.type, source.get(setting.name))
            if value is not None:
                values[setting.name] = value
                break
    settings = Settings(**values)
    if settings.liturgy_day not in LITURGY_DAYS:
        settings.liturgy_day = SATURDAY
    return settings


def convert(kind: Any, value: Any) -> Any:
    if kind is str:
        return text(value)
    if kind == list[str] and isinstance(value, list):
        return [line for item in value if (line := text(item))]
    if kind == list[Contact] and isinstance(value, list):
        names = [setting.name for setting in fields(Contact)]
        return [
            Contact(**{name: text(item.get(name)) or "" for name in names})
            for item in value
            if isinstance(item, dict)
        ]
    return None


def text(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    return str(value).strip()


################################################################################
# saving, undo and putting back the original
################################################################################


def save(updates: dict[str, Any]) -> bool:
    """Saves settings, keeping only what differs from the defaults; False when nothing changed."""
    base = defaults()
    current = changes()
    for name, value in updates.items():
        plain = as_yaml(name, value)
        if plain == base.get(name):
            current.pop(name, None)
        else:
            current[name] = plain
    if current == changes():
        return False
    remember()
    write(current)
    return True


def put_back(names: tuple[str, ...]) -> bool:
    base = defaults()
    return save({name: base[name] for name in names if name in base})


def as_yaml(name: str, value: Any) -> Any:
    if name == "hymnal_index":
        return tidy_lines(value)
    if isinstance(value, list):
        value = [asdict(item) if isinstance(item, Contact) else item for item in value]
    if name in PROSE:
        value = [typographic(item) for item in value] if isinstance(value, list) else typographic(value)
    if name == "contacts":
        value = [
            {key: typographic(field) if key in CONTACT_PROSE else field for key, field in contact.items()}
            for contact in value
        ]
    return value


def tidy_lines(text: str) -> str:
    return "\n".join(line.strip() for line in text.strip().splitlines()) + "\n"


def typographic(text: str) -> str:
    text = re.sub(r"(^|[\s(\[{])'", "\\1‘", text).replace("'", "’")
    return re.sub(r'(^|[\s(\[{])"', "\\1“", text).replace('"', "”")


def remember() -> None:
    saved = SETTINGS_PATH.read_bytes() if SETTINGS_PATH.exists() else b"{}\n"
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    (HISTORY_DIR / f"{stamp}.yaml").write_bytes(saved)
    for old in history()[:-HISTORY_KEPT]:
        old.unlink()


def history() -> list[Path]:
    return sorted(HISTORY_DIR.glob("*.yaml")) if HISTORY_DIR.is_dir() else []


def last_changed() -> datetime | None:
    saved = history()
    return datetime.fromtimestamp(saved[-1].stat().st_mtime) if saved else None


def undo() -> bool:
    saved = history()
    if not saved:
        return False
    # written anew rather than renamed, so its mtime tells render.py the Sundays are out of date
    write_if_changed(SETTINGS_PATH, saved[-1].read_bytes())
    saved[-1].unlink()
    ensure()
    return True


def write(data: dict[str, Any]) -> None:
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    write_yaml(data, SETTINGS_PATH)
    ensure()


################################################################################
# files the bulletin reads
################################################################################


def ensure() -> None:
    """Makes the files Typst reads under state/settings/, before anything renders.

    Typst can't check whether a file exists, so the church's settings file is
    written even when empty, and the QR code is kept in step with the website.
    """
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    if not SETTINGS_PATH.exists():
        write_yaml({}, SETTINGS_PATH)
    website = load().website
    if website:
        write_if_changed(QR_PATH, qr_svg(website))


def qr_svg(address: str) -> bytes:
    svg = io.BytesIO()
    segno.make(address, micro=False).save(svg, kind="svg", border=4)
    return svg.getvalue()


def write_if_changed(path: Path, content: bytes) -> None:
    # an unchanged file keeps its mtime, so the Sundays aren't all rendered again
    if path.exists() and path.read_bytes() == content:
        return
    partial = path.with_name(path.name + ".partial")
    partial.write_bytes(content)
    partial.replace(path)


def image_suffix(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def store_image(data: bytes) -> str:
    """Keeps an uploaded image under a name from its contents, so earlier settings can still refer to theirs."""
    suffix = image_suffix(data)
    if suffix is None:
        raise NotAnImage
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    path = IMAGES_DIR / f"{hashlib.sha256(data).hexdigest()[:16]}{suffix}"
    write_if_changed(path, data)
    return path.as_posix()
