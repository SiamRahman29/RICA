"""LangGraph wiring (§8.3): load_context → understand → [docs | web | url in parallel] → answer."""

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
from rica.context.evidence import CitationNormalizer, Evidence, cited_ids, pack_docs, sources_block, used_tokens
from rica.context.profile import Profile, ProfileStore
from rica.llm import LOCAL, AllRungsFailed, ModelLayer, Rung
from rica.nodes.docs import docs_context, retrieve
from rica.nodes.understand import Plan, extract_urls, heuristic_plan, planner_messages, restrict
from rica.nodes.web import UrlNote, WebTools, read_urls, url_context, web_context, web_search
from rica.retrieval.search import Chunk, DocSearch
from rica.routes import enabled_names

log = logging.getLogger(__name__)

LOCAL_NOTICE = (
    "> ⚠️ Cloud models are unavailable right now — this answer is from RICA's local model "
    "and may be less accurate.\n\n"
)
# Part of LOCAL_NOTICE that survives in the history Open WebUI sends back, so the
# warning is shown once per chat instead of on top of every local answer.
LOCAL_NOTICE_MARK = "Cloud models are unavailable right now"
CUT_NOTICE = "\n\n_(The answer was cut off: the model connection failed. Please ask again.)_"
RESTART_NOTICE = "\n\n_(The model stopped mid-answer; starting over with another one.)_\n\n"
UNAVAILABLE = "Sorry, none of my models are reachable right now. Please try again in a minute."
# Tokens kept free for the conversation when sizing evidence
HISTORY_RESERVE = 600


def already_warned(messages: list[BaseMessage]) -> bool:
    """True if an earlier answer in this chat already carried LOCAL_NOTICE."""
    return any(m.type == "ai" and LOCAL_NOTICE_MARK in m.text for m in messages)


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
    web_chunks: list[Chunk]
    web_status: str | None
    url_chunks: list[Chunk]
    url_notes: list[UrlNote]
    answer_tier: str | None
    evidence: list[Evidence]  # what the answering rung was given
    cited: list[int]
    invalid_citations: list[int]
    prompt_tokens: int
    attempts: list[str]


