import pytest

from rica.nodes.web import merge_results, page_chunks
from rica.web.fetch import FetchError, Page, _check_scheme, resolve_public
from rica.web.searx import Result


@pytest.mark.parametrize("host", ["127.0.0.1", "169.254.169.254", "10.1.2.3", "192.168.1.1", "::1", "0.0.0.0", "fc00::1", "localhost"])
async def test_non_public_addresses_blocked(host):
    with pytest.raises(FetchError) as e:
        await resolve_public(host, 80)
    assert e.value.reason == "blocked"


async def test_public_ip_allowed():
    assert await resolve_public("1.1.1.1", 443) == "1.1.1.1"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x", "gopher://x", "http:///nohost"])
def test_only_http_urls(url):
    with pytest.raises(FetchError):
        _check_scheme(url)


def r(url, title="t"):
    return Result(url, title, "snippet", None, ())


def test_merge_results_round_robin_dedupe_and_skip_social():
    a = [r("https://a.com/1"), r("https://www.youtube.com/watch?v=1"), r("https://a.com/2")]
    b = [r("https://a.com/1/"), r("https://b.com/1")]
    assert [x.url for x in merge_results([a, b])] == ["https://a.com/1", "https://b.com/1", "https://a.com/2"]


def test_page_chunks_rank_relevant_passage_first():
    text = "\n\n".join(["Filler about gardening and soil. " * 40, "The launch is scheduled for 12 October 2026. " * 5, "More filler on cooking. " * 40])
    page = Page("https://x.com/a", "X", text, "2026-09-18", "2026-09-19")
    chunks = page_chunks(page, "when is the launch scheduled")
    best = max(chunks, key=lambda c: c.score)
    assert "launch is scheduled" in best.text
    assert best.origin == "web" and best.date_label == "published" and best.updated_at == "2026-09-18"
