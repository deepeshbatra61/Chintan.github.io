"""pagemeta: the Desk's SSRF boundary. Every internal-address trick that
should be refused, plus the happy path, without touching the internet
(httpx MockTransport + a fake resolver)."""

import pytest

httpx = pytest.importorskip("httpx")
import pagemeta as P  # noqa: E402

HEAD = """<html><head><title>Plain title</title>
<meta property="og:title" content="SC strikes down electoral bonds">
<meta property="og:image" content="/img/lead.jpg">
<meta name="description" content="The court ordered disclosure.">
<meta property="og:site_name" content="The Hindu">
</head><body><meta property="og:title" content="IGNORED body tag"></body></html>"""


# ─────────────────────── pure ───────────────────────

@pytest.mark.parametrize("url", [
    "http://thehindu.com/x", "ftp://thehindu.com/x", "https://user:pw@thehindu.com/x",
    "https://thehindu.com:8443/x", "https://localhost/x", "https://metadata/x", "javascript:alert(1)", "",
])
def test_refused_urls(url):
    with pytest.raises(P.Refused):
        P.check_url(url)


def test_allowed_url():
    assert P.check_url("https://www.TheHindu.com/news/x?a=1")[0] == "www.thehindu.com"


@pytest.mark.parametrize("ip", [
    "127.0.0.1", "10.0.0.5", "172.16.3.4", "192.168.1.1", "169.254.169.254", "0.0.0.0",
    "100.64.0.1", "::1", "fe80::1", "fc00::1", "::ffff:127.0.0.1", "::ffff:169.254.169.254", "224.0.0.1",
])
def test_non_public_ips(ip):
    assert not P.ip_is_public(ip)


def test_public_ips():
    assert P.ip_is_public("104.18.2.3") and P.ip_is_public("2606:4700::1111")


def test_mixed_dns_answer_is_refused():
    with pytest.raises(P.Refused):
        P.pick_public_ip(["104.18.2.3", "10.0.0.1"])
    with pytest.raises(P.Refused):
        P.pick_public_ip([])


def test_parse_meta_prefers_og_and_absolutizes_image():
    m = P.parse_meta(HEAD, "https://www.thehindu.com/news/a.html")
    assert m == {"title": "SC strikes down electoral bonds", "image": "https://www.thehindu.com/img/lead.jpg",
                 "description": "The court ordered disclosure.", "site_name": "The Hindu", "published_time": ""}


def test_parse_meta_drops_http_images_and_falls_back_to_title():
    m = P.parse_meta('<head><title> T </title><meta property="og:image" content="http://x.com/a.jpg"></head>',
                     "https://x.com/")
    assert m["title"] == "T" and m["image"] == ""


def test_parse_meta_survives_garbage():
    assert P.parse_meta("<<<>>>", "https://x.com")["title"] == ""


def test_looks_like_url():
    assert P.looks_like_url("https://ndtv.com/a") and not P.looks_like_url("Asian Games medal tally")


# ─────────────────────── network shell ───────────────────────

def _resolver(table):
    async def resolve(host):
        return table[host]
    return resolve


async def test_happy_path_connects_to_checked_ip_with_host_and_sni():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["host"] = request.headers["host"]
        seen["sni"] = request.extensions.get("sni_hostname")
        return httpx.Response(200, headers={"content-type": "text/html"}, text=HEAD)

    m = await P.fetch_meta("https://www.thehindu.com/news/a.html",
                           resolve=_resolver({"www.thehindu.com": ["104.18.2.3"]}),
                           transport=httpx.MockTransport(handler))
    assert m["title"] == "SC strikes down electoral bonds"
    assert seen["url"].startswith("https://104.18.2.3/") and seen["host"] == "www.thehindu.com"
    assert seen["sni"] == "www.thehindu.com"


async def test_dns_pointing_inside_is_refused_before_any_request():
    calls = []
    m = await P.fetch_meta("https://evil.example.com/x",
                           resolve=_resolver({"evil.example.com": ["169.254.169.254"]}),
                           transport=httpx.MockTransport(lambda r: calls.append(r) or httpx.Response(200)))
    assert m is None and calls == []


async def test_redirect_into_private_network_is_refused():
    def handler(request):
        if request.headers["host"] == "good.example.com":
            return httpx.Response(302, headers={"location": "https://internal.example.com/admin"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=HEAD)

    m = await P.fetch_meta("https://good.example.com/x",
                           resolve=_resolver({"good.example.com": ["104.18.2.3"], "internal.example.com": ["10.0.0.7"]}),
                           transport=httpx.MockTransport(handler))
    assert m is None


async def test_redirect_to_http_is_refused():
    m = await P.fetch_meta("https://good.example.com/x",
                           resolve=_resolver({"good.example.com": ["104.18.2.3"]}),
                           transport=httpx.MockTransport(lambda r: httpx.Response(301, headers={"location": "http://good.example.com/y"})))
    assert m is None


async def test_redirect_loop_stops():
    m = await P.fetch_meta("https://a.example.com/x",
                           resolve=_resolver({"a.example.com": ["104.18.2.3"]}),
                           transport=httpx.MockTransport(lambda r: httpx.Response(302, headers={"location": "/again"})))
    assert m is None


async def test_non_html_and_oversize_are_refused():
    res = _resolver({"a.example.com": ["104.18.2.3"]})
    pdf = await P.fetch_meta("https://a.example.com/x", resolve=res,
                             transport=httpx.MockTransport(lambda r: httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")))
    big = await P.fetch_meta("https://a.example.com/x", resolve=res,
                             transport=httpx.MockTransport(lambda r: httpx.Response(200, headers={"content-type": "text/html", "content-length": str(P.MAX_BYTES + 1)}, text="x")))
    assert pdf is None and big is None


async def test_ip_literal_inside_is_refused():
    assert await P.fetch_meta("https://127.0.0.1/x", transport=httpx.MockTransport(lambda r: httpx.Response(200))) is None


async def test_parse_stops_reading_after_head_budget():
    body = "<html><head><title>T</title></head><body>" + "x" * (P.PARSE_BYTES * 3) + "</body></html>"
    m = await P.fetch_meta("https://a.example.com/x", resolve=_resolver({"a.example.com": ["104.18.2.3"]}),
                           transport=httpx.MockTransport(lambda r: httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"}, text=body)))
    assert m["title"] == "T"
