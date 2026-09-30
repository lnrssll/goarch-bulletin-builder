import argparse
import asyncio
import base64
import email.policy
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date
from email.parser import BytesParser
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, quote

import httpx
import jinja2
import waitress

import manual
import parish
import render
import sunday
from classes import ManualData, ManualHymnData, UpcomingServiceData
from yaml_io import read_yaml

STATIC_DIR = Path("static")
TEMPLATE_DIR = Path("templates")
MAX_BODY_BYTES = 1_000_000
# a logo of up to 5 MB, and the rest of its form
MAX_UPLOAD_BYTES = 5_100_000
UPLOAD_PATHS = ("/settings/logo",)
SESSION_COOKIE = "bulletin_session"
FLASH_COOKIE = "bulletin_flash"
SESSION_SECONDS = 30 * 24 * 60 * 60
FLASH_SECONDS = 60
FLASH_DETAIL_CHARS = 1000
FAILED_LOGIN_DELAY_S = 1.0
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
MIN_HYMN_ROWS = 5
MIN_SERVICE_ROWS = 4
RECENT_SUNDAYS = 12
STATIC_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
}
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}
HTML_HEADERS = [
    ("Content-Type", "text/html; charset=utf-8"),
    (
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; form-action 'self'; "
        "frame-ancestors 'none'; base-uri 'none'",
    ),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "same-origin"),
    ("Cache-Control", "no-store"),
]
LAYOUT_DESCRIPTIONS = {
    "split_before_alleluia": "Epistle on page 2; Alleluia and Gospel on page 3",
    "split_before_gospel": "Epistle and Alleluia on page 2; Gospel on page 3",
    "flow": "the readings run straight on from page 2 to page 3",
}

# scrapes, saves and renders all rewrite files under state/, so they take turns
WORK_LOCK = threading.Lock()

templates = jinja2.Environment(
    loader=jinja2.FileSystemLoader(TEMPLATE_DIR),
    autoescape=True,
    undefined=jinja2.StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)
templates.filters["long_date"] = lambda day: f"{day:%A}, {sunday.long_date(day)}"
templates.filters["paragraphs"] = "\n\n".join
templates.filters["sunday_url"] = lambda day: sunday_url(day)


class NotFound(Exception):
    pass


class BodyTooLarge(Exception):
    pass


@dataclass
class Flash:
    kind: str  # ok, warning or error
    message: str
    detail: str = ""


@dataclass
class Request:
    app: "App"
    method: str
    path: str
    query: dict[str, list[str]]
    form: dict[str, list[str]]
    files: dict[str, bytes]
    cookies: dict[str, str]
    https: bool

    def arg(self, name: str) -> str:
        return self.query.get(name, [""])[0]

    def field(self, name: str) -> str:
        return self.form.get(name, [""])[0].strip()

    def fields(self, name: str) -> list[str]:
        return [value.strip() for value in self.form.get(name, [])]


@dataclass
class Response:
    body: bytes = b""
    status: int = 200
    headers: list[tuple[str, str]] = field(default_factory=list)

    def set_cookie(self, req: Request, name: str, value: str, max_age: int) -> "Response":
        secure = "; Secure" if req.https else ""
        self.headers.append(
            ("Set-Cookie", f"{name}={value}; Max-Age={max_age}; Path=/; HttpOnly; SameSite=Lax{secure}")
        )
        return self


@dataclass
class SundaySummary:
    day: date
    title: str
    status: str

    @property
    def url(self) -> str:
        return sunday_url(self.day)


@dataclass(frozen=True)
class Section:
    slug: str
    title: str
    about: str
    settings: tuple[str, ...]
    # how many sides of the booklet the page shows, to check a change
    sides: int = 1
    advanced: bool = False

    @property
    def url(self) -> str:
        return f"/settings/{self.slug}"


@dataclass
class Preview:
    day: date | None = None
    sides: list[str] = field(default_factory=list)
    pages: int = 0
    error: str = ""


