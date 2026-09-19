import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, HumanMessage

from rica.context import tokens
from rica.context.builder import answer_messages, capabilities, fit_history
from rica.context.profile import Profile, ProfileStore, parse

TEMPLATE = """---
name: <full name>
preferred_name: <what RICA calls you>
timezone: Asia/Dhaka
location: <city, country>
languages: [English]
---
## About me
- <role / what you do, one line>
- <2–3 facts that change how RICA answers>

## How I want answers
- Lead with the answer; details only if I ask.
- <units, currency, date/time format>

## Current focus
- <what you're working on these weeks>
"""


def test_template_profile_uses_fallbacks():
    p = parse(TEMPLATE, "Sam", "UTC")
    assert p.preferred_name == "Sam" and p.name is None and p.location is None
    assert p.timezone == "Asia/Dhaka"
    assert p.body == "## How I want answers\n- Lead with the answer; details only if I ask."


def test_profile_hot_reload(tmp_path):
    f = tmp_path / "profile.md"
    store = ProfileStore(f, "", "Asia/Dhaka")
    assert store.get().preferred_name == "the owner"
    f.write_text("---\npreferred_name: Ana\n---\nLikes metric units.\n")
    assert store.get().preferred_name == "Ana"
    f.write_text("---\npreferred_name: Ann\n---\n")
    os.utime(f, (time.time() + 5, time.time() + 5))
    assert store.get().preferred_name == "Ann"


def test_capabilities_lists_what_is_not_possible_yet():
    text = capabilities("Ana")
    can, cannot = text.split("You cannot (yet):")
    assert "Search and read Ana's notes" in can
    assert "calendar" in cannot and "search the web" in cannot


def test_fit_history_keeps_latest_and_starts_on_user():
    h = [HumanMessage("old " * 300), AIMessage("reply " * 300), HumanMessage("latest question")]
    kept = fit_history(h, 400)
    assert [m.text for m in kept] == ["latest question"]


def test_fit_history_truncates_huge_latest_message():
    kept = fit_history([HumanMessage("word " * 5000 + "the question?")], 200)
    assert len(kept) == 1 and kept[0].text.endswith("the question?")
    assert tokens.count(kept[0].text) <= 200


def test_answer_messages_fit_budget():
    p = Profile(preferred_name="Ana", timezone="Asia/Dhaka")
    now = datetime(2026, 9, 19, 14, 5, tzinfo=ZoneInfo("Asia/Dhaka"))
    history = [HumanMessage("x " * 2000), AIMessage("y " * 2000), HumanMessage("hi")]
    msgs = answer_messages(p, now, "local", 2700, history)
    assert tokens.count_messages(msgs) <= 2700
    assert "Now: Saturday, 19 September 2026, 14:05 (Asia/Dhaka" in msgs[0].text
