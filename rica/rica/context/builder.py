"""Assembles the answer prompt (§6.6) and fits history into a rung's budget."""

from datetime import datetime
from functools import cache

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from rica.context import tokens
from rica.context.profile import Profile
from rica.routes import NOT_YET, ROUTES
from rica.settings import PACKAGE_DIR


@cache
def _template(name: str) -> str:
    return (PACKAGE_DIR / "context" / name).read_text().strip()


def format_now(now: datetime) -> str:
    return f"{now:%A, %d %B %Y, %H:%M} ({now.tzinfo}, UTC{now:%z})"


def capabilities(name: str) -> str:
    can = [r.can.format(name=name) for r in ROUTES if r.enabled and r.can]
    cannot = [r.cannot.format(name=name) for r in ROUTES if not r.enabled and r.cannot] + NOT_YET
    lines = ["You can:", f"- Chat, write, and reason using your own knowledge and what {name} tells you in this chat."]
    lines += [f"- {c}" for c in can]
    lines.append(f"You cannot (yet): {', '.join(cannot[:-1])}, or {cannot[-1]}.")
    return "\n".join(lines)


def owner_profile(p: Profile) -> str:
    facts = []
    if p.name and p.name != p.preferred_name:
        facts.append(f"Name: {p.name} (call them {p.preferred_name})")
    else:
        facts.append(f"Name: {p.preferred_name}")
    if p.location:
        facts.append(f"Location: {p.location}")
    if p.languages:
        facts.append(f"Languages: {', '.join(p.languages)}")
    facts.append(f"Timezone: {p.timezone}")
    body = "\n".join(facts) + (f"\n\n{p.body}" if p.body else "")
    return f"<owner_profile>\n{body}\n</owner_profile>"


def stable_prefix(p: Profile) -> str:
    """Identical across requests until the profile changes, so providers can cache it."""
    name = p.preferred_name
    return "\n\n".join(
        [
            _template("identity.md").format(preferred_name=name),
            capabilities(name),
            owner_profile(p),
            _template("rules.md").format(preferred_name=name),
        ]
    )


def answer_system(p: Profile, now: datetime, tier: str, extra: str = "") -> str:
    parts = [stable_prefix(p), f"Now: {format_now(now)}. Tier: {tier}."]
    if extra:
        parts.append(f"<ui_instructions>\n{extra}\n</ui_instructions>")
    return "\n\n".join(parts)


def fit_history(history: list[BaseMessage], budget: int) -> list[BaseMessage]:
    """Keep the most recent messages that fit; always keep (a tail of) the latest one."""
    kept: list[BaseMessage] = []
    used = 0
    for m in reversed(history):
        t = tokens.count(m.text) + tokens.MESSAGE_OVERHEAD
        if used + t > budget:
            if not kept:
                room = max(budget - tokens.MESSAGE_OVERHEAD, 16)
                kept.append(m.model_copy(update={"content": tokens.truncate(m.text, room)}))
            break
        kept.append(m)
        used += t
    kept.reverse()
    while len(kept) > 1 and not isinstance(kept[0], HumanMessage):
        kept.pop(0)
    return kept


def answer_messages(
    p: Profile, now: datetime, tier: str, budget: int, history: list[BaseMessage], extra: str = ""
) -> list[BaseMessage]:
    system = SystemMessage(answer_system(p, now, tier, extra))
    room = budget - tokens.count_messages([system])
    return [system, *fit_history(history, room)]
