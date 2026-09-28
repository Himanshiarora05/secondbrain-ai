"""
Website link ingestion: fetch a page safely and extract its main article text.

Fetching never lets httpx follow redirects or read proxy settings: every hop
is checked by url_safety.check_url() and every connection goes through
SafeNetworkBackend. Extraction uses trafilatura on the bytes we fetched
(never trafilatura's own downloader, which would skip those checks).
"""

import re
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin, urlsplit

import httpx
import trafilatura

from app.services.web.errors import WebPageError
from app.services.web.url_safety import SafeNetworkBackend, check_url

MAX_PAGE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_REDIRECTS = 5
TOTAL_TIMEOUT_SECONDS = 20
REQUEST_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MIN_TEXT_CHARS = 200
# Below this length, a page whose text asks the reader to enable JavaScript is
# treated as a JavaScript-only page (only its fallback notice was readable).
SHORT_PAGE_CHARS = 1000
MAX_TITLE_CHARS = 300

# An honest agent with a contact URL; sites like Wikipedia refuse generic or browser-imitating ones.
USER_AGENT = "SecondBrain/1.0 (study notes importer; +https://github.com/Himanshiarora05/secondbrain-ai)"
HTML_TYPES = {"text/html", "application/xhtml+xml"}

# Path segments that mean the site bounced us to a sign-in page.
_LOGIN_SEGMENTS = {"login", "log-in", "signin", "sign-in", "sign_in", "sso", "auth", "authenticate", "servicelogin"}
_NON_HTTP_SCHEME_RE = re.compile(r"^(javascript|data|mailto|file|ftp|about|blob|vbscript|tel):", re.IGNORECASE)

_PASSWORD_INPUT_RE = re.compile(r"<input[^>]+type\s*=\s*[\"']?password", re.IGNORECASE)
_EMPTY_APP_ROOT_RE = re.compile(
    r"<div[^>]+id\s*=\s*[\"'](root|app|__next|__nuxt|svelte|main-app)[\"'][^>]*>\s*</div>", re.IGNORECASE
)
_NOSCRIPT_JS_RE = re.compile(r"<noscript[^>]*>.{0,500}?javascript", re.IGNORECASE | re.DOTALL)
_ENABLE_JS_TEXT_RE = re.compile(
    r"(enable|turn on|activate|allow)\s+javascript"
    r"|javascript\s+(is\s+)?(enabled|required|disabled|must be enabled|is not enabled|needs to be enabled)",
    re.IGNORECASE,
)

# Reference lists, footnote markers and navigation boxes (Wikipedia/MediaWiki
# and pages using the ARIA doc-* roles). Removed before extraction so they don't
# end up in chunks, summaries and flashcards.
_PRUNE_XPATH = [
    "//sup[contains(@class,'reference')]",
    "//ol[contains(@class,'references')]",
    "//div[contains(@class,'reflist')]",
    "//*[contains(@class,'mw-references')]",
    "//*[@role='doc-bibliography']",
    "//*[@role='doc-endnotes']",
    "//*[@role='doc-noteref']",
    "//*[contains(@class,'navbox')]",
]
_CHALLENGE_MARKERS = (
    "<title>just a moment...</title>",
    "cf-browser-verification",
    "challenges.cloudflare.com",
    "attention required! | cloudflare",
    "cf-chl-",
    "captcha-delivery.com",
)


@dataclass
class FetchedPage:
    url: str  # final URL after redirects
    html: bytes


@dataclass
class Article:
    title: str
    text: str
    site_name: Optional[str]


def normalize_url(url: str) -> str:
    """Trim, and add https:// when the user left the scheme off ("example.com/page")."""
    url = url.strip()
    if url and "://" not in url and not _NON_HTTP_SCHEME_RE.match(url):
        url = "https://" + url
    return url


def _is_login_url(url: str) -> bool:
    segments = {s.lower() for s in urlsplit(url).path.split("/") if s}
    return bool(segments & _LOGIN_SEGMENTS)


def _is_challenge(resp: httpx.Response, body_start: str = "") -> bool:
    if resp.headers.get("cf-mitigated", "").lower() == "challenge":
        return True
    return any(marker in body_start for marker in _CHALLENGE_MARKERS)


def _check_status(resp: httpx.Response) -> None:
    status = resp.status_code
    if status < 400:
        return
    if status in (401, 407):
        raise WebPageError("login_required", "This page requires a login, so it can't be imported")
    if status in (404, 410):
        raise WebPageError("not_found", "This page could not be found (it may have been moved or deleted)")
    if status in (403, 429, 451, 999) or _is_challenge(resp):
        raise WebPageError(
            "blocked",
            "This website blocked access to the page. It may not allow automated access, or it may need a login",
        )
    if status >= 500:
        raise WebPageError(
            "site_error", f"The website returned an error (HTTP {status}). Please try again later", status_code=502
        )
    raise WebPageError("site_error", f"The website refused the request (HTTP {status})")


def _check_content_type(resp: httpx.Response) -> None:
    mime = resp.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not mime or mime in HTML_TYPES:
        return
    if mime == "application/pdf":
        raise WebPageError(
            "not_html", "This link is a PDF file, not a web page. Download it and upload it as a PDF instead"
        )
    raise WebPageError("not_html", f"This link points to a file ({mime}), not a web page")


