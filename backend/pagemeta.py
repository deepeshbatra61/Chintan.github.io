"""Fetch a news page's headline, image and description, safely.

Used by the Chintan Desk when the owner pastes a link (and to find an image
for the top source when they type only a headline). This is the one place
the server opens a URL it didn't choose, so it is written as an SSRF
boundary, per /plan-eng-review 2026-09-28 (owner-approved, hardened):

    https only · no credentials in the URL · port 443
    every hostname resolved first; ANY non-public address → refused
    the connection goes to the IP we checked (no second DNS lookup to
    rebind), with TLS still verified against the real hostname (SNI)
    redirects followed by hand, max 3, each hop re-checked
    5 s total, 2 MB cap (only the first 512 KB is parsed: the <head>)
    text/html only · only og/twitter/title/description tags are read

Pure parts (URL checks, IP checks, HTML parsing) are separate from the
network shell so they can be tested without the internet.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from html.parser import HTMLParser
from typing import Awaitable, Callable, Optional
from urllib.parse import urljoin, urlsplit

import httpx

TIMEOUT_S = 5.0
MAX_BYTES = 2 * 1024 * 1024
PARSE_BYTES = 512 * 1024
MAX_REDIRECTS = 3
# A mainstream mobile-browser UA, not a bot UA: NDTV's CDN returns 403 to
# anything that looks like a crawler (verified 2026-09-28), and this is one
# page view on behalf of a person who pasted the link, like any link preview.
USER_AGENT = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36")


class Refused(Exception):
    """The URL or an address it resolves to is not allowed."""


# ── pure checks ───────────────────────────────────────────────────────────────

def check_url(url: str) -> tuple[str, str]:
    """(hostname, normalized_url) or raise Refused."""
    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        raise Refused("unparseable")
    if parts.scheme != "https":
        raise Refused("https only")
    if parts.username or parts.password:
        raise Refused("credentials in url")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise Refused("no host")
    try:
        port = parts.port
    except ValueError:
        raise Refused("bad port")
    if port not in (None, 443):
        raise Refused("port")
    # An IP literal is checked like any resolved address; a bare single-label
    # name ("localhost", "metadata") never belongs to a news site.
    if "." not in host and ":" not in host:
        raise Refused("single-label host")
    return host, parts.geturl()


def ip_is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not (addr.is_multicast or addr.is_reserved or addr.is_loopback
                                   or addr.is_link_local or addr.is_private or addr.is_unspecified)


def pick_public_ip(addresses: list[str]) -> str:
    """ALL resolved addresses must be public (a mixed answer is how a
    rebinding attack hedges), then the first is used."""
    if not addresses:
        raise Refused("no address")
    for a in addresses:
        if not ip_is_public(a):
            raise Refused("non-public address")
    return addresses[0]


class _MetaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.title = ""
        self._in_title = False
        self.done = False

    def handle_starttag(self, tag, attrs):
        if self.done:
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").strip().lower()
            if key and "content" in a and key not in self.meta:
                self.meta[key] = a["content"].strip()
        elif tag == "title":
            self._in_title = True
        elif tag == "body":
            self.done = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "head":
            self.done = True

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()


def _clean(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text[:limit].rsplit(" ", 1)[0] + "…" if len(text) > limit else text


def parse_meta(html: str, page_url: str) -> dict:
    """{title, image, description, site_name, published_time} from a page's
    head. The image is made absolute and kept only if it is https."""
    p = _MetaParser()
    try:
        p.feed(html or "")
    except Exception:
        pass
    m = p.meta
    title = m.get("og:title") or m.get("twitter:title") or p.title
    image = m.get("og:image:secure_url") or m.get("og:image") or m.get("twitter:image") or ""
    if image:
        image = urljoin(page_url, image)
        if urlsplit(image).scheme != "https" or len(image) > 600 or any(c.isspace() for c in image):
            image = ""
    return {
        "title": _clean(title, 200),
        "image": image,
        "description": _clean(m.get("og:description") or m.get("description") or m.get("twitter:description") or "", 600),
        "site_name": _clean(m.get("og:site_name") or "", 80),
        "published_time": (m.get("article:published_time") or "")[:40],
    }


# ── network shell ─────────────────────────────────────────────────────────────

Resolver = Callable[[str], Awaitable[list[str]]]


async def system_resolve(host: str) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(i[4][0] for i in infos))


async def _fetch_once(client: httpx.AsyncClient, url: str, resolve: Resolver) -> tuple[Optional[str], Optional[bytes], str]:
    """(redirect_location, body, final_url) for one hop."""
    host, url = check_url(url)
    try:
        literal = ipaddress.ip_address(host)
        ip = str(literal)
        if not ip_is_public(ip):
            raise Refused("non-public address")
    except ValueError:
        ip = pick_public_ip(await resolve(host))

    parts = urlsplit(url)
    ip_host = f"[{ip}]" if ":" in ip else ip
    pinned = parts._replace(netloc=ip_host).geturl()
    req = client.build_request(
        "GET", pinned,
        headers={"Host": host, "User-Agent": USER_AGENT, "Accept": "text/html"},
        extensions={"sni_hostname": host},
    )
    resp = await client.send(req, stream=True)
    try:
        if resp.status_code in (301, 302, 303, 307, 308):
            loc = resp.headers.get("location")
            if not loc:
                raise Refused("redirect without location")
            return urljoin(url, loc), None, url
        if resp.status_code != 200:
            raise Refused(f"status {resp.status_code}")
        ctype = resp.headers.get("content-type", "").lower()
        if "text/html" not in ctype and "application/xhtml" not in ctype:
            raise Refused("not html")
        declared = resp.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_BYTES:
            raise Refused("too large")
        body = bytearray()
        async for chunk in resp.aiter_bytes():
            body.extend(chunk)
            if len(body) >= PARSE_BYTES:
                break
            if len(body) > MAX_BYTES:
                raise Refused("too large")
        return None, bytes(body), url
    finally:
        await resp.aclose()


async def fetch_meta(url: str, resolve: Resolver = system_resolve, transport=None) -> Optional[dict]:
    """Page metadata, or None if the URL is refused or unreachable. Never
    raises: a failed lookup must degrade to 'no image', not break a draft."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S, follow_redirects=False, transport=transport,
                                     verify=True) as client:
            async def run():
                current = url
                for _ in range(MAX_REDIRECTS + 1):
                    nxt, body, final = await _fetch_once(client, current, resolve)
                    if nxt is None:
                        html = body.decode("utf-8", errors="replace")
                        return {**parse_meta(html, final), "url": final}
                    current = nxt
                raise Refused("too many redirects")
            return await asyncio.wait_for(run(), timeout=TIMEOUT_S)
    except (Refused, httpx.HTTPError, asyncio.TimeoutError, OSError, ValueError):
        return None


def looks_like_url(text: str) -> bool:
    t = (text or "").strip()
    return t.lower().startswith(("https://", "http://")) and " " not in t