WORDING = {
    "site_name": "Name at the top of these pages (not printed)",
    "commemorate": "Front page, before the commemoration",
    "hymns_heading": "Front page, above the hymns",
    "prokeimenon_heading": "Above the prokeimenon",
    "verse_label": "Before the prokeimenon's verse",
    "reading_heading": "Before the book of each reading",
    "alleluia_heading": "Above the Alleluia",
    "services_heading": "Back page, above the upcoming services",
    "today": "Upcoming services, in place of the date of this week's service",
    "contacts_heading": "Back page, above the contacts",
}
SECTIONS = (
    Section(
        "welcome", "Welcome text", "The heading and paragraphs at the top of the back page.",
        ("welcome_heading", "welcome"),
    ),
    Section(
        "contacts", "Contact information", "The head priests of the two churches whose priests serve the mission, on the back page.",
        ("contacts",),
    ),
    Section(
        "website", "Website and QR code", "The address the QR code opens, and how it's printed next to it.",
        ("website", "website_lines"),
    ),
    Section(
        "logo", "Logo", "The picture at the top of the front page and at the bottom of the back page.",
        ("logo",),
    ),
    Section(
        "liturgy-day", "When the Liturgy is served", "On the Saturday before each Sunday, or on the Sunday itself.",
        ("liturgy_day",), sides=0,
    ),
    Section(
        "wording", "Headings and wording", "The headings printed in every bulletin, and the name at the top of these pages.",
        tuple(WORDING), sides=2, advanced=True,
    ),
    Section(
        "hymnal", "Hymnal page numbers", "The list under “Page numbers in the hymnal”, for a new edition of the hymnal.",
        ("hymnal_index",), sides=0, advanced=True,
    ),
)
LITURGY_DAY_CHOICES = {
    parish.SATURDAY: "On the Saturday before each Sunday, with the Sunday's hymns and readings",
    parish.SUNDAY: "On the Sunday itself",
}
MAX_WEBSITE_CHARS = 300


################################################################################
# requests and responses
################################################################################


def parse_request(app: "App", environ: dict) -> Request:
    method = environ["REQUEST_METHOD"]
    path = environ.get("PATH_INFO") or "/"
    form: dict[str, list[str]] = {}
    files: dict[str, bytes] = {}
    if method == "POST":
        length = int(environ.get("CONTENT_LENGTH") or 0)
        if length > (MAX_UPLOAD_BYTES if path in UPLOAD_PATHS else MAX_BODY_BYTES):
            raise BodyTooLarge
        body = environ["wsgi.input"].read(length)
        content_type = environ.get("CONTENT_TYPE", "")
        if content_type.startswith("multipart/form-data"):
            form, files = parse_multipart(content_type, body)
        else:
            form = parse_qs(body.decode("latin-1"), keep_blank_values=True)

    try:
        cookie = SimpleCookie(environ.get("HTTP_COOKIE", ""))
    except CookieError:
        cookie = SimpleCookie()
    return Request(
        app=app,
        method="GET" if method == "HEAD" else method,
        path=path,
        query=parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True),
        form=form,
        files=files,
        cookies={name: morsel.value for name, morsel in cookie.items()},
        https=environ.get("wsgi.url_scheme") == "https",
    )


def parse_multipart(content_type: str, body: bytes) -> tuple[dict[str, list[str]], dict[str, bytes]]:
    # the email parser reads multipart/form-data too, now that the cgi module is gone
    message = BytesParser(policy=email.policy.HTTP).parsebytes(
        f"Content-Type: {content_type}\r\n\r\n".encode("latin-1") + body
    )
    form: dict[str, list[str]] = {}
    files: dict[str, bytes] = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        content = part.get_payload(decode=True) or b""
        if not isinstance(name, str):
            continue
        if part.get_filename() is not None:
            files[name] = content
        else:
            form.setdefault(name, []).append(content.decode("utf-8", "replace"))
    return form, files


