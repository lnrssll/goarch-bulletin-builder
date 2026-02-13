from pathlib import Path
import yaml
from typing import Dict
from selectolax.parser import HTMLParser
from lxml import etree
import httpx
import re
import aiofiles

verbose = True


def to_alphanumeric(s: str) -> str:
    return re.sub(r"[^\w\s]", "", s)


def to_alpha(s: str | None) -> str:
    if s is None:
        return ""
    return re.sub(r"[^A-Za-z ]", "", s)


async def fetch_html(client: httpx.AsyncClient, url: str) -> HTMLParser:
    r = await client.get(url, follow_redirects=True)
    r.raise_for_status()

    return HTMLParser(r.text)


async def fetch_xml(client: httpx.AsyncClient, url: str) -> etree._Element:
    r = await client.get(url, follow_redirects=True)
    r.raise_for_status()

    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=True)

    return etree.fromstring(r.content, parser=parser)


async def download_image(client: httpx.AsyncClient, src: str, out_path: Path) -> None:
    async with client.stream("GET", src, follow_redirects=True) as r:
        r.raise_for_status()
        async with aiofiles.open(out_path, "wb") as f:
            async for chunk in r.aiter_bytes():
                await f.write(chunk)

    return None


async def write_yaml(data: Dict, out_path: Path) -> None:
    async with aiofiles.open(out_path, "w", encoding="utf-8") as f:
        await f.write(yaml.safe_dump(data) + "\n")

    return None
