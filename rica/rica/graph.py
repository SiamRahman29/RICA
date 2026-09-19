"""LangGraph wiring (§8.3). M2: load_context → understand → answer (chat route only)."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict
from zoneinfo import ZoneInfo

from langchain_core.messages import BaseMessage
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from rica.context import tokens
from rica.context.builder import answer_messages, answer_system
from rica.context.profile import Profile, ProfileStore
from rica.llm import LOCAL, AllRungsFailed, ModelLayer
from rica.nodes.understand import Plan, extract_urls, heuristic_plan, planner_messages, restrict

log = logging.getLogger(__name__)

LOCAL_NOTICE = (
    "> ⚠️ Cloud models are unavailable right now — this answer is from RICA's local model "
    "and may be less accurate.\n\n"
)
CUT_NOTICE = "\n\n_(The answer was cut off: the model connection failed. Please ask again.)_"
UNAVAILABLE = "Sorry, none of my models are reachable right now. Please try again in a minute."


class RicaState(TypedDict, total=False):
    messages: list[BaseMessage]  # conversation without system messages; last is the user's
    ui_system: str  # system text sent by the chat UI, if any
    profile: Profile
    now: datetime
    urls: list[str]
    plan: Plan
    plan_source: str
    answer_tier: str | None
    attempts: list[str]


@dataclass
class Deps:
    models: ModelLayer
    profiles: ProfileStore
    planner_history: int = 6


def build_graph(deps: Deps):
    def load_context(state: RicaState) -> RicaState:
        profile = deps.profiles.get()
        last = state["messages"][-1].text
        return {
            "profile": profile,
            "now": datetime.now(ZoneInfo(profile.timezone)),
            "urls": extract_urls(last),
            "attempts": [],
        }

    async def understand(state: RicaState) -> RicaState:
        history = state["messages"][-deps.planner_history :]
        last = state["messages"][-1].text
        attempts = list(state["attempts"])
        try:
            plan, source = await deps.models.structured(
                "understand",
                lambda rung: planner_messages(rung, state["profile"].preferred_name, state["now"], history),
                Plan,
                attempts,
            )
            plan = restrict(plan, last)
        except AllRungsFailed:
            plan, source = heuristic_plan(last), "heuristic"
        return {"plan": plan, "plan_source": source, "attempts": attempts}

    async def answer(state: RicaState) -> RicaState:
        write = get_stream_writer()
        attempts = list(state["attempts"])

        def build(rung):
            return answer_messages(
                state["profile"], state["now"], rung.alias, rung.input_budget,
                state["messages"], state.get("ui_system", ""),
            )

        # Conversations too long for the first answer rung go to the long-context ladder
        first = deps.models.ladder("answer")[0]
        system = answer_system(state["profile"], state["now"], first.alias, state.get("ui_system", ""))
        needed = tokens.count(system) + tokens.count_messages(state["messages"])
        ladder = "answer_long" if needed > first.input_budget else "answer"

        tier = None
        try:
            async for alias, text in deps.models.stream(ladder, build, attempts):
                if tier is None:
                    tier = alias
                    if alias == LOCAL:
                        write(LOCAL_NOTICE)
                write(text)
        except AllRungsFailed:
            write(UNAVAILABLE)
        except Exception:
            log.exception("answer stream failed after it started")
            write(CUT_NOTICE)
        return {"answer_tier": tier, "attempts": attempts}

    g = StateGraph(RicaState)
    g.add_node("load_context", load_context)
    g.add_node("understand", understand)
    g.add_node("answer", answer)
    g.add_edge(START, "load_context")
    g.add_edge("load_context", "understand")
    g.add_edge("understand", "answer")
    g.add_edge("answer", END)
    return g.compile()