def encode_flash(flash: Flash) -> str:
    raw = json.dumps([flash.kind, flash.message, flash.detail[:FLASH_DETAIL_CHARS]])
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_flash(value: str) -> Flash | None:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        kind, message, detail = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return Flash(kind, message, detail)


def page(req: Request, template: str, status: int = 200, **context) -> Response:
    flash = decode_flash(req.cookies.get(FLASH_COOKIE, ""))
    html = templates.get_template(template).render(
        flash=flash, show_logout=bool(req.app.password), parish=parish.load(), **context
    )
    response = Response(html.encode(), status, list(HTML_HEADERS))
    if FLASH_COOKIE in req.cookies:
        response.set_cookie(req, FLASH_COOKIE, "", 0)
    return response


def redirect(req: Request, location: str, flash: Flash | None = None) -> Response:
    response = Response(status=303, headers=[("Location", location)])
    if flash:
        response.set_cookie(req, FLASH_COOKIE, encode_flash(flash), FLASH_SECONDS)
    return response


def plain(status: int, message: str) -> Response:
    return Response(message.encode(), status, [("Content-Type", "text/plain; charset=utf-8")])


def not_found(req: Request) -> Response:
    return page(req, "error.html", 404, heading="Page not found", message="There's nothing at this address.")


def safe_next(target: str) -> str:
    # a plain local path only: browsers drop tabs and newlines, so "/\t/x.org" would become "//x.org"
    return target if re.fullmatch(r"(/[\w.-]+)*/?", target) else "/"


################################################################################
# helpers for the Sunday pages
################################################################################


def sunday_url(day: date) -> str:
    return f"/sundays/{day.isoformat()}"


def parse_sunday(iso: str) -> date:
    try:
        day = date.fromisoformat(iso)
    except ValueError:
        raise NotFound from None
    if day.weekday() != sunday.SUNDAY:
        raise NotFound
    return day


def summarize(day: date) -> SundaySummary:
    out_dir = sunday.sunday_dir(day)
    feed_path = out_dir / "feed.yaml"
    feed = read_yaml(feed_path) if feed_path.exists() else None
    title = (feed or {}).get("lectionary_title") or ""
    details = manual.read(out_dir)

    if not out_dir.exists():
        status = "Not started"
    elif not sunday.has_readings(out_dir):
        status = "Readings missing"
    elif details is None or manual.unfinished(details):
        status = "Hymns and services to fill in"
    else:
        status = "Ready"
    return SundaySummary(day, title, status)


def padded[T](rows: list[T], minimum: int, blank: Callable[[], T]) -> list[T]:
    return rows + [blank() for _ in range(max(len(rows) + 2, minimum) - len(rows))]


def lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def paragraphs(text: str) -> list[str]:
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n"))
    return [" ".join(block.split()) for block in blocks if block.strip()]


def explain(error: Exception) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        code = error.response.status_code
        if code == 404:
            return "goarch.org has no page for this Sunday yet"
        if code in (403, 429, 503):
            return (
                "goarch.org refused the download (it sometimes blocks automated "
                "downloads for a while, so try again later)"
            )
        return f"goarch.org answered with error {code}"
    if isinstance(error, httpx.TimeoutException):
        return "goarch.org took too long to answer"
    if isinstance(error, httpx.HTTPError):
        return "couldn't connect to goarch.org"
    return (
        "the page didn't have the expected content (it may have been a temporary "
        "block page, or the website has changed)"
    )


def fetch_flash(result: sunday.FetchResult) -> Flash:
    if not result.failures:
        return Flash("ok", "Readings downloaded from goarch.org.")

    detail = "\n".join(f"{source.name}: {error!r}" for source, error in result.failures.items())
    if len(result.failures) == len(sunday.SOURCES):
        reasons = "; ".join(sorted({explain(error) for error in result.failures.values()}))
        return Flash("error", f"Couldn't download the readings: {reasons}. Nothing was changed.", detail)

    source, error = next(iter(result.failures.items()))
    return Flash(
        "warning",
        f"Couldn't download {source.provides}: {explain(error)}. The rest was downloaded, "
        "and you can type in the missing part yourself.",
        detail,
    )


