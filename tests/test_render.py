import hashlib
import json
import os
import shutil
from datetime import date
from pathlib import Path

import pytest
import typst

import manual
import parish
import render
from classes import ManualData, ManualHymnData

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOTS = ROOT / "tests" / "snapshots"
SNAPSHOT_DATES = sorted(p.name for p in SNAPSHOTS.iterdir() if p.is_dir())
DAY = date(2026, 9, 27)
PREVIEW_HASHES = "previews.sha256"


def build_from_snapshot(site: Path, iso: str) -> Path:
    out_dir = site / "state" / "sundays" / iso
    shutil.copytree(SNAPSHOTS / iso, out_dir, ignore=shutil.ignore_patterns(PREVIEW_HASHES))
    manual.write_template(date.fromisoformat(iso), out_dir)
    return out_dir


@pytest.mark.parametrize("iso", SNAPSHOT_DATES)
def test_archived_sundays_fit_the_booklet(site, iso):
    out_dir = build_from_snapshot(site, iso)
    assert render.ensure_rendered(date.fromisoformat(iso)) == render.BOOKLET_PAGES
    assert (out_dir / "booklet.pdf").read_bytes().startswith(b"%PDF")
    assert (out_dir / "bulletin.pdf").read_bytes().startswith(b"%PDF")


@pytest.mark.parametrize("iso", SNAPSHOT_DATES)
def test_archived_sundays_look_the_same(site, iso, tmp_path_factory):
    """Rendering is deterministic (embedded fonts only), so any change to a picture is a change in print."""
    build_from_snapshot(site, iso)
    render.ensure_rendered(date.fromisoformat(iso))
    rendered = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in render.previews(date.fromisoformat(iso))}
    hashes = SNAPSHOTS / iso / PREVIEW_HASHES
    if os.environ.get("UPDATE_SNAPSHOTS"):
        hashes.write_text("".join(f"{digest}  {name}\n" for name, digest in rendered.items()))

    assert hashes.exists(), f"no picture hashes for {iso}; run with UPDATE_SNAPSHOTS=1"
    expected = dict(reversed(line.split()) for line in hashes.read_text().splitlines())
    changed = [name for name in expected.keys() | rendered.keys() if expected.get(name) != rendered.get(name)]
    if changed:
        saved = tmp_path_factory.mktemp(f"changed-{iso}")
        for name in changed:
            if name in rendered:
                shutil.copy(site / "state" / "sundays" / iso / name, saved / name)
        pytest.fail(
            f"{', '.join(sorted(changed))} for {iso} changed; the new pictures are in {saved}. "
            "If the change is intended, run with UPDATE_SNAPSHOTS=1."
        )


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


def printed_hymn_titles(run_date: date) -> list[str]:
    parish.ensure()
    return json.loads(
        typst.query(
            "bulletin.typ",
            "<hymn-title>",
            field="value",
            root=".",
            sys_inputs={"date": run_date.isoformat()},
            ignore_system_fonts=True,
        )
    )


def test_long_hymn_titles_are_shortened_to_fit(site):
    out_dir = build_from_snapshot(site, DAY.isoformat())
    manual.write(
        ManualData(
            [
                ManualHymnData("Resurrectional Apolytikion", 8, "p. 127"),
                ManualHymnData("Apolytikion of the Sunday of the Myrrh-bearing Women", 2, "p. 159"),
                ManualHymnData("Kontakion of the Holy Great Martyr Demetrios the Myrrh-streamer", 3, "Choir"),
                ManualHymnData("Apolytikion of Martyr Callistratus and Companions", 4, "Choir"),
            ],
            [],
        ),
        out_dir,
    )
    assert printed_hymn_titles(DAY) == [
        "Resurrectional Apolytikion",
        "Myrrh-bearing Women Apol.",
        "Kont. of the Holy Great Martyr Demetrios the Myrrh-streamer",
        "Apolytikion of Martyr Callistratus and Companions",
    ]
    assert render.ensure_rendered(DAY) == render.BOOKLET_PAGES


def test_typst_errors_become_render_errors(site):
    out_dir = build_from_snapshot(site, DAY.isoformat())
    (out_dir / manual.FILENAME).unlink()
    with pytest.raises(render.RenderError, match="manual.yaml"):
        render.render(DAY)
    assert not (out_dir / "booklet.pdf").exists()


TYPST_SPECIAL = "# @ref * $x$ <tag> _under_ \\ `raw` [link] // not a comment"


def test_every_printed_setting_is_plain_text(site):
    build_from_snapshot(site, DAY.isoformat())
    text_settings = [name for name, value in vars(parish.original()).items() if isinstance(value, str)]
    printed = [name for name in text_settings if name not in ("site_name", "liturgy_day", "logo", "hymnal_index")]
    parish.save({name: f"{name} {TYPST_SPECIAL}" for name in printed})
    parish.save({
        "welcome": [TYPST_SPECIAL, "= Not a heading"],
        "contacts": [parish.Contact(name=TYPST_SPECIAL, email="a#b@example.org")],
        "website_lines": [TYPST_SPECIAL],
    })
    assert render.ensure_rendered(DAY) == render.BOOKLET_PAGES


@pytest.mark.parametrize("count", [1, 2])
def test_any_number_of_contacts_renders(site, count):
    build_from_snapshot(site, DAY.isoformat())
    contacts = [parish.Contact(name=f"Fr. Priest {n}", church="Church", city="City, AZ") for n in range(count)]
    parish.save({"contacts": contacts})
    assert render.ensure_rendered(DAY) == render.BOOKLET_PAGES


def test_contacts_leave_out_empty_fields(site):
    build_from_snapshot(site, DAY.isoformat())
    parish.save({"contacts": [parish.Contact(name="Fr. John"), parish.Contact(email="office@example.org")]})
    assert render.ensure_rendered(DAY) == render.BOOKLET_PAGES


def test_no_website_prints_no_qr_code(site):
    build_from_snapshot(site, DAY.isoformat())
    parish.save({"website": "", "website_lines": []})
    assert not parish.QR_PATH.exists()
    assert render.ensure_rendered(DAY) == render.BOOKLET_PAGES


def test_a_new_logo_renders(site):
    build_from_snapshot(site, DAY.isoformat())
    path = parish.store_image((ROOT / "assets" / "lhoc-qr.png").read_bytes())
    render.check_image(path)
    parish.save({"logo": path})
    assert render.ensure_rendered(DAY) == render.BOOKLET_PAGES


def test_an_unreadable_image_is_refused(site):
    path = parish.store_image(b"\x89PNG\r\n\x1a\n" + b"not really a picture")
    with pytest.raises(render.RenderError):
        render.check_image(path)


def test_too_much_welcome_text_overflows(site):
    build_from_snapshot(site, DAY.isoformat())
    parish.save({"welcome": parish.original().welcome * 3})
    assert render.ensure_rendered(DAY) > render.BOOKLET_PAGES


def test_a_settings_change_renders_again(site):
    out_dir = build_from_snapshot(site, DAY.isoformat())
    render.ensure_rendered(DAY)
    later = (out_dir / "booklet.pdf").stat().st_mtime_ns + 1_000_000_000
    parish.save({"today": "This Saturday"})
    os.utime(parish.SETTINGS_PATH, ns=(later, later))
    assert render.is_stale(DAY)
