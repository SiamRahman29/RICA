"""Docs retrieval modes (§8.4): facts, whole_doc, find_docs. Blocking; call via a thread."""

import logging
from collections.abc import Iterable
from dataclasses import dataclass, replace

from fastembed.rerank.cross_encoder import TextCrossEncoder
from qdrant_client import QdrantClient, models
from rapidfuzz import fuzz, process

from rica.retrieval.store import vector_store
from rica.settings import Settings

log = logging.getLogger(__name__)

RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"
HINT_CUTOFF = 75  # rapidfuzz WRatio
# Reranking costs ~0.1 s per candidate on this CPU, so candidate counts are below §8.4's 30/50
FACTS_CANDIDATES = 20
FIND_CANDIDATES = 30


@dataclass(frozen=True)
class Chunk:
    doc_id: str
    source: str
    title: str
    heading_path: str
    chunk_index: int
    text: str  # without the contextual "Doc: …" header
    updated_at: str | None
    score: float = 0.0
    neighbor: bool = False  # added for context, not matched itself

    @property
    def key(self) -> tuple[str, int]:
        return self.doc_id, self.chunk_index


def _chunk(payload: dict, score: float = 0.0) -> Chunk:
    md = payload["metadata"]
    text = payload["page_content"].split("\n\n", 1)[-1]
    return Chunk(
        doc_id=md["doc_id"], source=md["source"], title=md["title"], heading_path=md.get("heading_path", ""),
        chunk_index=md["chunk_index"], text=text, updated_at=md.get("updated_at"), score=score,
    )


def _match(key: str, value) -> models.FieldCondition:
    if isinstance(value, list):
        return models.FieldCondition(key=f"metadata.{key}", match=models.MatchAny(any=value))
    return models.FieldCondition(key=f"metadata.{key}", match=models.MatchValue(value=value))


class DocSearch:
    def __init__(self, settings: Settings):
        self.client = QdrantClient(url=settings.qdrant_url)
        self.collection = settings.qdrant_collection
        self.store = vector_store(settings, self.client)
        self.reranker = TextCrossEncoder(RERANK_MODEL, cache_dir=str(settings.fastembed_cache))
        self.threshold = settings.rerank_threshold

    # --- building blocks -------------------------------------------------

    def _filter(self, about_me: bool, *conds: models.FieldCondition) -> models.Filter | None:
        must = [*conds] + ([_match("kind", "about-me")] if about_me else [])
        return models.Filter(must=must) if must else None

    def hybrid(self, query: str, k: int, about_me: bool) -> list[Chunk]:
        docs = self.store.similarity_search(query, k=k, filter=self._filter(about_me))
        return [_chunk({"page_content": d.page_content, "metadata": d.metadata}) for d in docs]

    def rerank(self, query: str, chunks: list[Chunk]) -> list[Chunk]:
        if not chunks:
            return []
        texts = [f"{c.title} › {c.heading_path}\n{c.text}" for c in chunks]
        scores = self.reranker.rerank(query, texts)
        ranked = [replace(c, score=float(s)) for c, s in zip(chunks, scores)]
        return sorted(ranked, key=lambda c: c.score, reverse=True)

    def _scroll(self, flt: models.Filter) -> list[Chunk]:
        points, _ = self.client.scroll(self.collection, scroll_filter=flt, limit=1000, with_payload=True)
        return [_chunk(p.payload) for p in points]

    def neighbors(self, hits: Iterable[Chunk]) -> list[Chunk]:
        """chunk_index ± 1 of each hit, scored just below its parent."""
        have = {h.key for h in hits}
        wanted: dict[str, dict[int, float]] = {}
        for h in hits:
            for i in (h.chunk_index - 1, h.chunk_index + 1):
                if i >= 0 and (h.doc_id, i) not in have:
                    wanted.setdefault(h.doc_id, {})[i] = max(wanted.get(h.doc_id, {}).get(i, -1e9), h.score)
        out = []
        for doc_id, idx in wanted.items():
            for c in self._scroll(models.Filter(must=[_match("doc_id", doc_id), _match("chunk_index", list(idx))])):
                out.append(replace(c, score=idx[c.chunk_index], neighbor=True))
        return out

    def catalog(self, about_me: bool = False) -> list[Chunk]:
        """First chunk of every document (title, source, doc_id)."""
        return self._scroll(self._filter(about_me, _match("chunk_index", 0)))

    def quick_titles(self, query: str, k: int = 3) -> list[str]:
        """Nearest notes without reranking (~10 ms): routing hints for the planner."""
        seen, out = set(), []
        for c in self.hybrid(query, k * 2, False):
            if c.doc_id not in seen:
                seen.add(c.doc_id)
                where = f"{c.title} › {c.heading_path}" if c.heading_path and c.heading_path != c.title else c.title
                out.append(f"{where} ({c.source})")
        return out[:k]

    # --- modes ------------------------------------------------------------

    def facts(self, query: str, about_me: bool, top: int = 8) -> list[Chunk]:
        candidates = self.hybrid(query, FACTS_CANDIDATES, about_me)
        hits = [c for c in self.rerank(query, candidates)[:top] if c.score >= self.threshold]
        return hits + self.neighbors(hits) if hits else []

    def resolve_doc(self, hint: str | None, query: str, about_me: bool) -> str | None:
        if hint:
            choices = {c.doc_id: f"{c.title} {c.source}" for c in self.catalog(about_me)}
            best = process.extractOne(hint, choices, scorer=fuzz.WRatio, score_cutoff=HINT_CUTOFF)
            if best:
                return best[2]
        hits = self.rerank(query, self.hybrid(query, FACTS_CANDIDATES, about_me))
        return hits[0].doc_id if hits and hits[0].score >= self.threshold else None

    def whole_doc(self, hint: str | None, query: str, about_me: bool) -> list[Chunk]:
        doc_id = self.resolve_doc(hint, query, about_me)
        if not doc_id:
            return []
        # Scored so that the packer can keep the most relevant sections if the doc doesn't fit
        return self.rerank(query, self._scroll(models.Filter(must=[_match("doc_id", doc_id)])))

    def find_docs(self, query: str, about_me: bool, limit: int = 15) -> list[Chunk]:
        best: dict[str, Chunk] = {}
        for c in self.rerank(query, self.hybrid(query, FIND_CANDIDATES, about_me)):
            if c.score >= self.threshold and c.doc_id not in best:
                best[c.doc_id] = c
        return list(best.values())[:limit]
