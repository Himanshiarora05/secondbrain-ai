"""Offline checks for website link ingestion (no network, no DB, no LLM).

Every socket connect and DNS lookup is replaced with one that fails the test,
DNS answers come from a patched url_safety._lookup, and HTTP responses come
from an httpx.MockTransport.

Run from backend/:  .venv/Scripts/python.exe tests/test_website_ingestion.py
"""
import json
import os
import socket
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Never touch the real database or model hub.
os.environ.setdefault("DATABASE_URL", "postgresql://offline:offline@127.0.0.1:1/offline")
os.environ["HF_HUB_OFFLINE"] = "1"


def _no_network(*args, **kwargs):
    raise RuntimeError("network access attempted in an offline test")


socket.socket.connect = _no_network
socket.socket.connect_ex = _no_network
socket.create_connection = _no_network
socket.getaddrinfo = _no_network

import httpx
from fastapi import HTTPException

from types import SimpleNamespace

# The signed-in user the route functions are called for (routes take it from get_current_user).
TEST_USER = SimpleNamespace(id=1)

from app.services.web import url_safety
from app.services.web.errors import WebPageError
from app.services.web.url_safety import SafeNetworkBackend, check_url
from app.services.web.web_service import WebService, normalize_url, url_key, MAX_PAGE_BYTES
from app.services.ai import summary_service
from app.services import search_service
from app.api import upload
from app.routes import study
from app.models.document import Document
from app.models.summary import Summary

PUBLIC_IP = "93.184.216.34"

ARTICLE_HTML = b"""<!doctype html><html><head>
<title>Photosynthesis Explained | BioSite</title>
<meta property="og:title" content="Photosynthesis Explained">
<meta property="og:site_name" content="BioSite"></head>
<body>
<nav><ul><li><a href="/">Home</a></li><li><a href="/about">About</a></li><li>MENU-ITEM-XYZ</li></ul></nav>
<div class="cookie-banner">We use cookies COOKIE-BANNER-XYZ. Accept all.</div>
<aside class="ad">ADVERT-XYZ Buy cheap flights now!</aside>
<main><article><h1>Photosynthesis Explained</h1>
<p>Photosynthesis is the process by which green plants use sunlight to synthesise nutrients from carbon dioxide and water. It takes place mainly in the chloroplasts of leaf cells.</p>
<p>The light-dependent reactions happen in the thylakoid membranes, where chlorophyll absorbs light energy and splits water molecules, releasing oxygen as a by-product.</p>
<p>The Calvin cycle then uses ATP and NADPH from the light reactions to fix carbon dioxide into glucose in the stroma of the chloroplast.</p>
</article></main>
<footer>FOOTER-XYZ Copyright 2026 BioSite. All rights reserved.</footer>
</body></html>"""

JS_ONLY_HTML = b"""<!doctype html><html><head><title>App</title>
<script src="/static/runtime.js"></script><script src="/static/vendor.js"></script></head>
<body><noscript>You need to enable JavaScript to run this app.</noscript>
<div id="root"></div><script src="/static/main.js"></script></body></html>"""

LOGIN_HTML = b"""<!doctype html><html><head><title>Sign in</title></head><body>
<form action="/session" method="post"><label>Email <input type="email" name="email"></label>
<label>Password <input type="password" name="password"></label><button>Sign in</button></form>
</body></html>"""

NAV_ONLY_HTML = b"""<!doctype html><html><head><title>Links</title></head><body>
<nav><a href="/a">Home</a> <a href="/b">Blog</a> <a href="/c">Contact</a></nav>
<footer>Copyright 2026</footer></body></html>"""

