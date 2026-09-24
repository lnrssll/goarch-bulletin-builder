import asyncio

import httpx
import pytest

from utils import NotArchived, SourceArchive

URL = "https://example.org/page"


def client(body: bytes, calls: list[str]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, content=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def fetch(archive: SourceArchive) -> bytes:
    return asyncio.run(archive.fetch(URL, "page.xml"))


def test_downloads_are_written_only_on_save(tmp_path):
    calls: list[str] = []
    archive = SourceArchive(tmp_path, client(b"new", calls))

    assert fetch(archive) == b"new"
    assert not (tmp_path / "page.xml").exists()

    archive.save()
    assert (tmp_path / "page.xml").read_bytes() == b"new"


def test_archived_source_is_not_downloaded_again(tmp_path):
    (tmp_path / "page.xml").write_bytes(b"old")
    calls: list[str] = []

    assert fetch(SourceArchive(tmp_path, client(b"new", calls))) == b"old"
    assert calls == []


def test_refresh_downloads_again(tmp_path):
    (tmp_path / "page.xml").write_bytes(b"old")
    calls: list[str] = []

    assert fetch(SourceArchive(tmp_path, client(b"new", calls), refresh=True)) == b"new"
    assert calls == [URL]


def test_offline_archive_raises_for_missing_source(tmp_path):
    with pytest.raises(NotArchived):
        fetch(SourceArchive(tmp_path))
