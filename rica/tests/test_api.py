import json

import pytest
from fastapi.testclient import TestClient

from rica import routes
from rica.api import create_app
from rica.graph import LOCAL_NOTICE, UNAVAILABLE
from rica.nodes.understand import heuristic_plan
from rica.settings import Settings
from rica.retrieval.search import Chunk
from tests.fakes import Scripted, layer

KEY = "test-key"
PLAN = '{"routes": ["chat"], "standalone_query": "hi"}'


class FakeSearch:
    def __init__(self, chunks):
        self.chunks = chunks

    def facts(self, q, about_me):
        return self.chunks

    whole_doc = lambda self, hint, q, about_me: self.chunks  # noqa: E731
    find_docs = facts

    def quick_titles(self, q):
        return [f"{c.title} ({c.source})" for c in self.chunks]


CAR = Chunk(doc_id="c", source="notes/car.md", title="Car", heading_path="Car", chunk_index=0,
            text="Next service is due in December 2026.", updated_at="2026-08-03T10:00:00+06:00", score=5.0)
DOCS_PLAN = '{"routes": ["docs"], "standalone_query": "When is my car service due?"}'


def client(models, tmp_path, chunks=()) -> TestClient:
    s = Settings(rica_internal_key=KEY, knowledge_dir=tmp_path, owner_name="Ana", warmup_local=False)
    search = FakeSearch(list(chunks))
    return TestClient(create_app(s, models, lambda: search))


def ask(c, stream=False, text="Who are you?"):
    return c.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {KEY}"},
        json={"model": "rica", "stream": stream, "messages": [{"role": "user", "content": text}]},
    )


def test_requires_key(tmp_path):
    c = client(layer(), tmp_path)
    assert c.get("/v1/models").status_code == 401
    assert c.get("/v1/models", headers={"Authorization": f"Bearer {KEY}"}).json()["data"][0]["id"] == "rica"


def test_non_stream_answer_and_identity_in_prompt(tmp_path):
    smart = Scripted(reply="I am RICA.")
    with client(layer(groq_fast=Scripted(reply=PLAN), groq_smart=smart), tmp_path) as c:
        r = ask(c)
    assert r.json()["choices"][0]["message"]["content"] == "I am RICA."
    system = smart.calls[-1][0].text
    assert system.startswith("You are RICA, Ana's personal AI assistant.")


def test_stream_format(tmp_path):
    with client(layer(groq_fast=Scripted(reply=PLAN), groq_smart=Scripted(reply="Hello Ana")), tmp_path) as c:
        r = ask(c, stream=True)
    lines = [l for l in r.text.splitlines() if l.startswith("data: ")]
    assert lines[-1] == "data: [DONE]"
    chunks = [json.loads(l[6:]) for l in lines[:-1]]
    assert "".join(ch["choices"][0]["delta"].get("content", "") for ch in chunks) == "Hello Ana"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"


def test_local_answer_carries_notice(tmp_path):
    with client(layer(local=Scripted(reply="Local answer")), tmp_path) as c:
        text = ask(c).json()["choices"][0]["message"]["content"]
    assert text == LOCAL_NOTICE + "Local answer"


def test_everything_down(tmp_path):
    with client(layer(), tmp_path) as c:
        assert ask(c).json()["choices"][0]["message"]["content"] == UNAVAILABLE


def test_last_message_must_be_user(tmp_path):
    with client(layer(), tmp_path) as c:
        r = c.post("/v1/chat/completions", headers={"Authorization": f"Bearer {KEY}"},
                   json={"messages": [{"role": "assistant", "content": "hi"}]})
    assert r.status_code == 400


@pytest.mark.parametrize(
    "text,route",
    [("read https://example.com/a.", "url"), ("what's my passport number", "docs"), ("hello", "chat")],
)
def test_heuristic_plan(monkeypatch, text, route):
    monkeypatch.setattr(routes, "enabled_names", lambda: {"chat", "docs", "web", "url"})
    monkeypatch.setattr("rica.nodes.understand.enabled_names", routes.enabled_names)
    assert heuristic_plan(text).routes == [route]


def test_heuristic_plan_only_uses_enabled_routes():
    assert heuristic_plan("read https://example.com").routes == ["chat"]


def test_docs_route_packs_evidence_and_appends_sources(tmp_path):
    smart = Scripted(reply="It is due in December 2026 [1].")
    with client(layer(groq_fast=Scripted(reply=DOCS_PLAN), groq_smart=smart), tmp_path, [CAR]) as c:
        text = ask(c, text="When is my car service due?").json()["choices"][0]["message"]["content"]
    assert text.startswith("It is due in December 2026 [1].")
    assert "**Sources**\n- [1] Car: `notes/car.md › Car` (updated 2026-08-03)" in text
    system = smart.calls[-1][0].text
    assert '<doc id=1 src="notes/car.md › Car" updated="2026-08-03">' in system


def test_docs_not_found_tells_model(tmp_path):
    smart = Scripted(reply="I couldn't find that in your notes.")
    with client(layer(groq_fast=Scripted(reply=DOCS_PLAN), groq_smart=smart), tmp_path, []) as c:
        text = ask(c).json()["choices"][0]["message"]["content"]
    assert "Sources" not in text
    assert 'status="not found"' in smart.calls[-1][0].text


def test_local_rung_gets_smaller_evidence_budget(tmp_path):
    many = [Chunk(**{**CAR.__dict__, "doc_id": f"d{i}", "text": "fact " * 300, "score": 5.0 - i}) for i in range(6)]
    local = Scripted(reply="Local [1]")
    with client(layer(groq_fast=Scripted(reply=DOCS_PLAN), local=local), tmp_path, many) as c:
        ask(c)
    assert local.calls[-1][0].text.count("<doc id=") == 3  # ~1200-token evidence budget


def test_planner_sees_note_hints(tmp_path):
    fast = Scripted(reply=DOCS_PLAN)
    with client(layer(groq_fast=fast, groq_smart=Scripted(reply="ok")), tmp_path, [CAR]) as c:
        ask(c, text="When is the service due?")
    assert "- Car (notes/car.md)" in fast.calls[0][0].text
