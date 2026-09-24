import os
import shutil
from datetime import date
from pathlib import Path

import pytest

import manual
import render
from classes import ManualData, ManualHymnData

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOTS = ROOT / "tests" / "snapshots"
SNAPSHOT_DATES = sorted(p.name for p in SNAPSHOTS.iterdir() if p.is_dir())
DAY = date(2026, 9, 27)


def build_from_snapshot(site: Path, iso: str) -> Path:
    out_dir = site / "build" / iso
    shutil.copytree(SNAPSHOTS / iso, out_dir)
    manual.write_template(date.fromisoformat(iso), out_dir)
    return out_dir


@pytest.mark.parametrize("iso", SNAPSHOT_DATES)
def test_archived_sundays_fit_the_booklet(site, iso):
    out_dir = build_from_snapshot(site, iso)
    assert render.ensure_rendered(date.fromisoformat(iso)) == render.BOOKLET_PAGES
    assert (out_dir / "booklet.pdf").read_bytes().startswith(b"%PDF")
    assert (out_dir / "bulletin.pdf").read_bytes().startswith(b"%PDF")


def test_renders_again_only_when_an_input_changes(site):
    out_dir = build_from_snapshot(site, DAY.isoformat())
    render.ensure_rendered(DAY)
    assert not render.is_stale(DAY)

    later = (out_dir / "booklet.pdf").stat().st_mtime_ns + 1_000_000_000
    os.utime(out_dir / manual.FILENAME, ns=(later, later))
    assert render.is_stale(DAY)


def test_a_hymn_without_a_mode_renders(site):
    out_dir = build_from_snapshot(site, DAY.isoformat())
    manual.write(ManualData([ManualHymnData("Ordinary Kontakion", None, "p. 225")], []), out_dir)
    assert render.ensure_rendered(DAY) == render.BOOKLET_PAGES


def test_typst_errors_become_render_errors(site):
    out_dir = build_from_snapshot(site, DAY.isoformat())
    (out_dir / manual.FILENAME).unlink()
    with pytest.raises(render.RenderError, match="manual.yaml"):
        render.render(DAY)
    assert not (out_dir / "booklet.pdf").exists()
