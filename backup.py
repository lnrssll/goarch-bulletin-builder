import io
import zipfile
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

STATE_DIR = Path("state")
LAST_DOWNLOAD_PATH = STATE_DIR / "last-backup.txt"
# made again from the rest whenever a Sunday is opened
GENERATED = ("*.pdf", "preview-*.png", "*.partial")


def files(state_dir: Path = STATE_DIR) -> Iterator[Path]:
    for path in sorted(state_dir.rglob("*")):
        if path.is_file() and path != LAST_DOWNLOAD_PATH and not any(path.match(p) for p in GENERATED):
            yield path


def make_zip(state_dir: Path = STATE_DIR) -> bytes:
    """Everything typed in or downloaded, as it sits under state/: unzip it into state/ to restore."""
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files(state_dir):
            archive.write(path, path.relative_to(state_dir).as_posix())
    return content.getvalue()


def filename(today: date) -> str:
    return f"bulletin-backup-{today.isoformat()}.zip"


def record_download(when: datetime) -> None:
    LAST_DOWNLOAD_PATH.write_text(when.isoformat(timespec="seconds") + "\n", encoding="utf-8")


def last_download() -> datetime | None:
    try:
        return datetime.fromisoformat(LAST_DOWNLOAD_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