################################################################################
# handlers
################################################################################


def home(req: Request) -> Response:
    upcoming = sunday.next_sunday(date.today())
    others = [day for day in sunday.saved_dates() if day != upcoming][:RECENT_SUNDAYS]
    return page(req, "home.html", upcoming=summarize(upcoming), sundays=[summarize(day) for day in others])


def open_sunday(req: Request) -> Response:
    try:
        day = date.fromisoformat(req.arg("date"))
    except ValueError:
        return redirect(req, "/", Flash("error", "Pick a date first."))
    return redirect(req, sunday_url(sunday.sunday_on_or_after(day)))


def sunday_page(req: Request, iso: str) -> Response:
    try:
        day = date.fromisoformat(iso)
    except ValueError:
        raise NotFound from None
    if day.weekday() != sunday.SUNDAY:
        return redirect(req, sunday_url(sunday.sunday_on_or_after(day)))

    out_dir = sunday.sunday_dir(day)
    missing = sunday.missing_sources(out_dir)
    details = manual.read(out_dir)

    pages = 0
    render_error = ""
    if not missing and details:
        try:
            with WORK_LOCK:
                pages = render.ensure_rendered(day)
        except render.RenderError as e:
            render_error = str(e)

    feed = read_yaml(out_dir / "feed.yaml") if not missing else {}
    version = render.pdf_path(day, "booklet").stat().st_mtime_ns if pages else 0
    previews = [f"{sunday_url(day)}/preview-{n}.png?v={version}" for n in range(1, pages + 1)]
    settings = parish.load()
    shown = details or manual.template(day, manual.previous(day, sunday.SUNDAYS_DIR), settings)

    return page(
        req,
        "sunday.html",
        day=day,
        url=sunday_url(day),
        service_day=manual.service_day(day, settings.liturgy_day),
        readings=sunday.load_readings(day, out_dir),
        missing=missing,
        nothing_fetched=len(missing) == len(sunday.SOURCES),
        font_size_pt=feed.get("font_size_pt"),
        layout=LAYOUT_DESCRIPTIONS.get(feed.get("layout"), ""),
        details_saved=details is not None,
        unfinished=manual.unfinished(details) if details else [],
        hymn_rows=padded(
            [replace(hymn, page=manual.page_number(hymn.page)) for hymn in shown.dismissal_hymns],
            MIN_HYMN_ROWS,
            ManualHymnData,
        ),
        service_rows=padded(
            [replace(service, priest=manual.priest_name(service.priest)) for service in shown.upcoming_services],
            MIN_SERVICE_ROWS,
            UpcomingServiceData,
        ),
        modes=manual.MODES,
        no_priest=manual.NO_PRIEST,
        suggestions=manual.suggestions(sunday.SUNDAYS_DIR),
        hymnal=manual.hymnal_index(settings.hymnal_index),
        render_error=render_error,
        pages=pages,
        expected_pages=render.BOOKLET_PAGES,
        previews=previews,
    )


def fetch(req: Request, iso: str) -> Response:
    day = parse_sunday(iso)
    with WORK_LOCK:
        result = asyncio.run(sunday.download_readings(day, refresh=req.field("refresh") == "yes"))
    return redirect(req, sunday_url(day), fetch_flash(result))