@dataclass
class Deps:
    models: ModelLayer
    profiles: ProfileStore
    doc_search: Callable[[], DocSearch]
    web: WebTools
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
            "web_status": None,
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
        # A link in the message is always read; "url" without a link has nothing to read
        routes = [r for r in plan.routes if r != "url"] + (["url"] if state["urls"] and "url" in enabled_names() else [])
        plan = plan.model_copy(update={"routes": routes or ["chat"]})
        return {"plan": plan, "plan_source": source, "attempts": attempts}

    def after_understand(state: RicaState) -> list[str]:
        return [r for r in ("docs", "web", "url") if r in state["plan"].routes] or ["answer"]

    async def docs(state: RicaState) -> RicaState:
        try:
            chunks = await asyncio.to_thread(lambda: retrieve(deps.doc_search(), state["plan"]))
        except Exception:
            log.exception("docs retrieval failed")
            return {"doc_chunks": [], "doc_status": "error"}
        return {"doc_chunks": chunks, "doc_status": "found" if chunks else "not_found"}

    async def web(state: RicaState) -> RicaState:
        try:
            chunks, status = await web_search(deps.web, state["plan"])
        except Exception:
            log.exception("web search failed")
            chunks, status = [], "error"
        return {"web_chunks": chunks, "web_status": status}

    async def url(state: RicaState) -> RicaState:
        chunks, notes = await read_urls(deps.web, state["urls"], state["plan"].standalone_query)
        return {"url_chunks": chunks, "url_notes": notes}

    async def answer(state: RicaState) -> RicaState:
        write = get_stream_writer()
        attempts = list(state["attempts"])
        profile, now, plan = state["profile"], state["now"], state["plan"]
        extra = state.get("ui_system", "")
        name = profile.preferred_name
        # Links the owner sent come first, then notes, then search results
        groups = {
            "url": state.get("url_chunks") or [],
            "docs": state.get("doc_chunks") or [],
            "web": state.get("web_chunks") or [],
        }
        packed: dict[str, list[Evidence]] = {}
        prompt_tokens: dict[str, int] = {}

        def build(rung: Rung):
            base = tokens.count(answer_system(profile, now, rung.alias, extra))
            last = tokens.count(state["messages"][-1].text)
            room = rung.input_budget - base - min(last, rung.input_budget // 4) - HISTORY_RESERVE
            remaining = max(min(rung.spec.evidence_budget or room, room), 0)
            by_group: dict[str, list[Evidence]] = {}
            active = [g for g, cs in groups.items() if cs]
            next_id = 1
            for i, g in enumerate(active):
                # Fair share of what's left, so unused budget flows to later groups
                by_group[g] = pack_docs(groups[g], remaining // (len(active) - i), first_id=next_id)
                remaining -= used_tokens(by_group[g])
                next_id += len(by_group[g])
            packed[rung.alias] = [e for g in active for e in by_group[g]]
            context = "\n\n".join(p for p in [
                url_context(state.get("url_notes") or [], by_group.get("url", []), name),
                docs_context(state.get("doc_status"), plan.doc_mode, by_group.get("docs", []), name),
                web_context(state.get("web_status"), by_group.get("web", []), now),
            ] if p)
            messages = answer_messages(profile, now, rung.alias, rung.input_budget, state["messages"], extra, context)
            prompt_tokens[rung.alias] = tokens.count_messages(messages)
            return messages

        # The long-context ladder is for whole notes, long linked pages, and long conversations.
        # Search results and note excerpts are packed down to the first rung's budget instead.
        first = deps.models.ladder("answer")[0]
        conversation = tokens.count(answer_system(profile, now, first.alias, extra)) + tokens.count_messages(state["messages"])
        linked = sum(tokens.count(c.text) for c in groups["url"])
        long = (
            (plan.doc_mode == "whole_doc" and groups["docs"])
            or linked > first.spec.evidence_budget
            or conversation > first.input_budget
        )
        ladder = "answer_long" if long else "answer"

        tier, text, cites = None, [], CitationNormalizer()
        warned = already_warned(state["messages"])

        def emit(piece: str) -> None:
            if piece:
                write(piece)
                text.append(piece)

        try:
            async for alias, piece in deps.models.stream(ladder, build, attempts):
                if piece is None:  # that rung died mid-answer; the next one starts over
                    write(cites.flush() + RESTART_NOTICE)
                    tier, cites = None, CitationNormalizer()
                    text.clear()
                    continue
                if tier is None:
                    tier = alias
                    if alias == LOCAL and not warned:
                        write(LOCAL_NOTICE)
                        warned = True
                emit(cites.feed(piece))
            emit(cites.flush())
        except AllRungsFailed:
            write(UNAVAILABLE)
        except Exception:
            log.exception("answer stream failed after it started")
            write(CUT_NOTICE)

        evidence = packed.get(tier, []) if tier else []
        answer_text = "".join(text)
        sources, invalid = sources_block(evidence, answer_text)
        if sources:
            write(sources)
        return {
            "answer_tier": tier,
            "attempts": attempts,
            "evidence": evidence,
            "cited": cited_ids(answer_text),
            "invalid_citations": invalid,
            "prompt_tokens": prompt_tokens.get(tier, 0) if tier else 0,
        }

    g = StateGraph(RicaState)
    g.add_node("load_context", load_context)
    g.add_node("understand", understand)
    g.add_node("docs", docs)
    g.add_node("web", web)
    g.add_node("url", url)
    g.add_node("answer", answer)
    g.add_edge(START, "load_context")
    g.add_edge("load_context", "understand")
    g.add_conditional_edges("understand", after_understand, ["docs", "web", "url", "answer"])
    for node in ("docs", "web", "url"):
        g.add_edge(node, "answer")
    g.add_edge("answer", END)
    return g.compile()
