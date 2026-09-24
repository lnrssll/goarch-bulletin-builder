from datetime import date
from pathlib import Path

import typst

from sunday import build_dir

BOOKLET_PAGES = 2
PREVIEW_PPI = 150


class RenderError(Exception):
    pass


def pdf_path(run_date: date, document: str) -> Path:
    return build_dir(run_date) / f"{document}.pdf"


def previews(run_date: date) -> list[Path]:
    paths = build_dir(run_date).glob("preview-*.png")
    return sorted(paths, key=lambda p: int(p.stem.removeprefix("preview-")))


def inputs(run_date: date) -> list[Path]:
    return [
        *build_dir(run_date).glob("*.yaml"),
        *Path().glob("*.typ"),
        Path("data/layout.yaml"),
        *Path("assets").iterdir(),
    ]


def is_stale(run_date: date) -> bool:
    booklet = pdf_path(run_date, "booklet")
    if not booklet.exists():
        return True
    rendered_at = booklet.stat().st_mtime_ns
    return any(path.stat().st_mtime_ns > rendered_at for path in inputs(run_date))


def compile_document(run_date: date, document: str, **options) -> bytes | list[bytes]:
    try:
        return typst.compile(
            f"{document}.typ",
            root=".",
            sys_inputs={"date": run_date.isoformat()},
            ignore_system_fonts=True,
            **options,
        )
    except typst.TypstError as e:
        hints = [f"hint: {hint}" for hint in getattr(e, "hints", [])]
        raise RenderError("\n".join([str(e), *hints])) from e


def write_atomic(path: Path, content: bytes) -> None:
    partial = path.with_name(path.name + ".partial")
    partial.write_bytes(content)
    partial.replace(path)


def render(run_date: date) -> None:
    pages = compile_document(run_date, "booklet", format="png", ppi=PREVIEW_PPI)
    bulletin = compile_document(run_date, "bulletin")
    booklet = compile_document(run_date, "booklet")

    for old in previews(run_date):
        old.unlink()
    for number, png in enumerate([pages] if isinstance(pages, bytes) else pages, start=1):
        write_atomic(build_dir(run_date) / f"preview-{number}.png", png)
    write_atomic(pdf_path(run_date, "bulletin"), bulletin)
    # last, because its mtime is what marks the render as current
    write_atomic(pdf_path(run_date, "booklet"), booklet)


def ensure_rendered(run_date: date) -> int:
    if is_stale(run_date):
        render(run_date)
    return len(previews(run_date))