def save_details(req: Request, iso: str) -> Response:
    day = parse_sunday(iso)
    abbreviations = manual.hymn_catalog().abbreviations
    hymns = [
        ManualHymnData(
            title=manual.expand_abbreviations(title, abbreviations),
            mode=manual.parse_mode(mode),
            page=manual.page_label(page),
        )
        for title, mode, page in zip(
            req.fields("hymn_title"), req.fields("hymn_mode"), req.fields("hymn_page")
        )
        if title
    ]
    services = [
        UpcomingServiceData(date=when, priest=priest)
        for when, priest in zip(
            req.fields("service_date"), map(manual.priest_label, req.fields("service_priest"))
        )
        if when or priest
    ]
    with WORK_LOCK:
        manual.write(ManualData(hymns, services), sunday.sunday_dir(day))
    return redirect(req, sunday_url(day), Flash("ok", "Hymns and services saved."))


def readings_form(req: Request, iso: str) -> Response:
    day = parse_sunday(iso)
    return page(
        req,
        "readings.html",
        day=day,
        url=sunday_url(day),
        readings=sunday.load_readings(day, sunday.sunday_dir(day)),
    )


def save_readings(req: Request, iso: str) -> Response:
    day = parse_sunday(iso)
    readings = sunday.Readings(
        lectionary_title=req.field("lectionary_title"),
        formatted_date=req.field("formatted_date"),
        icon_title=req.field("icon_title"),
        epistle_book=req.field("epistle_book"),
        epistle_chapverse=req.field("epistle_chapverse"),
        prokeimenon=req.field("prokeimenon"),
        verse=req.field("verse"),
        epistle_text=paragraphs(req.field("epistle_text")),
        alleluia=paragraphs(req.field("alleluia")),
        gospel_book=req.field("gospel_book"),
        gospel_chapverse=req.field("gospel_chapverse"),
        gospel_text=paragraphs(req.field("gospel_text")),
    )
    with WORK_LOCK:
        sunday.save_readings(day, sunday.sunday_dir(day), readings)
    return redirect(req, sunday_url(day), Flash("ok", "Readings saved."))


def pdf(req: Request, iso: str, document: str) -> Response:
    day = parse_sunday(iso)
    out_dir = sunday.sunday_dir(day)
    if not sunday.has_readings(out_dir) or not (out_dir / manual.FILENAME).exists():
        raise NotFound
    try:
        with WORK_LOCK:
            render.ensure_rendered(day)
    except render.RenderError as e:
        return plain(500, f"The PDF couldn't be made:\n\n{e}")

    disposition = "attachment" if req.arg("download") else "inline"
    return Response(
        render.pdf_path(day, document).read_bytes(),
        headers=[
            ("Content-Type", "application/pdf"),
            ("Content-Disposition", f'{disposition}; filename="{day.isoformat()}-{document}.pdf"'),
            ("Cache-Control", "no-store"),
        ],
    )


def preview(req: Request, iso: str, number: str) -> Response:
    path = sunday.sunday_dir(parse_sunday(iso)) / f"preview-{int(number)}.png"
    if not path.is_file():
        raise NotFound
    return Response(
        path.read_bytes(),
        headers=[("Content-Type", "image/png"), ("Cache-Control", "no-store")],
    )


def static(req: Request, name: str) -> Response:
    path = STATIC_DIR / name
    if path.suffix not in STATIC_TYPES or not path.is_file():
        raise NotFound
    return Response(
        path.read_bytes(),
        headers=[("Content-Type", STATIC_TYPES[path.suffix]), ("Cache-Control", "no-cache")],
    )


class Invalid(Exception):
    pass


def find_section(slug: str) -> Section:
    for section in SECTIONS:
        if section.slug == slug:
            return section
    raise NotFound


def settings_preview(sides: int) -> Preview:
    """The booklet for the next Sunday, or else the latest one that can be printed."""
    if sides == 0:
        return Preview()
    for day in [sunday.next_sunday(date.today()), *sunday.saved_dates()]:
        out_dir = sunday.sunday_dir(day)
        if sunday.has_readings(out_dir) and (out_dir / manual.FILENAME).exists():
            break
    else:
        return Preview()
    try:
        with WORK_LOCK:
            pages = render.ensure_rendered(day)
    except render.RenderError as e:
        return Preview(day, error=str(e))
    version = render.pdf_path(day, "booklet").stat().st_mtime_ns
    return Preview(
        day, [f"{sunday_url(day)}/preview-{n}.png?v={version}" for n in range(1, min(sides, pages) + 1)], pages
    )


