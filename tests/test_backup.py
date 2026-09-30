import io
import zipfile
from datetime import datetime

import backup
import parish


def test_a_backup_holds_what_cant_be_made_again(site):
    day = site / "state" / "sundays" / "2026-09-27"
    day.mkdir(parents=True)
    for name in ("manual.yaml", "feed.yaml", "icon.jpg", "booklet.pdf", "preview-1.png", "feed.yaml.partial"):
        (day / name).write_text(name)
    parish.save({"today": "This Saturday"})
    backup.record_download(datetime(2026, 9, 1))

    with zipfile.ZipFile(io.BytesIO(backup.make_zip())) as archive:
        names = archive.namelist()
        assert archive.read("sundays/2026-09-27/manual.yaml") == b"manual.yaml"
    assert "sundays/2026-09-27/feed.yaml" in names
    assert "sundays/2026-09-27/icon.jpg" in names
    assert "settings/parish.yaml" in names
    assert not [name for name in names if name.endswith((".pdf", ".png", ".partial", "last-backup.txt"))]


def test_the_last_download_is_remembered(site):
    assert backup.last_download() is None
    (site / "state").mkdir()
    backup.record_download(datetime(2026, 9, 30, 12, 0))
    assert backup.last_download() == datetime(2026, 9, 30, 12, 0)
    backup.LAST_DOWNLOAD_PATH.write_text("garbled")
    assert backup.last_download() is None
