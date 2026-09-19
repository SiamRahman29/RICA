"""Evidence packing per rung budget, <doc> rendering, and the Sources list (§6.6, §8.1)."""

import re
from dataclasses import dataclass
from html import escape

from rica.context import tokens
from rica.retrieval.search import Chunk

TAG_OVERHEAD = 30  # tokens for the <doc …> wrapper
_CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
# gpt-oss cites in its native browsing style: 【1】, 【1†L5-L6】, 【1, 2】
_OSS_CITATION = re.compile(r"【(\d+(?:\s*,\s*\d+)*)(?:†[^】]*)?】")
_OSS_MAX = 40  # longest bracket we wait for before giving up


class CitationNormalizer:
    """Rewrites 【n…】 citations to [n] in a token stream, holding back partial brackets."""

    def __init__(self):
        self._buf = ""

    def feed(self, piece: str) -> str:
        self._buf += piece
        out = []
        while (i := self._buf.find("【")) != -1:
            out.append(self._buf[:i])
            self._buf = self._buf[i:]
            j = self._buf.find("】")
            if j == -1:
                if len(self._buf) <= _OSS_MAX:
                    return "".join(out)  # wait for the closing bracket
                j = len(self._buf) - 1
            out.append(_OSS_CITATION.sub(r"[\1]", self._buf[: j + 1]))
            self._buf = self._buf[j + 1 :]
        out.append(self._buf)
        self._buf = ""
        return "".join(out)

    def flush(self) -> str:
        rest, self._buf = self._buf, ""
        return rest


@dataclass(frozen=True)
class Evidence:
    id: int
    source: str  # "doc" | "web"
    title: str
    locator: str  # "about/people.md › Family" or a URL
    text: str
    date: str | None
    date_label: str = "updated"


def join_overlapping(a: str, b: str) -> str:
    """Joins consecutive chunks, dropping the overlap the splitter repeated at the start of b."""
    probe = b[:20]
    start = a.find(probe, max(0, len(a) - 1500)) if len(probe) >= 20 else -1
    while start != -1:
        if b.startswith(a[start:]):
            return a + b[len(a) - start :]
        start = a.find(probe, start + 1)
    return a + "\n\n" + b


def _common_heading(paths: list[str]) -> str:
    parts = [p.split(" › ") if p else [] for p in paths]
    common = []
    for level in zip(*parts):
        if len(set(level)) != 1:
            break
        common.append(level[0])
    return " › ".join(common)


def pack_docs(chunks: list[Chunk], budget: int, first_id: int = 1) -> list[Evidence]:
    """Best chunks first (neighbors last) until the budget is used, then merge
    contiguous chunks of a document into one block, in document order."""
    chosen: list[Chunk] = []
    used = 0
    for c in sorted(chunks, key=lambda c: (c.neighbor, -c.score)):
        t = tokens.count(c.text) + TAG_OVERHEAD
        if used + t <= budget:
            chosen.append(c)
            used += t
    by_doc: dict[str, list[Chunk]] = {}
    for c in chosen:  # dict keeps the order of each doc's best chunk
        by_doc.setdefault(c.doc_id, []).append(c)

    blocks: list[Evidence] = []
    for cs in by_doc.values():
        cs.sort(key=lambda c: c.chunk_index)
        run = [cs[0]]
        for c in cs[1:] + [None]:
            if c is not None and c.chunk_index == run[-1].chunk_index + 1:
                run.append(c)
                continue
            text = run[0].text
            for nxt in run[1:]:
                text = join_overlapping(text, nxt.text)
            head = run[0]
            heading = _common_heading([c.heading_path for c in run])
            locator = f"{head.source} › {heading}" if heading else head.source
            blocks.append(Evidence(
                id=first_id + len(blocks), source=head.origin, title=head.title, locator=locator,
                text=text, date=(head.updated_at or "")[:10] or None, date_label=head.date_label,
            ))
            run = [c] if c is not None else []
    return blocks


def used_tokens(evidence: list[Evidence]) -> int:
    return sum(tokens.count(e.text) + TAG_OVERHEAD for e in evidence)


_TAG = re.compile(r"</?\s*(doc|web|doc_search|web_search|url_read|owner_profile|ui_instructions)\b", re.I)


def _defang(text: str) -> str:
    """Untrusted text can't close its own <doc>/<web> tag or open one of ours."""
    return _TAG.sub(lambda m: m.group(0).replace("<", "‹"), text)


def render(evidence: list[Evidence]) -> str:
    parts = []
    for e in evidence:
        date = f' {e.date_label}="{e.date}"' if e.date else ""
        parts.append(f'<{e.source} id={e.id} src="{escape(e.locator)}"{date}>\n{_defang(e.text)}\n</{e.source}>')
    return "\n\n".join(parts)


def cited_ids(answer: str) -> list[int]:
    ids: list[int] = []
    for group in _CITATION.findall(answer):
        for n in group.split(","):
            if int(n) not in ids:
                ids.append(int(n))
    return ids


def sources_block(evidence: list[Evidence], answer: str) -> tuple[str, list[int]]:
    """Markdown Sources list for the cited evidence, plus any cited ids that don't exist."""
    by_id = {e.id: e for e in evidence}
    cited = cited_ids(answer)
    lines = []
    for i in sorted(n for n in cited if n in by_id):
        e = by_id[i]
        date = f" ({e.date_label} {e.date})" if e.date else ""
        where = e.locator if e.source == "web" else f"`{e.locator}`"
        lines.append(f"[{i}] {e.title}: {where}{date}")
    invalid = [n for n in cited if n not in by_id]
    if not lines:
        return "", invalid
    return "\n\n**Sources**\n" + "\n".join(f"- {l}" for l in lines), invalid