def settings_home(req: Request) -> Response:
    return page(
        req,
        "settings.html",
        sections=SECTIONS,
        can_undo=bool(parish.history()),
        last_changed=parish.last_changed(),
    )


def settings_form(
    req: Request, slug: str, shown: parish.Settings | None = None, error: str = "", status: int = 200
) -> Response:
    section = find_section(slug)
    current = parish.load()
    original = parish.original()
    shown = shown or current
    return page(
        req,
        "settings_section.html",
        status,
        section=section,
        settings=shown,
        original=original,
        changed=any(getattr(current, name) != getattr(original, name) for name in section.settings),
        error=error,
        contact_rows=(shown.contacts + [parish.Contact()] * parish.CONTACTS)[: parish.CONTACTS],
        wording=WORDING,
        liturgy_days=LITURGY_DAY_CHOICES,
        preview=settings_preview(section.sides),
        expected_pages=render.BOOKLET_PAGES,
        can_undo=bool(parish.history()),
    )


def read_welcome(req: Request) -> dict:
    heading = req.field("welcome_heading")
    updates = {"welcome_heading": heading, "welcome": paragraphs(req.field("welcome"))}
    if not heading:
        raise Invalid("The heading can't be empty.", updates)
    return updates


def read_contacts(req: Request) -> dict:
    rows = [
        parish.Contact(*values)
        for values in zip(
            req.fields("contact_name"), req.fields("contact_church"), req.fields("contact_city"),
            req.fields("contact_email"), req.fields("contact_phone"),
        )
    ]
    return {"contacts": [contact for contact in rows[: parish.CONTACTS] if any(vars(contact).values())]}


def read_website(req: Request) -> dict:
    website = req.field("website")
    updates = {"website": website, "website_lines": lines(req.field("website_lines"))}
    if len(website) > MAX_WEBSITE_CHARS or any(char.isspace() for char in website):
        raise Invalid("The website address should be one short address with no spaces, like example.org.", updates)
    return updates


def read_liturgy_day(req: Request) -> dict:
    day = req.field("liturgy_day")
    if day not in LITURGY_DAY_CHOICES:
        raise Invalid("Choose when the Liturgy is served.", {})
    return {"liturgy_day": day}


def read_wording(req: Request) -> dict:
    updates = {name: req.field(name) for name in WORDING}
    for name, label in WORDING.items():
        if not updates[name]:
            raise Invalid(f"“{label}” can't be empty. To go back to the original, use “Put back the original”.", updates)
    return updates


def read_hymnal(req: Request) -> dict:
    index = req.field("hymnal_index")
    updates = {"hymnal_index": index}
    try:
        if not manual.hymnal_index(index):
            raise Invalid("The list can't be empty.", updates)
    except ValueError as e:
        raise Invalid(str(e), updates) from None
    return updates


def read_logo(req: Request) -> dict:
    content = req.files.get("logo", b"")
    if not content:
        raise Invalid("Choose a picture first.", {})
    try:
        path = parish.store_image(content)
    except parish.NotAnImage:
        raise Invalid("That file isn't a PNG, JPEG or WebP picture.", {}) from None
    try:
        render.check_image(path)
    except render.RenderError as e:
        if path != parish.load().logo:
            Path(path).unlink()
        raise Invalid(f"That picture couldn't be read, so the logo wasn't changed. ({e})", {}) from None
    return {"logo": path}


SETTINGS_READERS: dict[str, Callable[[Request], dict]] = {
    "welcome": read_welcome,
    "contacts": read_contacts,
    "website": read_website,
    "logo": read_logo,
    "liturgy-day": read_liturgy_day,
    "wording": read_wording,
    "hymnal": read_hymnal,
}


