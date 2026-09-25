import io
import shutil
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

import httpx
import pytest

import manual
import sunday
import web
from classes import ManualData, ManualHymnData, UpcomingServiceData
from yaml_io import read_yaml

ROOT = Path(__file__).resolve().parent.parent
DAY = "2026-09-27"
PASSWORD = "correct horse battery staple"


@dataclass
class Result:
    status: int
    headers: dict[str, str]
    body: bytes

    @property
    def text(self) -> str:
        return self.body.decode()


class Client:
    def __init__(self, app: web.App):
        self.app = app
        self.cookies: dict[str, str] = {}
        self.secure: set[str] = set()

    def request(self, method: str, url: str, form: dict | None = None, **environ: str) -> Result:
        path, _, query = url.partition("?")
        body = urlencode(form or {}, doseq=True).encode()
        env: dict = {}
        setup_testing_defaults(env)
        env |= {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
            "HTTP_COOKIE": "; ".join(f"{name}={value}" for name, value in self.cookies.items()),
            **environ,
        }
        started: dict = {}

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            started["status"] = int(status.split()[0])
            started["headers"] = headers

        content = b"".join(self.app(env, start_response))
        for name, value in started["headers"]:
            if name == "Set-Cookie":
                cookie, _, rest = value.partition("=")
                if "Max-Age=0;" in value:
                    self.cookies.pop(cookie, None)
                else:
                    self.cookies[cookie] = rest.split(";")[0]
                if value.endswith("; Secure"):
                    self.secure.add(cookie)
        return Result(started["status"], dict(started["headers"]), content)

    def get(self, url: str) -> Result:
        return self.request("GET", url)

    def post(self, url: str, form: dict | None = None, **environ: str) -> Result:
        return self.request("POST", url, form, **environ)

    def follow(self, result: Result) -> Result:
        assert result.status == 303, result.text
        return self.get(result.headers["Location"])


@pytest.fixture
def client(site) -> Client:
    return Client(web.App())


@pytest.fixture
def archived(site) -> Path:
    shutil.copytree(ROOT / "archive" / DAY, site / "archive" / DAY)
    return site / "build" / DAY


