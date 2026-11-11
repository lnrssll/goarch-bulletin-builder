import html
import io
import re
import shutil
import time
import zipfile
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults

import httpx
import pytest

import manual
import parish
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

    def request(
        self, method: str, url: str, form: dict | None = None, files: dict | None = None, **environ: str
    ) -> Result:
        path, _, query = url.partition("?")
        if files is None:
            body = urlencode(form or {}, doseq=True).encode()
            content_type = "application/x-www-form-urlencoded"
        else:
            body, content_type = multipart(form or {}, files)
        env: dict = {}
        setup_testing_defaults(env)
        env |= {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "CONTENT_TYPE": content_type,
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

    def post(self, url: str, form: dict | None = None, files: dict | None = None, **environ: str) -> Result:
        return self.request("POST", url, form, files, **environ)

    def follow(self, result: Result) -> Result:
        assert result.status == 303, result.text
        return self.get(result.headers["Location"])


def multipart(form: dict, files: dict[str, tuple[str, bytes]]) -> tuple[bytes, str]:
    """A form as a browser sends it with a file; filenames go into the header as given."""
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        for name, values in form.items()
        for value in (values if isinstance(values, list) else [values])
    ]
    parts += [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n".encode() + content + b"\r\n"
        for name, (filename, content) in files.items()
    ]
    return b"".join(parts) + f"--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


@pytest.fixture
def client(site) -> Client:
    return Client(web.App())


@pytest.fixture
def archived(site) -> Path:
    shutil.copytree(ROOT / "archive" / DAY, site / "archive" / DAY)
    return site / "state" / "sundays" / DAY