def save_settings(req: Request, slug: str) -> Response:
    section = find_section(slug)
    try:
        updates = SETTINGS_READERS[slug](req)
    except Invalid as e:
        message, updates = e.args
        return settings_form(req, slug, replace(parish.load(), **updates), message, 400)
    with WORK_LOCK:
        changed = parish.save(updates)
    if not changed:
        return redirect(req, section.url, Flash("ok", "Nothing was changed."))
    checked = " Check the picture of the booklet below." if section.sides else ""
    return redirect(req, section.url, Flash("ok", f"Saved.{checked}"))


def put_back_settings(req: Request, slug: str) -> Response:
    section = find_section(slug)
    with WORK_LOCK:
        changed = parish.put_back(section.settings)
    if not changed:
        return redirect(req, section.url, Flash("ok", "This is already the original."))
    return redirect(
        req, section.url, Flash("ok", "The original is back. “Undo the last change” brings yours back.")
    )


def undo_settings(req: Request) -> Response:
    with WORK_LOCK:
        undone = parish.undo()
    target = safe_next(req.field("next"))
    if not undone:
        return redirect(req, target, Flash("warning", "There's nothing to undo."))
    return redirect(req, target, Flash("ok", "The last change to the settings was undone."))


def logo_picture(req: Request) -> Response:
    path = Path(parish.load().logo)
    if path.suffix not in IMAGE_TYPES or not path.is_file() or ".." in path.parts or path.is_absolute():
        raise NotFound
    return Response(path.read_bytes(), headers=[("Content-Type", IMAGE_TYPES[path.suffix]), ("Cache-Control", "no-cache")])


def login_form(req: Request) -> Response:
    if not req.app.password:
        return redirect(req, "/")
    return page(req, "login.html", next=safe_next(req.arg("next")), error="")


def login(req: Request) -> Response:
    target = safe_next(req.field("next"))
    if not req.app.password:
        return redirect(req, target)
    if not req.app.is_password(req.form.get("password", [""])[0]):
        time.sleep(FAILED_LOGIN_DELAY_S)
        return page(req, "login.html", 401, next=target, error="That password isn't right.")
    return redirect(req, target).set_cookie(req, SESSION_COOKIE, req.app.new_session(), SESSION_SECONDS)


def logout(req: Request) -> Response:
    return redirect(req, "/login").set_cookie(req, SESSION_COOKIE, "", 0)


DATE = r"(\d{4}-\d{2}-\d{2})"
ROUTES: list[tuple[str, re.Pattern[str], Callable[..., Response]]] = [
    (method, re.compile(pattern), handler)
    for method, pattern, handler in [
        ("GET", r"/", home),
        ("GET", r"/login", login_form),
        ("POST", r"/login", login),
        ("POST", r"/logout", logout),
        ("GET", r"/sundays", open_sunday),
        ("GET", rf"/sundays/{DATE}", sunday_page),
        ("POST", rf"/sundays/{DATE}/fetch", fetch),
        ("POST", rf"/sundays/{DATE}/details", save_details),
        ("GET", rf"/sundays/{DATE}/readings", readings_form),
        ("POST", rf"/sundays/{DATE}/readings", save_readings),
        ("GET", rf"/sundays/{DATE}/(booklet|bulletin)\.pdf", pdf),
        ("GET", rf"/sundays/{DATE}/preview-(\d+)\.png", preview),
        ("GET", r"/settings", settings_home),
        ("POST", r"/settings/undo", undo_settings),
        ("GET", r"/settings/logo-picture", logo_picture),
        ("GET", r"/settings/([a-z-]+)", settings_form),
        ("POST", r"/settings/([a-z-]+)", save_settings),
        ("POST", r"/settings/([a-z-]+)/original", put_back_settings),
        ("GET", r"/static/([\w.-]+)", static),
    ]
]