WIKI_HTML = b"""<!doctype html><html><head><title>Mitochondrial matrix - Wikipedia</title></head>
<body><div id="mw-content-text"><div class="mw-parser-output">
<p>The mitochondrial matrix is the space enclosed by the inner membrane of the mitochondrion.<sup id="cite_ref-1" class="reference"><a href="#cite_note-1">[1]</a></sup> It contains mitochondrial DNA, ribosomes, soluble enzymes, small organic molecules, nucleotide cofactors and inorganic ions.<sup class="reference"><a href="#cite_note-2">[2]</a></sup></p>
<p>The enzymes in the matrix drive the citric acid cycle, oxidative phosphorylation, pyruvate oxidation and the beta oxidation of fatty acids, which together supply most of the cell's ATP.<sup class="reference"><a href="#cite_note-3">[3]</a></sup></p>
<p>The matrix pH is about 7.8, higher than the intermembrane space, because protons are pumped out across the inner membrane by the electron transport chain.</p>
<h2 id="References">References</h2>
<div class="reflist"><ol class="references">
<li id="cite_note-1">REFLIST-XYZ Alberts B (2002). Molecular Biology of the Cell. Garland Science. ISBN 0-8153-3218-1.</li>
<li id="cite_note-2">REFLIST-XYZ Voet D, Voet JG (2011). Biochemistry. Wiley. doi:10.1000/xyz. PMID 12345.</li>
<li id="cite_note-3">REFLIST-XYZ Grivell LA, Pel HJ (1994). Protein synthesis in mitochondria. Mol. Biol. Rep. 19 (3): 183-194.</li>
</ol></div>
<div class="navbox"><table><tr><td>NAVBOX-XYZ Cell anatomy: Nucleus, Mitochondrion, Ribosome, Golgi apparatus</td></tr></table></div>
</div></div></body></html>"""

JS_NOTICE_HTML = b"""<!doctype html><html><head><title>Flowchart Maker and Online Diagram Software</title></head>
<body><div class="geBlock"><p>DiagramApp is free online diagram software. You can use it as a flowchart maker, network diagram software, to create UML online, as an ER diagram tool, to design database schema, to build BPMN online, as a circuit diagram maker, and more.</p>
<p>Please ensure JavaScript is enabled.</p></div></body></html>"""

CHALLENGE_HTML = b"""<!doctype html><html><head><title>Just a moment...</title></head>
<body><div id="challenge"><script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script></div></body></html>"""


# ─── helpers ───

def fake_dns(mapping=None):
    """Patch DNS: hosts in mapping get those addresses, everything else a public IP."""
    mapping = mapping or {}

    def lookup(host, port):
        answer = mapping.get(host, [PUBLIC_IP])
        if isinstance(answer, Exception):
            raise answer
        return answer

    return patch.object(url_safety, "_lookup", side_effect=lookup)


def html_response(body=ARTICLE_HTML, status=200, headers=None):
    return httpx.Response(status, headers={"content-type": "text/html; charset=utf-8", **(headers or {})}, content=body)


def mock_transport(routes):
    """routes: {url: response or callable(request)}. Records every requested URL."""
    seen = []

    def handler(request):
        url = str(request.url)
        seen.append(url)
        if url not in routes:
            raise AssertionError(f"unexpected request to {url}")
        route = routes[url]
        return route(request) if callable(route) else route

    return httpx.MockTransport(handler), seen


