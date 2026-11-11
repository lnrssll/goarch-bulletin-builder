from datetime import date
from pathlib import Path

import typst

import parish
from sunday import sunday_dir

BOOKLET_PAGES = 2
PREVIEW_PPI = 150


class RenderError(Exception):
    pass


def pdf_path(run_date: date, document: str) -> Path:
    return sunday_dir(run_date) / f"{document}.pdf"


def previews(run_date: date) -> list[Path]:
    paths = sunday_dir(run_date).glob("preview-*.png")
    return sorted(paths, key=lambda p: int(p.stem.removeprefix("preview-")))


def inputs(run_date: date) -> list[Path]:
    return [
        *sunday_dir(run_date).glob("*.yaml"),
        *Path().glob("*.typ"),
        Path("data/layout.yaml"),
        Path("data/hymns.yaml"),
        parish.DEFAULTS_PATH,
        *Path("assets").iterdir(),
        *(path for path in parish.SETTINGS_DIR.iterdir() if path.is_file()),
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
    parish.ensure()
    pages = compile_document(run_date, "booklet", format="png", ppi=PREVIEW_PPI)
    bulletin = compile_document(run_date, "bulletin")
    booklet = compile_document(run_date, "booklet")

    pngs = [pages] if isinstance(pages, bytes) else pages
    # replaced in place, so a picture asked for meanwhile (served without WORK_LOCK) is never missing
    for number, png in enumerate(pngs, start=1):
        write_atomic(sunday_dir(run_date) / f"preview-{number}.png", png)
    for old in previews(run_date)[len(pngs):]:
        old.unlink()
    write_atomic(pdf_path(run_date, "bulletin"), bulletin)
    # last, because its mtime is what marks the render as current
    write_atomic(pdf_path(run_date, "booklet"), booklet)


def ensure_rendered(run_date: date) -> int:
    parish.ensure()
    if is_stale(run_date):
        render(run_date)
    return len(previews(run_date))


def check_image(path: str) -> None:
    compile_bytes(f'#image("/{path}")'.encode())


def compile_bytes(source: bytes) -> None:
    try:
        typst.compile(source, root=".", ignore_system_fonts=True)
    except typst.TypstError as e:
        raise RenderError(str(e)) from e