def _read_limited(resp: httpx.Response, deadline: float) -> bytes:
    declared = resp.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_PAGE_BYTES:
        raise _too_large()

    body = bytearray()
    for chunk in resp.iter_bytes():
        body.extend(chunk)
        if len(body) > MAX_PAGE_BYTES:
            raise _too_large()
        if time.monotonic() > deadline:
            raise _timeout()
    return bytes(body)


def _too_large() -> WebPageError:
    return WebPageError(
        "too_large", f"This page is too large to import (maximum {MAX_PAGE_BYTES // (1024 * 1024)} MB)", status_code=413
    )


def _timeout() -> WebPageError:
    return WebPageError("timeout", "The website took too long to respond. Please try again later", status_code=504)


def _javascript_required() -> WebPageError:
    return WebPageError(
        "javascript_required",
        "This page only shows its content with JavaScript, so its text can't be read. "
        "Try a different page or save it as a PDF and upload that",
    )


def _make_client(transport: Optional[httpx.BaseTransport]) -> httpx.Client:
    if transport is None:
        transport = httpx.HTTPTransport(retries=0)
        # httpx has no public hook for this; the pool's backend opens every socket.
        transport._pool._network_backend = SafeNetworkBackend()
    return httpx.Client(
        transport=transport,
        follow_redirects=False,
        trust_env=False,  # never route through a proxy from the environment
        timeout=REQUEST_TIMEOUT,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
            "Accept-Language": "en;q=0.9,*;q=0.5",
        },
    )


class WebService:

    @staticmethod
    def fetch_page(url: str, transport: Optional[httpx.BaseTransport] = None) -> FetchedPage:
        """Fetch an HTML page, re-checking every redirect hop.

        `transport` is only for tests; the default transport enforces the
        address checks at connect time.

        Raises WebPageError with a user-facing message on any failure.
        """
        current = normalize_url(url)
        deadline = time.monotonic() + TOTAL_TIMEOUT_SECONDS

        with _make_client(transport) as client:
            for _ in range(MAX_REDIRECTS + 1):
                check_url(current)
                if time.monotonic() > deadline:
                    raise _timeout()
                try:
                    with client.stream("GET", current) as resp:
                        if resp.is_redirect:
                            location = resp.headers.get("location")
                            if not location:
                                raise WebPageError("site_error", "The website sent an invalid redirect")
                            current = urljoin(str(resp.url), location)
                            if _is_login_url(current):
                                raise WebPageError(
                                    "login_required", "This page requires a login, so it can't be imported"
                                )
                            continue

                        _check_status(resp)
                        _check_content_type(resp)
                        body = _read_limited(resp, deadline)
                        head = body[:4096].decode("utf-8", errors="replace").lower()
                        if _is_challenge(resp, head):
                            raise WebPageError(
                                "blocked",
                                "This website blocked access to the page with a bot check, so it can't be imported",
                            )
                        return FetchedPage(url=str(resp.url), html=body)
                except httpx.TimeoutException:
                    raise _timeout()
                except httpx.HTTPError:
                    raise WebPageError(
                        "unreachable", "Could not connect to this website. Please check the link", status_code=502
                    )

        raise WebPageError("too_many_redirects", "This link redirects too many times to be imported")

    @staticmethod
    def extract_article(html: bytes, url: str) -> Article:
        """Pull the main article text and title out of a page.

        Raises WebPageError when the page has no readable article text, with
        a more specific reason when it looks like a login wall or a page that
        only renders with JavaScript.
        """
        doc = trafilatura.bare_extraction(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            include_images=False,
            include_links=False,
            with_metadata=True,
            deduplicate=True,
            prune_xpath=_PRUNE_XPATH,
        )
        text = ((doc.text if doc else None) or "").strip()

        if len(text) < MIN_TEXT_CHARS:
            lower = html.decode("utf-8", errors="replace").lower()
            if any(marker in lower for marker in _CHALLENGE_MARKERS):
                raise WebPageError(
                    "blocked", "This website blocked access to the page with a bot check, so it can't be imported"
                )
            if _PASSWORD_INPUT_RE.search(lower):
                raise WebPageError("login_required", "This page requires a login, so it can't be imported")
            if (
                _EMPTY_APP_ROOT_RE.search(lower)
                or _NOSCRIPT_JS_RE.search(lower)
                or lower.count("<script") >= 5
            ):
                raise _javascript_required()
            raise WebPageError("no_text", "No readable article text was found on this page")

        # A short page whose readable text is a "please enable JavaScript" notice
        # (e.g. an app's meta blurb plus its <noscript> fallback) has no real content.
        if len(text) < SHORT_PAGE_CHARS and _ENABLE_JS_TEXT_RE.search(text):
            raise _javascript_required()

        title = " ".join(((doc.title if doc else None) or "").split())
        if not title:
            parts = urlsplit(url)
            title = f"{parts.hostname}{parts.path}".rstrip("/")
        site_name = " ".join(((doc.sitename if doc else None) or "").split()) or None

        return Article(title=title[:MAX_TITLE_CHARS], text=text, site_name=site_name)