@pytest.fixture
def network(monkeypatch) -> list[str]:
    """Every download is answered with a bot-check refusal; returns the URLs asked for."""
    asked: list[str] = []

    def refuse(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        return httpx.Response(503, text="Just a moment...")

    monkeypatch.setattr(sunday, "http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(refuse)))
    return asked


def details_form(**fields: list[str]) -> dict[str, list[str]]:
    form = {"hymn_title": [], "hymn_mode": [], "hymn_page": [], "service_date": [], "service_priest": []}
    return form | fields


################################################################################
# pages and the Sunday workflow
################################################################################


def test_home_offers_the_next_sunday(client):
    page = client.get("/")
    assert page.status == 200
    assert f"/sundays/{sunday.next_sunday(date.today()).isoformat()}" in page.text
    assert page.headers["Content-Security-Policy"].startswith("default-src 'self'")


def test_home_lists_only_recent_sundays(site, client):
    for weeks in range(web.RECENT_SUNDAYS + 3):
        (site / "build" / (date(2026, 1, 4) + timedelta(weeks=weeks)).isoformat()).mkdir(parents=True)
    page = client.get("/").text
    assert page.count('<td><a href="/sundays/') == web.RECENT_SUNDAYS
    assert "/sundays/2026-01-04" not in page


def test_new_sunday_page_offers_the_download(client):
    page = client.get(f"/sundays/{DAY}")
    assert page.status == 200
    assert "Download the readings" in page.text
    assert "Not saved yet" in page.text


def test_download_makes_the_booklet(archived, network, client):
    page = client.follow(client.post(f"/sundays/{DAY}/fetch"))

    assert network == []
    assert "Readings downloaded" in page.text
    assert "1st Sunday of Luke" in page.text
    assert "preview-2.png" in page.text and "preview-3.png" not in page.text
    assert (archived / "booklet.pdf").exists()
    assert "Readings downloaded" not in client.get(f"/sundays/{DAY}").text

    pdf = client.get(f"/sundays/{DAY}/booklet.pdf?download=1")
    assert pdf.headers["Content-Type"] == "application/pdf"
    assert pdf.headers["Content-Disposition"] == f'attachment; filename="{DAY}-booklet.pdf"'
    assert pdf.body.startswith(b"%PDF")
    assert client.get(f"/sundays/{DAY}/bulletin.pdf").headers["Content-Disposition"].startswith("inline")
    assert client.get(f"/sundays/{DAY}/preview-1.png").body.startswith(b"\x89PNG")


def test_a_refused_download_changes_nothing(site, network, client):
    page = client.follow(client.post(f"/sundays/{DAY}/fetch"))

    assert "refused the download" in page.text
    assert "Nothing was changed" in page.text
    assert len(network) == 2
    assert not (site / "build" / DAY).exists()
    assert not (site / "archive" / DAY).exists()


def test_saving_hymns_and_services(site, client):
    result = client.post(
        f"/sundays/{DAY}/details",
        details_form(
            hymn_title=["Resurrectional Apolytikion", "", "Ordinary Kontakion"],
            hymn_mode=["8", "3", ""],
            hymn_page=["127", "p. 5", " Choir "],
            service_date=["Today", "10/03/2026", ""],
            service_priest=["Fr. Joshua", "", ""],
        ),
    )

    assert "Hymns and services saved" in client.follow(result).text
    assert manual.read(site / "build" / DAY) == ManualData(
        [
            ManualHymnData("Resurrectional Apolytikion", 8, "p. 127"),
            ManualHymnData("Ordinary Kontakion", None, "Choir"),
        ],
        [UpcomingServiceData("Today", "Fr. Joshua"), UpcomingServiceData("10/03/2026", "")],
    )


def test_saved_hymns_fill_the_form_and_suggestions(archived, network, client):
    client.post(f"/sundays/{DAY}/fetch")
    client.post(
        f"/sundays/{DAY}/details",
        details_form(hymn_title=["Ordinary Kontakion"], hymn_mode=["2"], hymn_page=["225"],
                     service_date=["Today"], service_priest=["Fr. Joshua"]),
    )

    page = client.get(f"/sundays/{DAY}").text
    assert 'value="Ordinary Kontakion"' in page
    assert "<option selected>2</option>" in page
    assert '<option value="Fr. Joshua">' in page
    assert "Not ready to print" not in page


def test_readings_can_be_typed_in_by_hand(site, client):
    day = "2026-10-11"
    result = client.post(
        f"/sundays/{day}/readings",
        {
            "lectionary_title": "3rd Sunday of Luke",
            "formatted_date": "October 11, 2026",
            "icon_title": "",
            "epistle_book": "St. Paul's Letter to the Galatians",
            "epistle_chapverse": "1:11-19",
            "prokeimenon": "The Lord will give strength to his people.",
            "verse": "Bring to the Lord, O sons of God.",
            "epistle_text": "Brethren, I would have you know\r\nthat the gospel.\r\n\r\n  For you have heard. ",
            "alleluia": "The heavens will confess your wonders.\n\nGod is glorified.",
            "gospel_book": "The Holy Gospel According to St. Luke",
            "gospel_chapverse": "7:11-16",
            "gospel_text": "At that time, Jesus went to a city called Nain.",
        },
    )

    page = client.follow(result).text
    out_dir = site / "build" / day
    assert "Readings saved" in page and "3rd Sunday of Luke" in page
    assert read_yaml(out_dir / "epistle.yaml")["text"] == [
        "Brethren, I would have you know that the gospel.",
        "For you have heard.",
    ]
    assert read_yaml(out_dir / "digital_chant_stand.yaml")["alleluia"] == [
        "The heavens will confess your wonders.",
        "God is glorified.",
    ]
    assert read_yaml(out_dir / "feed.yaml")["font_size_pt"] == 10
    assert (out_dir / "booklet.pdf").exists()


def test_readings_form_shows_the_downloaded_text(archived, network, client):
    client.post(f"/sundays/{DAY}/fetch")
    page = client.get(f"/sundays/{DAY}/readings").text
    assert 'value="St. Paul&#39;s Second Letter to the Corinthians"' in page
    assert "Make your vows to the Lord our God" in page


def test_text_is_escaped(site, client):
    client.post(
        f"/sundays/{DAY}/details",
        details_form(hymn_title=["<script>alert(1)</script>"], hymn_mode=[""], hymn_page=[""]),
    )
    page = client.get(f"/sundays/{DAY}").text
    assert "<script>alert(1)" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page


def test_the_page_before_readings_has_no_pdf(client):
    assert client.get(f"/sundays/{DAY}/booklet.pdf").status == 404
    assert client.get(f"/sundays/{DAY}/preview-1.png").status == 404


################################################################################
# addresses
################################################################################


def test_dates_that_are_not_sundays(client):
    assert client.get("/sundays/2026-09-26").headers["Location"] == f"/sundays/{DAY}"
    assert client.get("/sundays?date=2026-09-26").headers["Location"] == f"/sundays/{DAY}"
    assert client.get("/sundays?date=").headers["Location"] == "/"
    assert client.get("/sundays/2026-02-30").status == 404
    assert client.post("/sundays/2026-09-26/fetch").status == 404


def test_unknown_addresses(client):
    assert client.get("/nowhere").status == 404
    assert client.get("/static/..").status == 404
    assert client.get("/static/conftest.py").status == 404
    assert client.get("/static/style.css").headers["Content-Type"].startswith("text/css")
    assert client.post("/").status == 405


################################################################################
# login and safety
################################################################################


@pytest.fixture
def locked(site, monkeypatch) -> Client:
    monkeypatch.setattr(web, "FAILED_LOGIN_DELAY_S", 0)
    return Client(web.App(password=PASSWORD))


def test_password_protects_every_page(site, locked):
    assert locked.get(f"/sundays/{DAY}").headers["Location"] == f"/login?next=/sundays/{DAY}"
    assert locked.post(f"/sundays/{DAY}/details", details_form(hymn_title=["x"])).headers["Location"] == "/login?next=/"
    assert not (site / "build" / DAY).exists()
    assert locked.get("/login").status == 200
    assert locked.get("/static/style.css").status == 200


def test_login_and_logout(locked):
    assert locked.post("/login", {"password": "wrong", "next": "/"}).status == 401
    assert web.SESSION_COOKIE not in locked.cookies

    result = locked.post("/login", {"password": PASSWORD, "next": f"/sundays/{DAY}"})
    assert result.headers["Location"] == f"/sundays/{DAY}"
    assert "Log out" in locked.get(f"/sundays/{DAY}").text

    locked.post("/logout")
    assert locked.get("/").status == 303


def test_session_cookie_is_secure_over_https(locked):
    locked.request("POST", "/login", {"password": PASSWORD}, **{"wsgi.url_scheme": "https"})
    plain_http = Client(locked.app)
    plain_http.post("/login", {"password": PASSWORD})
    assert locked.cookies and plain_http.cookies
    assert locked.secure == {web.SESSION_COOKIE}
    assert plain_http.secure == set()


def test_login_only_returns_to_this_site(locked):
    for target in ("//example.com/", "/\t/example.com/", "https://example.com/"):
        result = locked.post("/login", {"password": PASSWORD, "next": target})
        assert result.headers["Location"] == "/"


def test_forged_and_foreign_sessions_are_refused(locked):
    expires = str(int(time.time()) + 3600)
    locked.cookies[web.SESSION_COOKIE] = f"{expires}.{'0' * 64}"
    assert locked.get("/").status == 303

    locked.cookies[web.SESSION_COOKIE] = web.App(password=PASSWORD).new_session()
    assert locked.get("/").status == 303


def test_garbled_flash_cookie_is_ignored(client):
    client.cookies[web.FLASH_COOKIE] = "NQ"  # base64 of the JSON number 5
    assert client.get("/").status == 200


def test_cross_site_forms_are_refused(site, client):
    result = client.post(
        f"/sundays/{DAY}/details",
        details_form(hymn_title=["x"]),
        HTTP_SEC_FETCH_SITE="cross-site",
    )
    assert result.status == 403
    assert not (site / "build" / DAY).exists()


def test_oversized_forms_are_refused(client):
    result = client.post(f"/sundays/{DAY}/readings", {"gospel_text": "x" * (web.MAX_BODY_BYTES + 1)})
    assert result.status == 413
