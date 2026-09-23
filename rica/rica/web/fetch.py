"""Page fetching with an SSRF guard (§8.6).

Every hop (including redirects) is resolved here and must point only to public addresses.
The request then goes to the checked IP, with the original hostname as SNI and Host header,
so DNS can't be swapped between the check and the connection (rebinding).
"""

import asyncio
import ipaddress
import logging
import re
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
import trafilatura

log = logging.getLogger(__name__)

TIMEOUT = 8.0
MAX_REDIRECTS = 5
MAX_BYTES = 2 * 1024 * 1024
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"
)
HTML_TYPES = ("text/html", "application/xhtml+xml")
# Wikipedia-style reference markers survive extraction, and the answer model copies them
# straight into its text, where they collide with RICA's own [n] citation ids — [9] may
# not exist, or worse, may point at unrelated evidence. Wikipedia emits them as
# <sup>[1]</sup> (left alone when the <sup> holds anything else, e.g. an exponent);
# other sites attach them to the prose as "opened in 2022.[9]".
SUP_MARKER = re.compile(r"\s*<sup>(?:\[\d{1,3}\])+</sup>")
REF_MARKER = re.compile(r"""(?<=[\w.,;:!?"')\]])\[\d{1,3}\]""")
# Code keeps its brackets, so `items[0]` survives. Indented blocks are not detected;
# trafilatura's markdown fences the code it recognises.
CODE_SPAN = re.compile(r"```.*?```|`[^`\n]*`", re.S)


class FetchError(Exception):
    """reason is shown to the model: blocked, failed, unsupported, empty."""

    def __init__(self, reason: str, detail: str):
        super().__init__(f"{reason}: {detail}")
        self.reason, self.detail = reason, detail


@dataclass(frozen=True)
class Page:
    url: str  # final URL after redirects
    title: str
    text: str  # markdown
    published: str | None  # YYYY-MM-DD if the page says
    fetched: str  # YYYY-MM-DD


async def resolve_public(host: str, port: int) -> str:
    """Returns a public IP for host, or raises FetchError('blocked')."""
    try:
        ip = ipaddress.ip_address(host)
        addrs = [ip]
    except ValueError:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as e:
            raise FetchError("failed", f"can't resolve {host}") from e
        addrs = [ipaddress.ip_address(i[4][0]) for i in infos]
    # All addresses must be public: a name that resolves to both is suspicious
    bad = [a for a in addrs if not a.is_global or a.is_multicast]
    if not addrs or bad:
        raise FetchError("blocked", f"{host} resolves to a non-public address")
    return str(addrs[0])


def _check_scheme(url: str) -> tuple[str, str, int]:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FetchError("blocked", "only http(s) URLs can be read")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    return parts.scheme, parts.hostname, port


async def fetch_html(client: httpx.AsyncClient, url: str) -> tuple[str, str]:
    """Returns (final_url, html)."""
    for _ in range(MAX_REDIRECTS + 1):
        scheme, host, port = _check_scheme(url)
        ip = await resolve_public(host, port)
        parts = urlsplit(url)
        netloc_ip = f"[{ip}]" if ":" in ip else ip
        if parts.port:
            netloc_ip += f":{parts.port}"
        target = urlunsplit(parts._replace(netloc=netloc_ip))
        headers = {"Host": parts.netloc.rsplit("@", 1)[-1], "User-Agent": USER_AGENT, "Accept": "text/html,*/*;q=0.5"}
        req = client.build_request("GET", target, headers=headers, extensions={"sni_hostname": host})
        resp = await client.send(req, stream=True)
        try:
            if resp.status_code in (301, 302, 303, 307, 308) and "location" in resp.headers:
                url = urljoin(url, resp.headers["location"])
                continue
            if resp.status_code >= 400:
                raise FetchError("failed", f"HTTP {resp.status_code}")
            ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
            if ctype and ctype not in HTML_TYPES:
                raise FetchError("unsupported", f"{ctype or 'unknown'} content (only web pages can be read for now)")
            body = bytearray()
            async for part in resp.aiter_bytes():
                body += part
                if len(body) >= MAX_BYTES:
                    break
            return url, body.decode(resp.encoding or "utf-8", errors="replace")
        finally:
            await resp.aclose()
    raise FetchError("failed", "too many redirects")


def strip_ref_markers(text: str) -> str:
    """Drops footnote markers like [9] from prose, leaving code spans untouched."""
    def clean(s: str) -> str:
        return REF_MARKER.sub("", SUP_MARKER.sub("", s))

    out, last = [], 0
    for m in CODE_SPAN.finditer(text):
        out.append(clean(text[last : m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(clean(text[last:]))
    return "".join(out)


def extract(url: str, html: str) -> Page:
    text = trafilatura.extract(html, url=url, output_format="markdown", include_links=False, include_tables=True)
    if not text or len(text) < 200:
        raise FetchError("empty", "no readable text (the page may need JavaScript)")
    meta = trafilatura.extract_metadata(html, default_url=url)
    return Page(
        url=url,
        title=(meta.title if meta and meta.title else urlsplit(url).hostname or url),
        text=strip_ref_markers(text),
        published=(meta.date if meta and meta.date else None),
        fetched=datetime.now(UTC).date().isoformat(),
    )


def new_client() -> httpx.AsyncClient:
    # Redirects are followed by hand so that every hop passes the SSRF check
    return httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False, http2=False)


async def fetch_page(client: httpx.AsyncClient, url: str) -> Page:
    try:
        final_url, html = await asyncio.wait_for(fetch_html(client, url), TIMEOUT * 2)
    except FetchError:
        raise
    except (httpx.HTTPError, asyncio.TimeoutError) as e:
        raise FetchError("failed", type(e).__name__) from e
    return await asyncio.to_thread(extract, final_url, html)
