from rica.context.evidence import cited_ids, pack_docs, render, sources_block
from rica.retrieval.search import Chunk


def chunk(doc, i, text, score, neighbor=False, heading="H"):
    return Chunk(doc_id=doc, source=f"notes/{doc}.md", title=doc.title(), heading_path=heading,
                 chunk_index=i, text=text, updated_at="2026-08-03T10:00:00+06:00", score=score, neighbor=neighbor)


def test_pack_merges_contiguous_chunks_in_document_order():
    cs = [
        chunk("car", 1, "second part", 5.0),
        chunk("car", 0, "first part", 1.0, neighbor=True),
        chunk("solar", 3, "inverter", 3.0),
    ]
    ev = pack_docs(cs, budget=1000)
    assert [(e.id, e.locator, e.text) for e in ev] == [
        (1, "notes/car.md › H", "first part\n\nsecond part"),
        (2, "notes/solar.md › H", "inverter"),
    ]
    assert ev[0].date == "2026-08-03"


def test_pack_respects_budget_and_prefers_matches_over_neighbors():
    cs = [chunk("a", 0, "word " * 100, 1.0, neighbor=True), chunk("b", 0, "word " * 100, 0.5)]
    ev = pack_docs(cs, budget=150)
    assert [e.title for e in ev] == ["B"]


def test_render_and_sources():
    ev = pack_docs([chunk("car", 0, "Service due in December.", 2.0)], 1000)
    assert render(ev).startswith('<doc id=1 src="notes/car.md › H" updated="2026-08-03">')
    sources, invalid = sources_block(ev, "It's due in December [1]. Also [1, 3].")
    assert "[1] Car: `notes/car.md › H` (updated 2026-08-03)" in sources
    assert invalid == [3]
    assert sources_block(ev, "No citations.") == ("", [])


def test_cited_ids():
    assert cited_ids("a [2] b [1, 2] c [10]") == [2, 1, 10]


def test_citation_normalizer_across_split_tokens():
    from rica.context.evidence import CitationNormalizer

    n = CitationNormalizer()
    pieces = ["Lina lives in Chittagong", "【", "1†L5", "-L6】 and ", "works【2, 3】.", " 【not a cite"]
    out = "".join(n.feed(p) for p in pieces) + n.flush()
    assert out == "Lina lives in Chittagong[1] and works[2, 3]. 【not a cite"


def test_merged_run_locator_uses_common_heading():
    cs = [chunk("p", 0, "a", 2.0, heading="Proj › Goals"), chunk("p", 1, "b", 1.0, heading="Proj › Risks")]
    assert pack_docs(cs, 1000)[0].locator == "notes/p.md › Proj"