def dispatch(req: Request) -> Response:
    path_exists = False
    for method, pattern, handler in ROUTES:
        match = pattern.fullmatch(req.path)
        if not match:
            continue
        if method == req.method:
            try:
                return handler(req, *match.groups())
            except NotFound:
                return not_found(req)
        path_exists = True
    return plain(405, "Method not allowed.") if path_exists else not_found(req)


################################################################################
# app
################################################################################


class App:
    def __init__(self, password: str = ""):
        self.password = password
        # sessions end when the server restarts, which is rare and costs only a login
        self.secret = secrets.token_bytes(32)

    def sign(self, value: str) -> str:
        return hmac.new(self.secret, value.encode(), hashlib.sha256).hexdigest()

    def new_session(self) -> str:
        expires = str(int(time.time()) + SESSION_SECONDS)
        return f"{expires}.{self.sign(expires)}"

    def has_session(self, req: Request) -> bool:
        expires, _, signature = req.cookies.get(SESSION_COOKIE, "").partition(".")
        return (
            expires.isdigit()
            and hmac.compare_digest(signature, self.sign(expires))
            and int(expires) > time.time()
        )

    def is_password(self, attempt: str) -> bool:
        return hmac.compare_digest(attempt.encode(), self.password.encode())

    def respond(self, req: Request, environ: dict) -> Response:
        fetch_site = environ.get("HTTP_SEC_FETCH_SITE", "same-origin")
        if req.method == "POST" and fetch_site not in ("same-origin", "none"):
            return plain(403, "Forms can only be sent from this site.")
        public = req.path == "/login" or req.path.startswith("/static/")
        if self.password and not public and not self.has_session(req):
            target = req.path if req.method == "GET" else "/"
            return redirect(req, f"/login?next={quote(target)}")
        return dispatch(req)

    def __call__(self, environ: dict, start_response: Callable) -> list[bytes]:
        started = time.monotonic()
        try:
            response = self.respond(parse_request(self, environ), environ)
        except BodyTooLarge:
            if environ.get("PATH_INFO") in UPLOAD_PATHS:
                response = plain(413, "That picture is too large: it can be up to 5 MB. Go back and choose a smaller one.")
            else:
                response = plain(413, "That form was too large to save.")
        except Exception:
            traceback.print_exc()
            response = plain(500, "Something went wrong. The details are in the server log.")

        elapsed_ms = (time.monotonic() - started) * 1000
        print(
            f"{environ['REQUEST_METHOD']} {environ.get('PATH_INFO')} {response.status} {elapsed_ms:.0f}ms",
            file=sys.stderr,
        )
        start_response(f"{response.status} {HTTPStatus(response.status).phrase}", response.headers)
        return [response.body]


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the bulletin builder web UI")
    parser.add_argument("--host", default="127.0.0.1", help="address to listen on (default: this computer only)")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8000)))
    args = parser.parse_args()

    password = os.environ.get("BULLETIN_PASSWORD", "")
    if not password and args.host not in LOCAL_HOSTS:
        parser.error("set BULLETIN_PASSWORD to serve beyond this computer")

    os.chdir(Path(__file__).resolve().parent)
    sunday.STATE_DIR.mkdir(exist_ok=True)
    if not os.access(sunday.STATE_DIR, os.W_OK):
        parser.error(f"can't write to {sunday.STATE_DIR.resolve()} (on Railway, set RAILWAY_RUN_UID=0)")
    sunday.SUNDAYS_DIR.mkdir(exist_ok=True)
    parish.ensure()
    print(f"Bulletin Builder on http://{args.host}:{args.port}/", file=sys.stderr)
    waitress.serve(
        App(password),
        host=args.host,
        port=args.port,
        threads=4,
        # above the app's own limits, so that the app can explain them
        max_request_body_size=2 * MAX_UPLOAD_BYTES,
        # behind the reverse proxy (see deploy/), so the session cookie is marked Secure
        trusted_proxy="*",
        trusted_proxy_headers={"x-forwarded-proto"},
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
