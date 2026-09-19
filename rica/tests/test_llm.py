import pytest
from pydantic import BaseModel

from rica.llm import AllRungsFailed, ModelLayer
from tests.fakes import CONFIG, Scripted, layer


class Out(BaseModel):
    x: int


def test_recursion_guard():
    bad = CONFIG.model_copy(update={"ladders": {"answer": ["groq-smart", "rica"]}})
    with pytest.raises(ValueError, match="recursion guard"):
        ModelLayer(bad, lambda r: Scripted())


def test_real_ladders_file_is_valid():
    from rica.llm import load_config
    from rica.settings import Settings

    ModelLayer(load_config(Settings().ladders_file), lambda r: Scripted())


async def test_stream_falls_back_and_rebuilds_per_rung():
    budgets = []
    flash = Scripted(reply="hello there")
    models = layer(gemini_flash=flash)
    attempts: list[str] = []

    def build(rung):
        budgets.append(rung.input_budget)
        return [("user", "hi")]

    out = [(a, t) async for a, t in models.stream("answer", build, attempts)]
    assert "".join(t for _, t in out) == "hello there"
    assert {a for a, _ in out} == {"gemini-flash"}
    assert attempts == ["groq-smart:RuntimeError", "gemini-flash:ok"]
    assert budgets == [5400, 54000]


async def test_stream_restarts_on_next_rung_after_mid_answer_failure():
    models = layer(groq_smart=Scripted(reply="one two", fail_after_first=True), gemini_flash=Scripted(reply="fresh answer"))
    attempts: list[str] = []
    out = [x async for x in models.stream("answer", lambda r: [("user", "hi")], attempts)]
    assert out == [("groq-smart", "one"), ("groq-smart", None), ("gemini-flash", "fresh"), ("gemini-flash", " answer")]
    assert attempts == ["groq-smart:cut:RuntimeError", "gemini-flash:ok"]


async def test_stream_empty_answer_advances():
    models = layer(groq_smart=Scripted(reply=""), gemini_flash=Scripted(reply="ok"))
    attempts: list[str] = []
    out = [a async for a, _ in models.stream("answer", lambda r: [("user", "hi")], attempts)]
    assert out == ["gemini-flash"] and attempts[0] == "groq-smart:empty"


async def test_structured_invalid_output_advances():
    models = layer(groq_fast=Scripted(reply="not json"), gemini_lite=Scripted(reply='```json\n{"x": 3}\n```'))
    attempts: list[str] = []
    out, alias = await models.structured("understand", lambda r: [("user", "hi")], Out, attempts)
    assert (out.x, alias) == (3, "gemini-lite")
    assert attempts == ["groq-fast:ValidationError", "gemini-lite:ok"]


async def test_structured_all_fail():
    with pytest.raises(AllRungsFailed):
        await layer().structured("understand", lambda r: [("user", "hi")], Out, [])