@pytest.fixture
def network(monkeypatch) -> list[str]:
    """Every download is answered with a bot-check refusal; returns the URLs asked for."""
    asked: list[str] = []

    def refuse(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        return httpx.Response(503, text="Just a moment...")

    monkeypatch.setattr(sunday, "http_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(refuse)))
    return asked


def readings_form(page: str) -> dict[str, str]:
    """The readings editor's text as it would be sent back unchanged."""
    fields = dict(re.findall(r'<input name="(\w+)" value="([^"]*)"', page))
    fields |= {name: html.unescape(text) for name, text in re.findall(r'<textarea name="(\w+)"[^>]*>(.*?)</textarea>', page, re.S)}
    return {name: html.unescape(value) for name, value in fields.items()}


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
        (site / "state" / "sundays" / (date(2026, 1, 4) + timedelta(weeks=weeks)).isoformat()).mkdir(parents=True)
    page = client.get("/").text
    assert page.count('<td><a href="/sundays/') == web.RECENT_SUNDAYS
    assert "/sundays/2026-01-04" not in page


def test_new_sunday_page_offers_the_download(client):
    page = client.get(f"/sundays/{DAY}")
    assert page.status == 200
    assert "Download the readings" in page.text
    assert "Not saved yet" in page.text


def pages_elsewhere(page: Result) -> dict[str, str]:
    links = re.findall(r'<a class="button small" href="([^"]*)" target="_blank" rel="noopener">([^<]*) <span', page.text)
    return {name: html.unescape(url) for url, name in links}


def test_the_pages_elsewhere_can_be_opened(archived, network, client):
    expected = {
        "Online Chapel": "https://onlinechapel.goarch.org/daily?date=9/27/2026",
        "Digital Chant Stand": "https://dcs.goarch.org/goa/dcs/h/s/2026/09/27/li2/en/",
        "Church calendar": "https://www.lakehavasuorthodoxchurch.org/calendar",
    }
    assert pages_elsewhere(client.get("/sundays/2026-11-08"))["Digital Chant Stand"].endswith("/2026/11/08/li2/en/")
    client.post(f"/sundays/{DAY}/fetch")
    assert network == []
    assert pages_elsewhere(client.get(f"/sundays/{DAY}")) == expected


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


def test_the_days_hymns_are_shown_next_to_goarch(archived, network, client):
    page = client.follow(client.post(f"/sundays/{DAY}/fetch")).text

    assert '<details class="day-hymns" data-replace="Example" open>' in page
    assert "Callistratus the Martyr &amp; his 49 Companions" in page
    assert "Gideon the Righteous" in page and "no hymns" in page
    assert "On goarch.org: Apolytikion of Martyr Callistratus &amp; his Companions · Mode 4" in page
    assert "In the Chant Stand as “For the Martyrs”" in page

    added = re.findall(r'<button type="button" class="link" data-title="([^"]*)" data-mode="(\d*)">', page)
    assert [(html.unescape(title), mode) for title, mode in added[:3]] == [
        ("Resurrectional Apolytikion", "8"),
        ("Apolytikion of Martyr Callistratus & his Companions", "4"),
        ("Kontakion Mode 2", "2"),
    ]


def test_a_refused_download_changes_nothing(site, network, client):
    page = client.follow(client.post(f"/sundays/{DAY}/fetch"))

    assert "refused the download" in page.text
    assert "Nothing was changed" in page.text
    assert "What it sent is saved in state/failed-downloads/" in page.text
    assert len(network) == 2
    assert not (site / "state" / "sundays" / DAY).exists()
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
    assert manual.read(site / "state" / "sundays" / DAY) == ManualData(
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
    assert 'name="hymn_page" value="225"' in page
    assert 'name="service_priest" value="Joshua"' in page
    assert '<option value="Joshua">' in page
    assert "Not ready to print" not in page


def test_suggestions_carry_the_mode_and_page(client):
    page = client.get(f"/sundays/{DAY}").text
    assert (
        '<option value="Resurrectional Apolytikion" data-pages=\'{"1": "99", "2": "103", "3": "107", "4": "111", '
        '"5": "115", "6": "119", "7": "123", "8": "127"}\''
    ) in page
    assert '<option value="Kontakion for the Mother of God" data-mode="2" data-page="225"' in page
    assert '<option value="Reader Service">' in page
    assert '<option value="Handout">' in page


def test_saving_adds_the_prefixes(site, client):
    client.post(
        f"/sundays/{DAY}/details",
        details_form(
            hymn_title=["Apol. of Sun. of Orthodoxy", "Hypakoe"],
            hymn_mode=["2", "4"],
            hymn_page=["129", "handout"],
            service_date=["Today", "10/03/2026", "10/10/2026"],
            service_priest=["Joshua", "reader service", "Fr. Jacob"],
        ),
    )
    assert manual.read(site / "state" / "sundays" / DAY) == ManualData(
        [
            ManualHymnData("Apolytikion of Sunday of Orthodoxy", 2, "p. 129"),
            ManualHymnData("Hypakoe", 4, "Handout"),
        ],
        [
            UpcomingServiceData("Today", "Fr. Joshua"),
            UpcomingServiceData("10/03/2026", "Reader Service"),
            UpcomingServiceData("10/10/2026", "Fr. Jacob"),
        ],
    )


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
            "prokeimenon": "The Lord will give strength\r\nto his people.",
            "verse": "Bring to the Lord, O sons of God.",
            "epistle_text": "Brethren, I would have you know\r\nthat the gospel.\r\n\r\n  For you have heard. ",
            "alleluia": "The heavens will confess your wonders.\n\nGod is glorified.",
            "gospel_book": "The Holy Gospel According to St. Luke",
            "gospel_chapverse": "7:11-16",
            "gospel_text": "At that time, Jesus went to a city called Nain.",
        },
    )

    page = client.follow(result).text
    out_dir = site / "state" / "sundays" / day
    assert "Readings saved" in page and "3rd Sunday of Luke" in page
    assert read_yaml(out_dir / "epistle.yaml")["text"] == [
        "Brethren, I would have you know that the gospel.",
        "For you have heard.",
    ]
    assert read_yaml(out_dir / "epistle.yaml")["prokeimenon"] == "The Lord will give strength to his people."
    assert read_yaml(out_dir / "digital_chant_stand.yaml")["alleluia"] == [
        "The heavens will confess your wonders.",
        "God is glorified.",
    ]
    assert read_yaml(out_dir / "feed.yaml")["font_size_pt"] == 10
    assert (out_dir / "booklet.pdf").exists()


def test_an_overflowing_sunday_can_be_fixed_by_hand(ready, client):
    feed_path = ready / "feed.yaml"
    readings = client.get(f"/sundays/{DAY}/readings").text
    form = readings_form(readings)

    client.post(f"/sundays/{DAY}/readings", form | {"size_override_pt": "10.0", "layout_override": "split_before_alleluia"})
    feed = read_yaml(feed_path)
    assert (feed["size_override_pt"], feed["layout_override"]) == (10.0, "split_before_alleluia")
    assert feed["text_size_factor"] == 100.0 and feed["alleluia_page_break"]
    page = client.get(f"/sundays/{DAY}").text
    assert "(chosen by hand)" in page
    assert "preview-3.png" in page and "readings#text-size" in page

    client.post(f"/sundays/{DAY}/readings", form | {"size_override_pt": "7.0", "layout_override": "split_before_alleluia"})
    assert "preview-3.png" not in client.get(f"/sundays/{DAY}").text
    assert 'value="7.0" selected' in client.get(f"/sundays/{DAY}/readings").text

    client.post(f"/sundays/{DAY}/readings", form | {"size_override_pt": "", "layout_override": "nonsense"})
    feed = read_yaml(feed_path)
    assert (feed["size_override_pt"], feed["layout_override"]) == (None, None)
    assert "(chosen by hand)" not in client.get(f"/sundays/{DAY}").text


def test_readings_form_shows_the_downloaded_text(archived, network, client):
    client.post(f"/sundays/{DAY}/fetch")
    page = client.get(f"/sundays/{DAY}/readings").text
    assert 'value="St. Paul’s Second Letter to the Corinthians"' in page
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
# settings
################################################################################


@pytest.fixture
def ready(site) -> Path:
    """A Sunday that can be printed, for the settings pages' pictures."""
    out_dir = site / "state" / "sundays" / DAY
    shutil.copytree(ROOT / "tests" / "snapshots" / DAY, out_dir)
    manual.write_template(date.fromisoformat(DAY), out_dir)
    return out_dir


def test_settings_are_only_linked_from_the_footer(client):
    page = client.get("/").text
    assert page.count('href="/settings"') == 1
    assert '<footer class="site-footer">' in page
    settings = client.get("/settings").text
    for section in web.SECTIONS:
        assert f'href="{section.url}"' in settings
    assert "Nothing has been changed here yet" in settings


@pytest.mark.parametrize("section", web.SECTIONS, ids=lambda section: section.slug)
def test_every_settings_page_opens(ready, client, section):
    page = client.get(section.url)
    assert page.status == 200
    assert ("preview-1.png" in page.text) == bool(section.sides)
    assert ("preview-2.png" in page.text) == (section.sides == 2)


def test_settings_page_without_a_sunday_to_show(client):
    assert "appears here once a Sunday" in client.get("/settings/welcome").text


def test_saving_the_welcome_text(ready, client):
    result = client.post(
        "/settings/welcome",
        {"welcome_heading": " Welcome! ", "welcome": "First  paragraph,\r\nstill first.\r\n\r\nSecond <b>one</b>."},
    )
    assert result.headers["Location"] == "/settings/welcome"
    page = client.follow(result).text
    assert "Saved." in page
    assert "Second &lt;b&gt;one&lt;/b&gt;." in page
    assert "Put back the original" in page
    settings = parish.load()
    assert settings.welcome_heading == "Welcome!"
    assert settings.welcome == ["First paragraph, still first.", "Second <b>one</b>."]

    assert "Nothing was changed" in client.follow(client.post("/settings/welcome", {
        "welcome_heading": "Welcome!", "welcome": "First paragraph, still first.\n\nSecond <b>one</b>.",
    })).text


def test_a_refused_setting_keeps_what_was_typed(client):
    result = client.post("/settings/wording", {name: "Typed" for name in web.WORDING} | {"today": ""})
    assert result.status == 400
    assert "can't be empty" in html.unescape(result.text)
    assert 'value="Typed"' in result.text
    assert parish.load() == parish.original()


def test_the_two_contacts(client):
    page = client.get("/settings/contacts").text
    assert page.count('name="contact_name"') == parish.CONTACTS
    assert 'value="Fr. Timothy Pavlatos"' in page

    form = {
        "contact_name": ["", "Fr. B", "Fr. C"],
        "contact_church": ["", "", "Church C"],
        "contact_city": ["", "", ""],
        "contact_email": ["", "b@example.org", ""],
        "contact_phone": ["", "", ""],
    }
    client.post("/settings/contacts", form)
    assert parish.load().contacts == [parish.Contact(name="Fr. B", email="b@example.org")]


def test_the_calendar(client):
    client.post("/settings/calendar", {"calendar": "example.org/events"})
    assert parish.load().calendar == "example.org/events"
    assert pages_elsewhere(client.get(f"/sundays/{DAY}"))["Church calendar"] == "https://example.org/events"
    assert client.post("/settings/calendar", {"calendar": "two words"}).status == 400

    client.post("/settings/calendar", {"calendar": ""})
    assert "Church calendar" not in pages_elsewhere(client.get(f"/sundays/{DAY}"))


def test_website_and_liturgy_day(client):
    client.post("/settings/website", {"website": "example.org", "website_lines": " example\r\n\r\n.org "})
    settings = parish.load()
    assert (settings.website, settings.website_lines) == ("example.org", ["example", ".org"])
    assert client.post("/settings/website", {"website": "two words", "website_lines": ""}).status == 400

    assert client.post("/settings/liturgy-day", {"liturgy_day": "monday"}).status == 400
    client.post("/settings/liturgy-day", {"liturgy_day": parish.SUNDAY})
    assert "Picking the Saturday" not in client.get("/").text
    page = client.get(f"/sundays/{DAY}").text
    assert "Divine Liturgy on Sunday, September 27, 2026" in page
    assert "10/04/2026" in page


def test_the_hymnal_index(client):
    result = client.post("/settings/hymnal", {"hymnal_index": "Ordinary Kontakion | 225 | Kontakia\r\nJust a title\r\n"})
    assert result.status == 400
    assert "Line 2" in result.text
    client.post("/settings/hymnal", {"hymnal_index": "New Hymn | 301 | New Section\r\n"})
    assert "New Hymn" in client.get(f"/sundays/{DAY}").text


def test_put_back_the_original_and_undo(client):
    client.post("/settings/welcome", {"welcome_heading": "Hello", "welcome": "Hi."})
    page = client.follow(client.post("/settings/welcome/original")).text
    assert "The original is back" in page
    assert parish.load() == parish.original()

    page = client.follow(client.post("/settings/undo", {"next": "/settings/welcome"})).text
    assert "was undone" in page
    assert parish.load().welcome_heading == "Hello"
    client.post("/settings/undo", {"next": "/settings"})
    assert "nothing to undo" in html.unescape(client.follow(client.post("/settings/undo", {"next": "//example.org"})).text)


def test_a_setting_that_overflows_is_reported(ready, client):
    client.post("/settings/welcome", {"welcome_heading": "Welcome", "welcome": "Long text. " * 400})
    page = client.get("/settings/welcome").text
    assert "has 3 pages instead of 2" in page
    assert 'action="/settings/undo"' in page


def test_uploading_a_logo(ready, client):
    logo = (ROOT / "assets" / "lhoc-qr.png").read_bytes()
    result = client.post("/settings/logo", files={"logo": ('my "logo" ïcon.png', logo)})
    assert "Saved." in client.follow(result).text
    path = Path(parish.load().logo)
    assert path.parent == parish.IMAGES_DIR and path.read_bytes() == logo

    picture = client.get("/settings/logo-picture")
    assert (picture.headers["Content-Type"], picture.body) == ("image/png", logo)


def test_uploads_that_are_not_logos(client):
    for content, message in [
        (b"", "Choose a picture first"),
        (b"GIF89a....", "isn't a PNG, JPEG or WebP"),
        (b"\x89PNG\r\n\x1a\nbroken", "couldn't be read"),
    ]:
        result = client.post("/settings/logo", files={"logo": ("logo.png", content)})
        assert result.status == 400 and message in html.unescape(result.text)
    assert parish.load().logo == parish.original().logo
    assert not list(parish.IMAGES_DIR.glob("*"))


def test_a_logo_that_is_too_large(client):
    result = client.post("/settings/logo", files={"logo": ("big.png", b"\x89PNG" + b"0" * web.MAX_UPLOAD_BYTES)})
    assert result.status == 413 and "up to 5 MB" in result.text
    small = client.post("/settings/welcome", {"welcome": "x" * (web.MAX_BODY_BYTES + 1)})
    assert small.status == 413


def test_downloading_a_backup(ready, client):
    assert "download a backup" in client.get("/").text
    assert "No backup has been downloaded yet" in client.get("/settings").text

    result = client.get("/settings/backup.zip")
    assert result.headers["Content-Type"] == "application/zip"
    assert result.headers["Content-Disposition"].startswith('attachment; filename="bulletin-backup-')
    with zipfile.ZipFile(io.BytesIO(result.body)) as archive:
        assert f"sundays/{DAY}/manual.yaml" in archive.namelist()

    assert "download a backup" not in client.get("/").text
    assert "Last downloaded on" in client.get("/settings").text


def test_no_backup_reminder_before_the_first_sunday(client):
    assert "download a backup" not in client.get("/").text


def test_the_parish_name_heads_every_page(client):
    client.post("/settings/wording", {name: getattr(parish.original(), name) for name in web.WORDING} | {"site_name": "St. Anywhere"})
    assert '<a class="brand" href="/">St. Anywhere</a>' in client.get("/").text


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
    assert not (site / "state" / "sundays" / DAY).exists()
    assert locked.get("/login").status == 200
    assert locked.get("/static/style.css").status == 200


def test_settings_need_a_login(site, locked):
    assert locked.get("/settings").headers["Location"] == "/login?next=/settings"
    assert locked.get("/settings/backup.zip").status == 303
    assert locked.post("/settings/welcome", {"welcome_heading": "Hi"}).status == 303
    assert locked.post("/settings/logo", files={"logo": ("x.png", b"\x89PNG\r\n\x1a\n")}).status == 303
    assert parish.load() == parish.original()


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
    assert not (site / "state" / "sundays" / DAY).exists()


def test_without_a_password_only_this_computer_is_served(site, client, locked):
    # a page whose own name was pointed at 127.0.0.1 (DNS rebinding) sends its name as the Host
    result = client.post(f"/sundays/{DAY}/details", details_form(hymn_title=["x"]), HTTP_HOST="attacker.example:8000")
    assert result.status == 403
    assert not (site / "state" / "sundays" / DAY).exists()
    for host in ("localhost:8000", "127.0.0.1", "[::1]:8000", "LOCALHOST"):
        assert client.request("GET", "/", HTTP_HOST=host).status == 200, host
    # with a password, the server is meant to be reached under any name
    assert locked.request("GET", "/login", HTTP_HOST="bulletin.example.org").status == 200


def test_oversized_forms_are_refused(client):
    result = client.post(f"/sundays/{DAY}/readings", {"gospel_text": "x" * (web.MAX_BODY_BYTES + 1)})
    assert result.status == 413
