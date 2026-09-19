"""Route registry: what RICA can do. Capabilities in the prompt are generated from it (§6.4)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    name: str
    enabled: bool
    can: str | None  # capability line; None = not listed
    cannot: str  # used in the "cannot (yet)" line while disabled
    planner: str  # when the planner should pick this route


ROUTES: list[Route] = [
    Route(
        "chat",
        True,
        None,
        "",
        "conversation, writing, reasoning, general knowledge, questions about RICA "
        "itself, or the current date/time",
    ),
    Route(
        "docs",
        False,
        "Search and read {name}'s notes (Markdown knowledge base).",
        "search {name}'s notes",
        "anything about {name} or their notes, projects, people, or plans",
    ),
    Route(
        "web",
        False,
        "Search the web and read web pages.",
        "search the web",
        "current events, prices, recent facts, or anything that needs up-to-date information",
    ),
    Route(
        "url",
        False,
        "Read web pages from links {name} sends.",
        "open links",
        "the message contains a link that should be read",
    ),
]

# Always out of reach in Phase 1
NOT_YET = ["access calendar, email, or messages", "create or modify any files"]


def enabled_routes() -> list[Route]:
    return [r for r in ROUTES if r.enabled]


def enabled_names() -> set[str]:
    return {r.name for r in enabled_routes()}
