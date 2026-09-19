"""web and url routes (§8.5, §8.6): search, read pages, pick the passages that matter."""

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

import httpx
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi

from rica.context.evidence import Evidence, render
from rica.nodes.understand import Plan
from rica.retrieval.search import Chunk
from rica.web import searx
from rica.web.cache import NEWS_PAGE_TTL, PAGE_TTL, SEARCH_TTL, WebCache
from rica.web.fetch import FetchError, Page, fetch_page, new_client

log = logging.getLogger(__name__)

MAX_RESULTS = 8
MAX_USER_URLS = 3
SNIPPET_WEIGHT = 0.3  # snippets rank below page passages
SKIP_DOMAINS = {
    "youtube.com", "youtu.be", "tiktok.com", "instagram.com", "facebook.com", "x.com",
    "twitter.com", "pinterest.com", "linkedin.com",
}
_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    encoding_name="o200k_base", chunk_size=400, chunk_overlap=40
)
_WORD = re.compile(r"\w+")


@dataclass
class UrlNote:
    url: str
    reason: str  # blocked, failed, unsupported, empty
    detail: str


@dataclass
class WebTools:
    searxng_url: str
    cache: WebCache
    pages_to_read: int = 3


def _domain(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.").removeprefix("m.")


def _norm_url(url: str) -> str:
    p = urlsplit(url)
    return f"{p.scheme}://{p.netloc.lower()}{p.path.rstrip('/')}{'?' + p.query if p.query else ''}"


def _bm25_scores(query: str, texts: list[str]) -> list[float]:
    """0..1 relevance of each text to the query."""
    docs = [_WORD.findall(t.lower()) for t in texts]
    if not docs or not any(docs):
        return [0.0] * len(texts)
    scores = BM25Okapi(docs).get_scores(_WORD.findall(query.lower()))
    top = max(scores) if len(scores) and max(scores) > 0 else 1.0
    return [max(float(s), 0.0) / top for s in scores]


def page_chunks(page: Page, query: str, weight: float = 1.0, position_prior: float = 0.0) -> list[Chunk]:
    parts = _splitter.split_text(page.text)
    rel = _bm25_scores(query, parts)
    n = max(len(parts), 1)
    date, label = (page.published, "published") if page.published else (page.fetched, "fetched")
    return [
        Chunk(
            doc_id=page.url, source=page.url, title=page.title, heading_path="", chunk_index=i,
            text=text, updated_at=date, origin="web", date_label=label,
            score=weight * (rel[i] + position_prior * (1 - i / n)),
        )
        for i, text in enumerate(parts)
    ]


async def _cached_page(http: httpx.AsyncClient, cache: WebCache, url: str, news: bool) -> Page:
    key = f"page:{url}"
    if hit := cache.get(key):
        return Page(**hit)
    page = await fetch_page(http, url)
    cache.put(key, page.__dict__, NEWS_PAGE_TTL if news else PAGE_TTL)
    return page


async def _cached_search(tools: WebTools, http: httpx.AsyncClient, q: str, recency: str, news: bool) -> list[searx.Result]:
    key = "search:" + json.dumps([q, recency, news])
    if hit := tools.cache.get(key):
        return [searx.Result(**{**r, "engines": tuple(r["engines"])}) for r in hit]
    results = await searx.search(http, tools.searxng_url, q, recency, news)
    tools.cache.put(key, [r.__dict__ for r in results], SEARCH_TTL)
    return results


def merge_results(lists: list[list[searx.Result]], limit: int = MAX_RESULTS) -> list[searx.Result]:
    """Round-robin across queries, dropping duplicate URLs and video/social sites."""
    seen, out = set(), []
    for rank in range(max((len(l) for l in lists), default=0)):
        for results in lists:
            if rank >= len(results):
                continue
            r = results[rank]
            key = _norm_url(r.url)
            if key in seen or _domain(r.url) in SKIP_DOMAINS or not r.url.startswith(("http://", "https://")):
                continue
            seen.add(key)
            out.append(r)
    return out[:limit]


async def web_search(tools: WebTools, plan: Plan) -> tuple[list[Chunk], str]:
    """Returns (chunks, status) with status found / not_found / error."""
    queries = (plan.search_queries or [plan.standalone_query])[:3]
    news = plan.recency in ("day", "week")
    # General search (with the time range) is the main source; SearXNG's news category
    # only has Bing News here, so it adds one extra search for the first query.
    searches = [(q, False) for q in queries] + ([(queries[0], True)] if news else [])
    async with httpx.AsyncClient() as http:
        lists = await asyncio.gather(
            *(_cached_search(tools, http, q, plan.recency, is_news) for q, is_news in searches),
            return_exceptions=True,
        )
    ok = [l for l in lists if not isinstance(l, BaseException)]
    for e in (l for l in lists if isinstance(l, BaseException)):
        log.warning("searxng search failed: %s: %s", type(e).__name__, e)
    if not ok:
        return [], "error"
    results = merge_results(ok)
    if not results:
        return [], "not_found"

    def snippet(k: int, r: searx.Result) -> Chunk:
        return Chunk(
            doc_id=r.url, source=r.url, title=r.title, heading_path="", chunk_index=0,
            text=r.snippet, updated_at=r.published, origin="web", date_label="published",
            score=SNIPPET_WEIGHT / (1 + 0.3 * k),
        )

    snippets = [snippet(k, r) for k, r in enumerate(results) if r.snippet]
    if plan.snippets_sufficient:
        return snippets, "found"

    to_read = results[: tools.pages_to_read]
    async with new_client() as http:
        pages = await asyncio.gather(
            *(_cached_page(http, tools.cache, r.url, news) for r in to_read), return_exceptions=True
        )
    chunks: list[Chunk] = []
    read = set()
    for k, (r, page) in enumerate(zip(to_read, pages)):
        if isinstance(page, BaseException):
            log.info("could not read %s: %s", r.url, page)
            continue
        read.add(r.url)
        chunks += page_chunks(page, plan.standalone_query, weight=1 / (1 + 0.3 * k))
    chunks += [s for s in snippets if s.source not in read]
    return chunks, "found"


async def read_urls(tools: WebTools, urls: list[str], query: str) -> tuple[list[Chunk], list[UrlNote]]:
    chunks: list[Chunk] = []
    notes: list[UrlNote] = []
    async with new_client() as http:
        pages = await asyncio.gather(
            *(_cached_page(http, tools.cache, u, False) for u in urls[:MAX_USER_URLS]), return_exceptions=True
        )
    for url, page in zip(urls, pages):
        if isinstance(page, FetchError):
            notes.append(UrlNote(url, page.reason, page.detail))
        elif isinstance(page, BaseException):
            log.warning("reading %s failed: %s", url, page)
            notes.append(UrlNote(url, "failed", type(page).__name__))
        else:
            # The start of a page matters for "summarize this", so it gets a position prior
            chunks += page_chunks(page, query, position_prior=0.5)
    return chunks, notes


URL_NOTE_TEXT = {
    "blocked": "This address can't be opened: it points to a private or internal network, or isn't http(s).",
    "failed": "The page couldn't be loaded ({detail}).",
    "unsupported": "This isn't a web page RICA can read yet ({detail}).",
    "empty": "No readable text was found; the page may need JavaScript.",
}


def web_context(status: str | None, packed: list[Evidence], now: datetime) -> str:
    if status is None:
        return ""
    if status == "error":
        return '<web_search status="error">Web search is unavailable right now. Say so.</web_search>'
    if status == "not_found" or not packed:
        return '<web_search status="no results">The web search found nothing useful. Say so.</web_search>'
    return f"Web search results (searched {now:%Y-%m-%d}):\n\n{render(packed)}"


def url_context(notes: list[UrlNote], packed: list[Evidence], name: str) -> str:
    parts = []
    if packed:
        parts.append(f"Pages from the links {name} sent:\n\n{render(packed)}")
    for n in notes:
        text = URL_NOTE_TEXT[n.reason].format(detail=n.detail)
        parts.append(f'<url_read url="{n.url}" status="{n.reason}">{text} Tell {name}.</url_read>')
    return "\n\n".join(parts)
