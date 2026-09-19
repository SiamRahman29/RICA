"""LangGraph wiring (§8.3): load_context → understand → [docs] → answer."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict
from zoneinfo import ZoneInfo

from langchain_core.messages import BaseMessage
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from rica.context import tokens
from rica.context.builder import answer_messages, answer_system
from rica.context.evidence import CitationNormalizer, Evidence, pack_docs, sources_block
from rica.context.profile import Profile, ProfileStore
from rica.llm import LOCAL, AllRungsFailed, ModelLayer, Rung
from rica.nodes.docs import docs_context, retrieve
from rica.nodes.understand import Plan, extract_urls, heuristic_plan, planner_messages, restrict
from rica.retrieval.search import Chunk, DocSearch
from rica.routes import enabled_names

log = logging.getLogger(__name__)

LOCAL_NOTICE = (
    "> ⚠️ Cloud models are unavailable right now — this answer is from RICA's local model "
    "and may be less accurate.\n\n"
)
CUT_NOTICE = "\n\n_(The answer was cut off: the model connection failed. Please ask again.)_"
UNAVAILABLE = "Sorry, none of my models are reachable right now. Please try again in a minute."
# Tokens kept free for the conversation when sizing evidence
HISTORY_RESERVE = 600


class RicaState(TypedDict, total=False):
    messages: list[BaseMessage]  # conversation without system messages; last is the user's
    ui_system: str  # system text sent by the chat UI, if any
    profile: Profile
    now: datetime
    urls: list[str]
    plan: Plan
    plan_source: str
    doc_chunks: list[Chunk]
    doc_status: str | None  # None (route not used), found, not_found, error
    answer_tier: str | None
    evidence_used: int
    invalid_citations: list[int]
    attempts: list[str]


@dataclass
class Deps:
    models: ModelLayer
    profiles: ProfileStore
    doc_search: Callable[[], DocSearch]
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
            "doc_status": None,
        }

    async def understand(state: RicaState) -> RicaState:
        history = state["messages"][-deps.planner_history :]
        last = state["messages"][-1].text
        attempts = list(state["attempts"])
        hints: list[str] = []
        if "docs" in enabled_names():
            try:
                hints = await asyncio.to_thread(lambda: deps.doc_search().quick_titles(last))
            except Exception as e:
                log.warning("planner hints unavailable: %s", e)
        try:
            plan, source = await deps.models.structured(
                "understand",
                lambda rung: planner_messages(rung, state["profile"].preferred_name, state["now"], history, hints),
                Plan,
                attempts,
            )
            plan = restrict(plan, last)
        except AllRungsFailed:
            plan, source = heuristic_plan(last), "heuristic"
        return {"plan": plan, "plan_source": source, "attempts": attempts}

    def after_understand(state: RicaState) -> list[str]:
        return ["docs"] if "docs" in state["plan"].routes else ["answer"]

    async def docs(state: RicaState) -> RicaState:
        try:
            chunks = await asyncio.to_thread(lambda: retrieve(deps.doc_search(), state["plan"]))
        except Exception:
            log.exception("docs retrieval failed")
            return {"doc_chunks": [], "doc_status": "error"}
        return {"doc_chunks": chunks, "doc_status": "found" if chunks else "not_found"}

    async def answer(state: RicaState) -> RicaState:
        write = get_stream_writer()
        attempts = list(state["attempts"])
        profile, now, plan = state["profile"], state["now"], state["plan"]
        extra = state.get("ui_system", "")
        chunks = state.get("doc_chunks") or []
        packed: dict[str, list[Evidence]] = {}

        def build(rung: Rung):
            base = tokens.count(answer_system(profile, now, rung.alias, extra))
            last = tokens.count(state["messages"][-1].text)
            room = rung.input_budget - base - min(last, rung.input_budget // 4) - HISTORY_RESERVE
            budget = min(rung.spec.evidence_budget or room, room)
            packed[rung.alias] = pack_docs(chunks, max(budget, 0)) if chunks else []
            context = docs_context(state.get("doc_status"), plan.doc_mode, packed[rung.alias], profile.preferred_name)
            return answer_messages(profile, now, rung.alias, rung.input_budget, state["messages"], extra, context)

        # Whole notes and conversations too long for the first answer rung use the long-context ladder
        first = deps.models.ladder("answer")[0]
        needed = (
            tokens.count(answer_system(profile, now, first.alias, extra))
            + tokens.count_messages(state["messages"])
            + sum(tokens.count(c.text) for c in chunks)
        )
        long = (plan.doc_mode == "whole_doc" and chunks) or needed > first.input_budget
        ladder = "answer_long" if long else "answer"

        tier, text, cites = None, [], CitationNormalizer()

        def emit(piece: str) -> None:
            if piece:
                write(piece)
                text.append(piece)

        try:
            async for alias, piece in deps.models.stream(ladder, build, attempts):
                if tier is None:
                    tier = alias
                    if alias == LOCAL:
                        write(LOCAL_NOTICE)
                emit(cites.feed(piece))
            emit(cites.flush())
        except AllRungsFailed:
            write(UNAVAILABLE)
        except Exception:
            log.exception("answer stream failed after it started")
            write(CUT_NOTICE)

        evidence = packed.get(tier, []) if tier else []
        sources, invalid = sources_block(evidence, "".join(text))
        if sources:
            write(sources)
        return {
            "answer_tier": tier,
            "attempts": attempts,
            "evidence_used": len(evidence),
            "invalid_citations": invalid,
        }

    g = StateGraph(RicaState)
    g.add_node("load_context", load_context)
    g.add_node("understand", understand)
    g.add_node("docs", docs)
    g.add_node("answer", answer)
    g.add_edge(START, "load_context")
    g.add_edge("load_context", "understand")
    g.add_conditional_edges("understand", after_understand, ["docs", "answer"])
    g.add_edge("docs", "answer")
    g.add_edge("answer", END)
    return g.compile()
