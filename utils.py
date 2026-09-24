import re
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from lxml import etree
from selectolax.parser import HTMLParser

ARCHIVE_DIR = Path("archive")


def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0))


class ScrapeError(Exception):
    pass


class NotArchived(Exception):
    pass


@dataclass
class SourceArchive:
    root: Path
    client: httpx.AsyncClient | None = None
    refresh: bool = False
    downloaded: dict[Path, bytes] = field(default_factory=dict)

    async def fetch(self, url: str, name: str) -> bytes:
        path = self.root / name
        if path.exists() and not (self.refresh and self.client):
            return path.read_bytes()
        if self.client is None:
            raise NotArchived(f"{path} is not archived ({url})")

        r = await self.client.get(url, follow_redirects=True)
        r.raise_for_status()
        self.downloaded[path] = r.content
        return r.content

    def save(self) -> None:
        # only after the scrape parsed everything, so an error or bot-check page is never archived
        for path, content in self.downloaded.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.downloaded.clear()

    async def fetch_xml(self, url: str, name: str) -> etree._Element:
        parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=True)
        return etree.fromstring(await self.fetch(url, name), parser=parser)

    async def fetch_html(self, url: str, name: str) -> HTMLParser:
        return HTMLParser((await self.fetch(url, name)).decode("utf-8"))


def to_alphanumeric(s: str) -> str:
    return re.sub(r"[^\w\s]", "", s)


def to_alpha(s: str | None) -> str:
    if s is None:
        return ""
    return re.sub(r"[^A-Za-z ]", "", s)


def xpath_text(tree: etree._Element, path: str) -> str:
    matches = tree.xpath(path)
    if not matches:
        raise ScrapeError(f"nothing at {path}")
    return str(matches[0])
