import os

import pytest

import parish
from yaml_io import read_yaml, write_yaml

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 20


def test_without_changes_the_settings_are_the_defaults(site):
    settings = parish.load()
    assert settings == parish.original()
    assert settings.liturgy_day == parish.SATURDAY
    assert [contact.name for contact in settings.contacts] == ["Rev. Fr. Andrew J. Barakos", "Fr. Timothy Pavlatos"]
    assert "Ordinary Kontakion | 225 | Kontakia" in settings.hymnal_index


def test_only_changes_are_kept(site):
    assert parish.save({"welcome_heading": "Welcome, friends", "services_heading": "Upcoming Services"})
    assert read_yaml(parish.SETTINGS_PATH) == {"welcome_heading": "Welcome, friends"}
    assert parish.load().welcome_heading == "Welcome, friends"
    assert not parish.save({"welcome_heading": "Welcome, friends"})


def test_saving_the_default_again_forgets_the_change(site):
    parish.save({"today": "This Saturday"})
    parish.save({"today": "Today"})
    assert read_yaml(parish.SETTINGS_PATH) == {}


def test_missing_and_unreadable_settings_get_their_defaults(site):
    parish.SETTINGS_DIR.mkdir(parents=True)
    write_yaml(
        {"welcome": "not a list", "contacts": [{"name": "Fr. John", "phone": 5551234}, "junk"],
         "liturgy_day": "monday", "website": None, "today": True},
        parish.SETTINGS_PATH,
    )
    settings = parish.load()
    original = parish.original()
    assert settings.welcome == original.welcome
    assert settings.contacts == [parish.Contact(name="Fr. John", phone="5551234")]
    assert settings.liturgy_day == parish.SATURDAY
    assert settings.website == original.website
    assert settings.today == original.today


def test_an_unreadable_settings_file_is_ignored(site):
    parish.SETTINGS_DIR.mkdir(parents=True)
    parish.SETTINGS_PATH.write_text("- just\n- a list\n")
    assert parish.load() == parish.original()


def test_quotes_are_made_typographic(site):
    parish.save({
        "welcome": ["We're glad you're here. \"Come and see\" ('John 1:46')."],
        "contacts": [parish.Contact(name="Fr. John O'Brien", church="St. Mary's", email="o'brien@example.org")],
    })
    settings = parish.load()
    assert settings.welcome == ["We’re glad you’re here. “Come and see” (‘John 1:46’)."]
    assert settings.contacts == [parish.Contact(name="Fr. John O’Brien", church="St. Mary’s", email="o'brien@example.org")]


def test_put_back_the_original(site):
    parish.save({"welcome_heading": "Hello", "welcome": ["One paragraph."], "today": "Saturday"})
    assert parish.put_back(("welcome_heading", "welcome"))
    assert read_yaml(parish.SETTINGS_PATH) == {"today": "Saturday"}
    assert not parish.put_back(("welcome_heading", "welcome"))


def test_undo_goes_back_one_change_at_a_time(site):
    assert not parish.undo()
    parish.save({"today": "First"})
    parish.save({"today": "Second"})
    assert parish.undo()
    assert parish.load().today == "First"
    assert parish.undo()
    assert parish.load() == parish.original()
    assert not parish.undo()


def test_undo_marks_the_settings_as_changed(site):
    parish.save({"today": "First"})
    os.utime(parish.history()[-1], (0, 0))
    parish.undo()
    assert parish.SETTINGS_PATH.stat().st_mtime > 0


def test_history_is_limited(site, monkeypatch):
    monkeypatch.setattr(parish, "HISTORY_KEPT", 3)
    for n in range(5):
        parish.save({"today": f"Change {n}"})
    assert len(parish.history()) == 3


def test_ensure_makes_what_typst_reads(site):
    parish.ensure()
    assert read_yaml(parish.SETTINGS_PATH) == {}
    svg = parish.QR_PATH.read_bytes()
    assert b"<svg" in svg

    mtime = parish.QR_PATH.stat().st_mtime_ns
    parish.ensure()
    assert parish.QR_PATH.stat().st_mtime_ns == mtime

    parish.save({"website": "example.org"})
    assert parish.QR_PATH.read_bytes() != svg


@pytest.mark.parametrize(
    "content, suffix",
    [(PNG, ".png"), (b"\xff\xd8\xff\xe0" + b"\0" * 20, ".jpg"), (b"RIFF\0\0\0\0WEBPVP8 ", ".webp")],
)
def test_images_are_kept_by_content(site, content, suffix):
    path = parish.store_image(content)
    assert path.startswith("state/settings/images/") and path.endswith(suffix)
    assert parish.store_image(content) == path


@pytest.mark.parametrize("content", [b"", b"GIF89a", b"<svg xmlns='http://www.w3.org/2000/svg'/>", b"%PDF-1.7"])
def test_other_files_are_not_images(site, content):
    with pytest.raises(parish.NotAnImage):
        parish.store_image(content)
