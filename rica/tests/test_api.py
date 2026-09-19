import json

import pytest
from fastapi.testclient import TestClient

from rica import routes
from rica.api import create_app
from rica.graph import LOCAL_NOTICE, UNAVAILABLE
from rica.nodes.understand import heuristic_plan
from rica.settings import Settings
from tests.fakes import Scripted, layer

KEY = "test-key"
PLAN = '{"routes": ["chat"], "standalone_query": "hi"}'


def client(models, tmp_path) -> TestClient:
    s = Settings(rica_internal_key=KEY, knowledge_dir=tmp_path, owner_name="Ana", warmup_local=False)
    return TestClient(create_app(s, models))


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
