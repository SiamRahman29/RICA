"""Route registry: what RICA can do. Capabilities in the prompt are generated from it (§6.4)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    name: str
    enabled: bool
    can: str | None  # capability line; None = not listed
    cannot: str  # used in the "cannot (yet)" line while disabled
    planner: str  # when the planner should pick this route
    planner_fields: str = ""  # how to fill the plan fields this route uses


ROUTES: list[Route] = [
    Route(
        "chat",
        True,
        None,
        "",
        "conversation, writing, reasoning, general knowledge, questions about RICA itself, "
        "the current date or time (RICA is given them), and requests for things RICA can't do "
        "(calendar, email, messages, files), so it can say so. Use chat alone when nothing about "
        "{name} needs looking up and no current information from the web is needed",
    ),
    Route(
        "docs",
        True,
        "Search and read {name}'s notes (Markdown knowledge base).",
        "search {name}'s notes",
        "any question whose answer could depend on {name}'s own life: their background, people, "
        "preferences and habits, belongings, plans, projects, or anything they wrote down. "
        "Use it even for casual questions (\"how do I take my coffee?\", \"when is my car due?\")",
        "For docs: doc_filter=about_me when the question is about {name} personally, else any. "
        "doc_mode: facts for specific questions (the usual case); whole_doc only to summarize or "
        "discuss one whole note (put its name or topic in doc_hint); find_docs only when {name} "
        "asks which notes mention something or where they wrote about it.",
    ),
    Route(
        "web",
        True,
        "Search the web and read web pages.",
        "search the web",
        "news, current events, prices, weather, schedules, recent releases, or facts you are "
        "not sure of. Use BOTH docs and web when {name} asks whether something of theirs is "
        "typical, normal, good, or up to date (\"is my X normal?\", \"is my plan realistic?\")",
        "For web: search_queries = 1-3 short keyword queries (different angles, not rephrasings); "
        "recency = day or week for news and fast-changing facts, else any; snippets_sufficient = true "
        "only for one simple fact a search snippet would show (a date, a score, a price).",
    ),
    Route(
        "url",
        True,
        "Read web pages from links {name} sends.",
        "open links",
        "the message contains a link. Don't add web just to read a link; add it only if the "
        "request also needs other sources",
    ),
]

# Always out of reach in Phase 1
NOT_YET = ["access calendar, email, or messages", "create or modify any files"]


def enabled_routes() -> list[Route]:
    return [r for r in ROUTES if r.enabled]


def enabled_names() -> set[str]:
    return {r.name for r in enabled_routes()}
