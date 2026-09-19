"""Planner (§8.2): one structured-output call picks routes; heuristic plan if every rung fails."""

import re
from datetime import datetime
from typing import Literal

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from rica.context import tokens
from rica.context.builder import format_now
from rica.llm import Rung
from rica.routes import enabled_names, enabled_routes

RouteName = Literal["chat", "docs", "web", "url"]
URL_RE = re.compile(r"https?://[^\s<>\"'`]+[^\s<>\"'`.,;:!?)\]]")
_FIRST_PERSON = re.compile(r"\b(my|mine)\b", re.I)
MAX_CHARS_PER_MESSAGE = 1500


class Plan(BaseModel):
    routes: list[RouteName] = Field(description="One or more routes; 'chat' alone if nothing needs looking up.")
    standalone_query: str = Field(
        description="The latest request rewritten to make sense without the conversation."
    )
    doc_filter: Literal["any", "about_me"] = "any"
    doc_mode: Literal["facts", "whole_doc", "find_docs"] = "facts"
    doc_hint: str | None = None
    search_queries: list[str] = Field(default_factory=list, description="1-3 web search queries.")
    recency: Literal["any", "day", "week", "month", "year"] = "any"
    snippets_sufficient: bool = False


def extract_urls(text: str) -> list[str]:
    return list(dict.fromkeys(URL_RE.findall(text)))


def restrict(plan: Plan, fallback_query: str) -> Plan:
    """Drop routes that aren't enabled yet; a plan always has at least 'chat'."""
    enabled = enabled_names()
    routes = [r for r in dict.fromkeys(plan.routes) if r in enabled] or ["chat"]
    query = plan.standalone_query.strip() or fallback_query
    return plan.model_copy(update={"routes": routes, "standalone_query": query})


def heuristic_plan(text: str) -> Plan:
    """No-LLM last resort (§5.3 rule 3)."""
    if extract_urls(text):
        routes = ["url"]
    elif _FIRST_PERSON.search(text):
        routes = ["docs"]
    else:
        routes = ["chat"]
    return restrict(Plan(routes=routes, standalone_query=text), text)


def _system(name: str, now: datetime) -> str:
    lines = [
        f"You are RICA, planning how to handle {name}'s latest request. "
        "Do not answer it; only fill in the plan as JSON.",
        f"Now: {format_now(now)}.",
        "",
        "Routes:",
    ]
    lines += [f"- {r.name}: {r.planner.format(name=name)}" for r in enabled_routes()]
    lines += ["", "Also write standalone_query: the latest request rewritten in the user's own voice so it makes "
        "sense on its own (a request, not a description of it)."]
    return "\n".join(lines)


def _transcript(history: list[BaseMessage], budget: int) -> str:
    lines: list[str] = []
    used = 0
    for m in reversed(history):
        who = "User" if isinstance(m, HumanMessage) else "RICA"
        text = m.text if len(m.text) <= MAX_CHARS_PER_MESSAGE else m.text[:MAX_CHARS_PER_MESSAGE] + " …"
        line = f"{who}: {text}"
        t = tokens.count(line)
        if lines and used + t > budget:
            break
        lines.append(line)
        used += t
    return "\n\n".join(reversed(lines))


def planner_messages(rung: Rung, name: str, now: datetime, history: list[BaseMessage]) -> list[BaseMessage]:
    system = SystemMessage(_system(name, now))
    room = rung.input_budget - tokens.count(system.text) - 400  # room for the JSON schema
    return [system, HumanMessage("Conversation (latest last):\n\n" + _transcript(history, room))]
