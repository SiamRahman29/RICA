"""SearXNG JSON search (§8.5 step 1)."""

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class Result:
    url: str
    title: str
    snippet: str
    published: str | None
    engines: tuple[str, ...]


async def search(client: httpx.AsyncClient, base_url: str, query: str, recency: str = "any", news: bool = False) -> list[Result]:
    params = {"q": query, "format": "json", "language": "en", "categories": "news" if news else "general"}
    if recency in ("day", "week", "month", "year"):
        params["time_range"] = recency
    resp = await client.get(f"{base_url}/search", params=params, timeout=10)
    resp.raise_for_status()
    out = []
    for r in resp.json().get("results", []):
        if not r.get("url"):
            continue
        date = (r.get("publishedDate") or "")[:10] or None
        out.append(Result(r["url"], r.get("title") or r["url"], r.get("content") or "", date, tuple(r.get("engines") or ())))
    return out
