import argparse
import asyncio
import base64
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
from dataclasses import dataclass, field
from datetime import date
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, quote

import httpx
import jinja2
import waitress

import manual
import render
import sunday
from classes import ManualData, ManualHymnData, UpcomingServiceData
from yaml_io import read_yaml

STATIC_DIR = Path("static")
TEMPLATE_DIR = Path("templates")
MAX_BODY_BYTES = 1_000_000
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

# scrapes, saves and renders all rewrite build dirs, so they take turns
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


################################################################################
# requests and responses
################################################################################


def parse_request(app: "App", environ: dict) -> Request:
    method = environ["REQUEST_METHOD"]
    form = {}
    if method == "POST":
        length = int(environ.get("CONTENT_LENGTH") or 0)
        if length > MAX_BODY_BYTES:
            raise BodyTooLarge
        body = environ["wsgi.input"].read(length).decode("latin-1")
        form = parse_qs(body, keep_blank_values=True)

    try:
        cookie = SimpleCookie(environ.get("HTTP_COOKIE", ""))
    except CookieError:
        cookie = SimpleCookie()
    return Request(
        app=app,
        method="GET" if method == "HEAD" else method,
        path=environ.get("PATH_INFO") or "/",
        query=parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True),
        form=form,
        cookies={name: morsel.value for name, morsel in cookie.items()},
        https=environ.get("wsgi.url_scheme") == "https",
    )


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
        flash=flash, show_logout=bool(req.app.password), **context
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
    out_dir = sunday.build_dir(day)
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
    others = [day for day in sunday.built_dates() if day != upcoming][:RECENT_SUNDAYS]
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

    out_dir = sunday.build_dir(day)
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
    shown = details or manual.template(day, manual.previous(day, sunday.BUILD_DIR))

    return page(
        req,
        "sunday.html",
        day=day,
        url=sunday_url(day),
        service_day=manual.service_day(day),
        readings=sunday.load_readings(day, out_dir),
        missing=missing,
        nothing_fetched=len(missing) == len(sunday.SOURCES),
        font_size_pt=feed.get("font_size_pt"),
        layout=LAYOUT_DESCRIPTIONS.get(feed.get("layout"), ""),
        details_saved=details is not None,
        unfinished=manual.unfinished(details) if details else [],
        hymn_rows=padded(shown.dismissal_hymns, MIN_HYMN_ROWS, ManualHymnData),
        service_rows=padded(shown.upcoming_services, MIN_SERVICE_ROWS, UpcomingServiceData),
        modes=manual.MODES,
        suggestions=manual.suggestions(sunday.BUILD_DIR),
        hymnal=manual.hymnal_index(),
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
    hymns = [
        ManualHymnData(title=title, mode=manual.parse_mode(mode), page=manual.page_label(page))
        for title, mode, page in zip(
            req.fields("hymn_title"), req.fields("hymn_mode"), req.fields("hymn_page")
        )
        if title
    ]
    services = [
        UpcomingServiceData(date=when, priest=priest)
        for when, priest in zip(req.fields("service_date"), req.fields("service_priest"))
        if when or priest
    ]
    with WORK_LOCK:
        manual.write(ManualData(hymns, services), sunday.build_dir(day))
    return redirect(req, sunday_url(day), Flash("ok", "Hymns and services saved."))


def readings_form(req: Request, iso: str) -> Response:
    day = parse_sunday(iso)
    return page(
        req,
        "readings.html",
        day=day,
        url=sunday_url(day),
        readings=sunday.load_readings(day, sunday.build_dir(day)),
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
        sunday.save_readings(day, sunday.build_dir(day), readings)
    return redirect(req, sunday_url(day), Flash("ok", "Readings saved."))


def pdf(req: Request, iso: str, document: str) -> Response:
    day = parse_sunday(iso)
    out_dir = sunday.build_dir(day)
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
    path = sunday.build_dir(parse_sunday(iso)) / f"preview-{int(number)}.png"
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
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    password = os.environ.get("BULLETIN_PASSWORD", "")
    if not password and args.host not in LOCAL_HOSTS:
        parser.error("set BULLETIN_PASSWORD to serve beyond this computer")

    os.chdir(Path(__file__).resolve().parent)
    print(f"Bulletin Builder on http://{args.host}:{args.port}/", file=sys.stderr)
    waitress.serve(
        App(password),
        host=args.host,
        port=args.port,
        threads=4,
        max_request_body_size=MAX_BODY_BYTES,
        # behind the reverse proxy (see deploy/), so the session cookie is marked Secure
        trusted_proxy="*",
        trusted_proxy_headers={"x-forwarded-proto"},
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
