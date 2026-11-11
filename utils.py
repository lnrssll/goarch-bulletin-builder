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
    # error pages, kept apart so that save() can never archive one
    refused: dict[Path, bytes] = field(default_factory=dict)

    async def fetch(self, url: str, name: str) -> bytes:
        path = self.root / name
        if path.exists() and not (self.refresh and self.client):
            return path.read_bytes()
        if self.client is None:
            raise NotArchived(f"{path} is not archived ({url})")

        r = await self.client.get(url, follow_redirects=True)
        if r.is_error:
            self.refused[path] = r.content
        r.raise_for_status()
        self.downloaded[path] = r.content
        return r.content

    def discard(self, name: str) -> None:
        """Don't archive a download that turned out not to be the page asked for."""
        path = self.root / name
        if path in self.downloaded:
            self.refused[path] = self.downloaded.pop(path)

    def save(self) -> None:
        # only after the scrape parsed everything, so an error or bot-check page is never archived
        for path, content in self.downloaded.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.downloaded.clear()

    def save_failed(self, dest: Path) -> list[Path]:
        """Everything this scrape downloaded, error pages included, for a developer to see what changed."""
        saved = []
        for path, content in {**self.downloaded, **self.refused}.items():
            target = dest / path.relative_to(self.root)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            saved.append(target)
        return saved

    async def fetch_xml(self, url: str, name: str) -> etree._Element:
        parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=True)
        content = await self.fetch(url, name)
        try:
            return etree.fromstring(content, parser=parser)
        except etree.XMLSyntaxError as e:
            # recover=True still refuses an empty or all-garbage page
            raise ScrapeError(f"{name} {url}: not XML: {e}") from e

    async def fetch_html(self, url: str, name: str) -> HTMLParser:
        # one stray byte shouldn't lose the whole page
        return HTMLParser((await self.fetch(url, name)).decode("utf-8", "replace"))


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