def expect_error(code, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except WebPageError as e:
        assert e.code == code, f"expected {code}, got {e.code}: {e.message}"
        return e
    raise AssertionError(f"expected WebPageError({code})")


def redirect(location, status=302):
    return httpx.Response(status, headers={"location": location})


# ─── URL validation and SSRF address checks ───

def test_normalize_url_adds_https_only_when_scheme_missing():
    assert normalize_url("  example.com/page ") == "https://example.com/page"
    assert normalize_url("http://example.com") == "http://example.com"
    assert normalize_url("javascript:alert(1)") == "javascript:alert(1)"


def test_rejects_bad_schemes_and_shapes():
    with fake_dns():
        for url in [
            "ftp://example.com/file",
            "file:///etc/passwd",
            "javascript:alert(1)",
            "gopher://example.com/",
            "https://",
            "https://user:pass@example.com/",
            "https://example.com:8080/",
            "http://example.com:22/",
            "https://exa mple.com/",
        ]:
            expect_error("invalid_url", check_url, url)


def test_blocks_local_and_private_addresses():
    blocked = [
        "http://localhost/",
        "http://LOCALHOST./",
        "http://foo.localhost/",
        "http://printer.local/",
        "http://metadata.google.internal/",
        "http://127.0.0.1/",
        "http://127.8.9.10/",
        "http://2130706433/",          # decimal 127.0.0.1
        "http://0x7f.1/",              # hex / short form
        "http://017700000001/",        # octal
        "http://0.0.0.0/",
        "http://10.0.0.1/",
        "http://172.16.5.4/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.64.0.1/",          # carrier-grade NAT
        "http://224.0.0.1/",
        "http://[::1]/",
        "http://[::]/",
        "http://[fc00::1]/",
        "http://[fe80::1]/",
        "http://[::ffff:127.0.0.1]/",  # IPv4-mapped
        "http://[::ffff:10.0.0.1]/",
        "http://[2002:7f00:1::]/",     # 6to4 wrapping 127.0.0.1
        "http://[64:ff9b::a00:1]/",    # NAT64 wrapping 10.0.0.1
    ]
    with fake_dns() as lookup:
        for url in blocked:
            expect_error("blocked_address", check_url, url)
        assert lookup.call_count == 0, "literal IPs and local names must be refused without DNS"


def test_allows_public_addresses():
    with fake_dns({"example.com": [PUBLIC_IP, "2606:2800:220:1:248:1893:25c8:1946"]}):
        check_url("https://example.com/article")
        check_url("http://93.184.216.34/")
        check_url("https://[2606:4700::1111]/")


def test_hostname_resolving_to_private_ip_is_blocked():
    with fake_dns({"intranet.example.com": ["10.20.30.40"], "mixed.example.com": [PUBLIC_IP, "127.0.0.1"],
                   "scoped.example.com": ["fe80::1%12"]}):
        expect_error("blocked_address", check_url, "https://intranet.example.com/")
        expect_error("blocked_address", check_url, "https://mixed.example.com/")
        expect_error("blocked_address", check_url, "https://scoped.example.com/")


def test_dns_failure_is_unreachable():
    with fake_dns({"no-such-host.example": socket.gaierror(11001, "getaddrinfo failed")}):
        expect_error("unreachable", check_url, "https://no-such-host.example/")


def test_network_backend_refuses_private_ip_before_connecting():
    backend = SafeNetworkBackend()
    backend._inner = MagicMock()
    with fake_dns({"rebind.example.com": ["192.168.0.10"]}):
        expect_error("blocked_address", backend.connect_tcp, "rebind.example.com", 443)
        expect_error("blocked_address", backend.connect_tcp, "93.184.216.34", 8080)
    backend._inner.connect_tcp.assert_not_called()


def test_network_backend_pins_the_checked_ip():
    backend = SafeNetworkBackend()
    backend._inner = MagicMock()
    with fake_dns({"example.com": [PUBLIC_IP]}):
        backend.connect_tcp("example.com", 443, timeout=5)
    args = backend._inner.connect_tcp.call_args[0]
    assert args[0] == PUBLIC_IP and args[1] == 443, args


def test_dns_rebinding_blocked_at_connect_time():
    """DNS answers public for the pre-check, then private at connect: the real transport must refuse."""
    answers = iter([[PUBLIC_IP], ["127.0.0.1"]])
    with patch.object(url_safety, "_lookup", side_effect=lambda h, p: next(answers)):
        expect_error("blocked_address", WebService.fetch_page, "https://rebind.example.com/")


# ─── Fetching: redirects, limits, status codes ───

def test_fetch_follows_safe_redirects_and_returns_final_url():
    transport, seen = mock_transport({
        "https://example.com/old": redirect("/new", 301),
        "https://example.com/new": redirect("https://www.example.com/article"),
        "https://www.example.com/article": html_response(),
    })
    with fake_dns():
        page = WebService.fetch_page("example.com/old", transport=transport)
    assert page.url == "https://www.example.com/article"
    assert page.html == ARTICLE_HTML
    assert len(seen) == 3


def test_redirect_to_private_address_is_blocked_before_request():
    transport, seen = mock_transport({"https://example.com/go": redirect("http://internal.example.com/admin")})
    with fake_dns({"internal.example.com": ["10.0.0.7"]}):
        expect_error("blocked_address", WebService.fetch_page, "https://example.com/go", transport=transport)
    assert seen == ["https://example.com/go"]


def test_redirect_to_metadata_ip_scheme_or_port_is_blocked():
    cases = [
        ("http://169.254.169.254/latest/meta-data/", "blocked_address"),
        ("ftp://example.com/file", "invalid_url"),
        ("https://example.com:8443/x", "invalid_url"),
        ("http://localhost/", "blocked_address"),
    ]
    for location, code in cases:
        transport, seen = mock_transport({"https://example.com/go": redirect(location)})
        with fake_dns():
            expect_error(code, WebService.fetch_page, "https://example.com/go", transport=transport)
        assert len(seen) == 1, location


def test_too_many_redirects():
    transport, _ = mock_transport({"https://example.com/loop": redirect("https://example.com/loop")})
    with fake_dns():
        expect_error("too_many_redirects", WebService.fetch_page, "https://example.com/loop", transport=transport)


def test_redirect_to_login_page_is_login_required():
    transport, _ = mock_transport({
        "https://example.com/private": redirect("https://example.com/users/sign-in?next=/private"),
    })
    with fake_dns():
        expect_error("login_required", WebService.fetch_page, "https://example.com/private", transport=transport)


def test_timeout():
    def slow(request):
        raise httpx.ReadTimeout("timed out", request=request)

    transport, _ = mock_transport({"https://example.com/slow": slow})
    with fake_dns():
        err = expect_error("timeout", WebService.fetch_page, "https://example.com/slow", transport=transport)
    assert err.status_code == 504


def test_connection_error_is_unreachable():
    def refuse(request):
        raise httpx.ConnectError("refused", request=request)

    transport, _ = mock_transport({"https://example.com/": refuse})
    with fake_dns():
        err = expect_error("unreachable", WebService.fetch_page, "https://example.com/", transport=transport)
    assert err.status_code == 502


def test_declared_oversized_page_is_refused_without_reading():
    def body():
        raise AssertionError("body should not be read")
        yield b""

    response = httpx.Response(
        200, headers={"content-type": "text/html", "content-length": str(MAX_PAGE_BYTES + 1)}, content=body()
    )
    transport, _ = mock_transport({"https://example.com/big": response})
    with fake_dns():
        err = expect_error("too_large", WebService.fetch_page, "https://example.com/big", transport=transport)
    assert err.status_code == 413


def test_streamed_oversized_page_is_cut_off():
    sent = []

    def body():
        for _ in range(100):
            sent.append(1)
            yield b"x" * (1024 * 1024)

    transport, _ = mock_transport({
        "https://example.com/huge": lambda r: httpx.Response(200, headers={"content-type": "text/html"}, content=body()),
    })
    with fake_dns():
        expect_error("too_large", WebService.fetch_page, "https://example.com/huge", transport=transport)
    assert len(sent) <= 6, f"read {len(sent)} MB before stopping"


def test_non_html_content_types():
    transport, _ = mock_transport({
        "https://example.com/paper.pdf": httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF-1.7"),
        "https://example.com/cat.png": httpx.Response(200, headers={"content-type": "image/png"}, content=b"\x89PNG"),
    })
    with fake_dns():
        err = expect_error("not_html", WebService.fetch_page, "https://example.com/paper.pdf", transport=transport)
        assert "PDF" in err.message
        expect_error("not_html", WebService.fetch_page, "https://example.com/cat.png", transport=transport)


def test_status_codes():
    cases = [
        (401, {}, "login_required"),
        (403, {}, "blocked"),
        (429, {}, "blocked"),
        (404, {}, "not_found"),
        (410, {}, "not_found"),
        (503, {"cf-mitigated": "challenge"}, "blocked"),
        (500, {}, "site_error"),
    ]
    for status, headers, code in cases:
        transport, _ = mock_transport({"https://example.com/p": html_response(b"<html></html>", status, headers)})
        with fake_dns():
            expect_error(code, WebService.fetch_page, "https://example.com/p", transport=transport)


def test_bot_challenge_page_with_200_is_blocked():
    transport, _ = mock_transport({"https://example.com/p": html_response(CHALLENGE_HTML)})
    with fake_dns():
        expect_error("blocked", WebService.fetch_page, "https://example.com/p", transport=transport)


# ─── Extraction ───

def test_extracts_main_article_and_title():
    article = WebService.extract_article(ARTICLE_HTML, "https://bio.example.com/photosynthesis")
    assert article.title == "Photosynthesis Explained"
    assert article.site_name == "BioSite"
    assert "Calvin cycle" in article.text and "thylakoid membranes" in article.text
    for junk in ("MENU-ITEM-XYZ", "COOKIE-BANNER-XYZ", "ADVERT-XYZ", "FOOTER-XYZ"):
        assert junk not in article.text, junk


def test_title_falls_back_to_url():
    html = ARTICLE_HTML.replace(b"<title>Photosynthesis Explained | BioSite</title>", b"").replace(
        b'<meta property="og:title" content="Photosynthesis Explained">', b""
    ).replace(b"<h1>Photosynthesis Explained</h1>", b"")
    article = WebService.extract_article(html, "https://bio.example.com/notes/photo/")
    assert article.title == "bio.example.com/notes/photo", article.title


def test_reference_lists_footnotes_and_navboxes_are_dropped():
    article = WebService.extract_article(WIKI_HTML, "https://en.wikipedia.org/wiki/Mitochondrial_matrix")
    assert "inner membrane of the mitochondrion" in article.text
    assert "matrix pH is about 7.8" in article.text
    for junk in ("REFLIST-XYZ", "NAVBOX-XYZ", "[1]", "[2]", "[3]", "PMID"):
        assert junk not in article.text, junk


def test_short_page_asking_for_javascript_is_javascript_required():
    expect_error("javascript_required", WebService.extract_article, JS_NOTICE_HTML, "https://app.example.com/")


def test_long_article_mentioning_javascript_is_kept():
    paragraphs = "".join(
        f"<p>Lesson {i}: to follow the interactive examples in this tutorial, enable JavaScript in your "
        f"browser settings and reload the page so that the code editor and output panel appear.</p>"
        for i in range(12)
    )
    html = f"<html><head><title>Intro to the DOM</title></head><body><article>{paragraphs}</article></body></html>"
    article = WebService.extract_article(html.encode(), "https://docs.example.com/dom")
    assert len(article.text) > 1000 and "enable JavaScript" in article.text


def test_unreadable_pages_get_specific_errors():
    expect_error("javascript_required", WebService.extract_article, JS_ONLY_HTML, "https://app.example.com/")
    expect_error("login_required", WebService.extract_article, LOGIN_HTML, "https://example.com/login")
    expect_error("no_text", WebService.extract_article, NAV_ONLY_HTML, "https://example.com/")
    expect_error("no_text", WebService.extract_article, b"", "https://example.com/")
    expect_error("blocked", WebService.extract_article, CHALLENGE_HTML, "https://example.com/")


# ─── Endpoint ───

def _call_upload(url, fetch_result=None, fetch_error=None, saved=()):
    """Call the endpoint with fetching and storage mocked; `saved` are existing website documents."""
    fetched = MagicMock(url="https://www.example.com/article", html=ARTICLE_HTML)
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = list(saved)
    with patch.object(upload.WebService, "fetch_page",
                      side_effect=fetch_error, return_value=fetch_result or fetched) as fetch, \
         patch.object(upload, "_store_document_and_chunks", return_value={"status": "stored"}) as store, \
         patch.object(upload, "logger"):
        result = upload.upload_website(upload.WebsiteUploadRequest(url=url), db=db, user=TEST_USER)
    return result, fetch, store


def _saved_doc(doc_id, source_url, original_url=None, filename="Saved page"):
    row = MagicMock(id=doc_id, source_url=source_url,
                    metadata_json=json.dumps({"original_url": original_url or source_url}))
    row.filename = filename
    return row


# ─── Duplicate detection ───

def test_url_key_treats_equivalent_links_as_the_same_page():
    same = [
        "https://en.wikipedia.org/wiki/Ohm%27s_law",
        "http://en.wikipedia.org/wiki/Ohm's_law",
        "en.wikipedia.org/wiki/Ohm's_law/",
        "https://EN.Wikipedia.org/wiki/Ohm%27s_law#History",
        "https://en.wikipedia.org:443/wiki/Ohm%27s_law?utm_source=x&fbclid=abc",
    ]
    keys = {url_key(u) for u in same}
    assert len(keys) == 1, keys
    assert url_key("https://www.example.com/a?b=2&a=1") == url_key("example.com/a?a=1&b=2")


def test_url_key_keeps_what_changes_the_page():
    assert url_key("https://example.com/Page") != url_key("https://example.com/page")  # path case
    assert url_key("https://example.com/item?id=1") != url_key("https://example.com/item?id=2")
    assert url_key("https://example.com/a") != url_key("https://other.example.com/a")
    assert url_key("https://example.com:8080/a") != url_key("https://example.com/a")
    assert url_key("") is None and url_key("https://") is None and url_key("http://[bad") is None


def _expect_duplicate(call, doc_id):
    try:
        call()
    except HTTPException as e:
        assert e.status_code == 409, e.status_code
        assert e.detail["document_id"] == doc_id and "already in your library" in e.detail["message"]
        return e
    raise AssertionError("expected a 409 duplicate error")


def test_duplicate_is_refused_before_fetching():
    saved = [_saved_doc(3, "https://en.wikipedia.org/wiki/Mitochondrial_matrix", filename="Mitochondrial matrix - Wikipedia")]
    # Any fetch raises AssertionError, which _expect_duplicate would not accept as a 409.
    e = _expect_duplicate(lambda: _call_upload("en.wikipedia.org/wiki/Mitochondrial_matrix/#Structure", saved=saved,
                                               fetch_error=AssertionError("must not fetch a known page")), 3)
    assert '"Mitochondrial matrix - Wikipedia"' in e.detail["message"]


def test_duplicate_of_the_originally_entered_link_is_refused():
    saved = [_saved_doc(4, "https://www.example.com/article", original_url="http://short.example/abc")]
    _expect_duplicate(lambda: _call_upload("http://short.example/abc", saved=saved), 4)


def test_duplicate_found_after_redirect_is_refused_before_storing():
    saved = [_saved_doc(5, "https://www.example.com/article")]
    stored = []
    with patch.object(upload, "_store_document_and_chunks", side_effect=lambda **kw: stored.append(kw)):
        # A different link that redirects (fetch returns final URL www.example.com/article).
        _expect_duplicate(lambda: _call_upload("https://bit.example/xyz", saved=saved), 5)
    assert not stored


def test_different_page_is_still_imported():
    saved = [_saved_doc(6, "https://www.example.com/other-article")]
    result, fetch, store = _call_upload("https://www.example.com/article", saved=saved)
    assert result == {"status": "stored"} and fetch.called and store.called


def test_endpoint_stores_website_document():
    result, fetch, store = _call_upload("  example.com/article  ")
    assert result == {"status": "stored"}
    fetch.assert_called_once_with("example.com/article")
    kwargs = store.call_args.kwargs
    assert kwargs["source_type"] == "website"
    assert kwargs["filename"] == "Photosynthesis Explained"
    assert kwargs["source_url"] == "https://www.example.com/article"
    assert kwargs["chunks"] and "Calvin cycle" in kwargs["content"]
    assert '"original_url": "example.com/article"' in kwargs["metadata_json"]


def test_endpoint_maps_errors_to_http():
    cases = [
        (WebPageError("blocked_address", "private", 400), 400),
        (WebPageError("too_large", "big", 413), 413),
        (WebPageError("timeout", "slow", 504), 504),
        (RuntimeError("boom"), 502),
    ]
    for error, status in cases:
        try:
            _call_upload("https://example.com/x", fetch_error=error)
        except HTTPException as e:
            assert e.status_code == status, (error, e.status_code)
            if isinstance(error, WebPageError):
                assert e.detail == error.message
            else:
                assert "boom" not in e.detail
        else:
            raise AssertionError(f"expected HTTPException for {error!r}")

    try:
        upload.upload_website(upload.WebsiteUploadRequest(url="   "), db=MagicMock(), user=TEST_USER)
    except HTTPException as e:
        assert e.status_code == 400
    else:
        raise AssertionError("empty URL should be rejected")


# ─── Linking back to the page ───

def test_search_returns_source_url_for_websites():
    from types import SimpleNamespace as NS
    rows = [
        (NS(content="web text", page_start=None, page_end=None, start_seconds=None),
         NS(filename="Photosynthesis Explained", source_type="website",
            source_url="https://www.example.com/article"), 0.1),
        (NS(content="video text", page_start=None, page_end=None, start_seconds=46),
         NS(filename="YouTube: abcdefghijk", source_type="youtube",
            source_url="https://www.youtube.com/watch?v=abcdefghijk"), 0.2),
    ]
    with patch.object(search_service, "nearest_chunks", return_value=rows), \
         patch.object(search_service, "get_embedding", return_value=[0.0]):
        results = search_service.search_similar_chunks(MagicMock(), "light reactions", TEST_USER.id)
    web, video = results
    assert web[2:] == ("Photosynthesis Explained", None, "website", "https://www.example.com/article", None)
    assert video[3] == "https://www.youtube.com/watch?v=abcdefghijk&t=46s" and video[4] == "youtube"


def test_append_source_link_escapes_title_and_url():
    out = summary_service.append_source_link(
        "## Notes\n- point\n", "Graphs [Part 1]", "https://en.wikipedia.org/wiki/Graph_(discrete_mathematics)"
    )
    assert out.endswith(
        "- point\n\n---\n\nSource: [Graphs \\[Part 1\\]](https://en.wikipedia.org/wiki/Graph_%28discrete_mathematics%29)"
    ), out


def test_website_summary_gets_source_line():
    doc = MagicMock(id=7, content="Some article text", source_type="website",
                    source_url="https://www.example.com/article")
    doc.filename = "Photosynthesis Explained"
    db = MagicMock()

    def query(model):
        q = MagicMock()
        q.filter.return_value.first.return_value = {Document: doc, Summary: None}.get(model)  # Document.id: the row lock
        return q

    db.query.side_effect = query
    db.refresh.side_effect = lambda obj: None
    with patch.object(study, "generate_summary", return_value="## Notes\n- point"):
        result = study.create_or_regenerate_summary(7, regenerate=False, db=db, user=TEST_USER)
    assert result["summary"].endswith(
        "Source: [Photosynthesis Explained](https://www.example.com/article)"
    ), result["summary"]


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
