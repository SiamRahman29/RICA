"""OpenAI-compatible endpoint (§8.1). LiteLLM exposes it to Open WebUI as model `rica`."""

import asyncio
import json
import logging
import secrets
import threading
import time
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from pydantic import BaseModel

from rica.context.profile import ProfileStore
from rica.graph import UNAVAILABLE, Deps, build_graph
from rica.llm import LOCAL, ModelLayer
from rica.nodes.web import WebTools
from rica.retrieval.search import DocSearch
from rica.web.cache import WebCache
from rica.settings import Settings

log = logging.getLogger("rica")
MODEL_ID = "rica"


class ChatMessage(BaseModel):
    role: str
    content: str | list | None = None


class ChatRequest(BaseModel):
    model: str = MODEL_ID
    messages: list[ChatMessage]
    stream: bool = False


def _text(content: str | list | None) -> str:
    """Content may be a list of parts (text, images); only text is used for now."""
    if isinstance(content, str):
        return content
    parts = content or []
    return "\n".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("type") == "text")


def to_state(messages: list[ChatMessage]) -> dict:
    history: list[BaseMessage] = []
    ui_system: list[str] = []
    for m in messages:
        text = _text(m.content)
        if m.role in ("system", "developer"):
            ui_system.append(text)
        elif m.role == "user":
            history.append(HumanMessage(text))
        elif m.role == "assistant" and text:
            history.append(AIMessage(text))
    if not history or not isinstance(history[-1], HumanMessage):
        raise HTTPException(400, "the last message must be from the user")
    return {"messages": history, "ui_system": "\n\n".join(t for t in ui_system if t.strip())}


def lazy[T](make: Callable[[], T]) -> Callable[[], T]:
    """Thread-safe create-once: embedding models load on first use, not at import."""
    lock, box = threading.Lock(), []

    def get() -> T:
        with lock:
            if not box:
                box.append(make())
            return box[0]

    return get


def create_app(
    settings: Settings | None = None,
    models: ModelLayer | None = None,
    doc_search: Callable[[], DocSearch] | None = None,
) -> FastAPI:
    settings = settings or Settings()
    models = models or ModelLayer.from_settings(settings)
    profiles = ProfileStore(settings.knowledge_dir / "_rica" / "profile.md", settings.owner_name, settings.tz)
    doc_search = doc_search or lazy(lambda: DocSearch(settings))
    web = WebTools(settings.searxng_url, WebCache(settings.data_dir / "web_cache.db"), settings.web_pages_to_read)
    graph = build_graph(Deps(models, profiles, doc_search, web, settings.planner_history_messages))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not settings.rica_internal_key:
            raise RuntimeError("RICA_INTERNAL_KEY is not set")
        tasks = []
        if settings.warmup_local:
            tasks.append(asyncio.create_task(_warm_local(models)))
            tasks.append(asyncio.create_task(_warm_docs(doc_search)))
        yield
        for t in tasks:
            t.cancel()

    app = FastAPI(title="RICA", lifespan=lifespan)

    def auth(request: Request) -> None:
        header = request.headers.get("authorization", "")
        token = header.removeprefix("Bearer ").strip()
        if not secrets.compare_digest(token.encode(), settings.rica_internal_key.encode()):
            raise HTTPException(401, "invalid API key")

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    @app.get("/v1/models", dependencies=[Depends(auth)])
    async def list_models():
        return {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "owned_by": "rica"}]}

    async def run(state: dict) -> AsyncIterator[str]:
        t0 = time.monotonic()
        info: dict = {}
        try:
            async for mode, data in graph.astream(state, stream_mode=["custom", "updates"]):
                if mode == "custom":
                    yield data
                else:
                    for update in data.values():
                        info.update(update or {})
        except Exception:
            log.exception("graph failed")
            yield UNAVAILABLE
        plan = info.get("plan")
        log.info(json.dumps({
            "event": "request",
            "routes": plan.routes if plan else None,
            "plan_source": info.get("plan_source"),
            "answer_tier": info.get("answer_tier"),
            "local": info.get("answer_tier") == LOCAL,
            "doc_mode": plan.doc_mode if plan and "docs" in plan.routes else None,
            "doc_status": info.get("doc_status"),
            "web_status": info.get("web_status"),
            "urls_read": len({c.source for c in info.get("url_chunks") or []}) or None,
            "url_notes": [n.reason for n in info.get("url_notes") or []] or None,
            "evidence": info.get("evidence_used"),
            "invalid_citations": info.get("invalid_citations") or None,
            "attempts": info.get("attempts"),
            "latency_s": round(time.monotonic() - t0, 2),
        }))

    @app.post("/v1/chat/completions", dependencies=[Depends(auth)])
    async def chat_completions(req: ChatRequest):
        state = to_state(req.messages)
        cid, created = f"chatcmpl-{uuid.uuid4().hex}", int(time.time())

        if not req.stream:
            text = "".join([t async for t in run(state)])
            return JSONResponse({
                "id": cid, "object": "chat.completion", "created": created, "model": MODEL_ID,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            })

        def chunk(delta: dict, finish: str | None = None) -> str:
            body = {
                "id": cid, "object": "chat.completion.chunk", "created": created, "model": MODEL_ID,
                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            }
            return f"data: {json.dumps(body, ensure_ascii=False)}\n\n"

        async def sse() -> AsyncIterator[str]:
            yield chunk({"role": "assistant", "content": ""})
            async for text in run(state):
                yield chunk({"content": text})
            yield chunk({}, "stop")
            yield "data: [DONE]\n\n"

        return StreamingResponse(sse(), media_type="text/event-stream")

    return app


async def _warm_local(models: ModelLayer) -> None:
    """llama.cpp loads models on first use; load it now so a fallback doesn't wait (§5.4)."""
    for _ in range(10):  # LiteLLM may still be starting
        try:
            await models.model(LOCAL).ainvoke("Hi", max_tokens=1)
            log.info("local model warmed up")
            return
        except Exception as e:
            last = e
            await asyncio.sleep(6)
    log.warning("local warm-up failed: %s", last)


async def _warm_docs(doc_search: Callable[[], DocSearch]) -> None:
    """Loads the embedding and rerank models (downloads them on first run)."""
    try:
        await asyncio.to_thread(doc_search)
        log.info("docs search ready")
    except Exception as e:
        log.warning("docs search warm-up failed: %s", e)


def app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return create_app()
