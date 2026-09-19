"""Approximate token counts. o200k is close enough for budgeting all our models."""

import tiktoken
from langchain_core.messages import BaseMessage

_enc = tiktoken.get_encoding("o200k_base")

# Per-message overhead for role/formatting tokens
MESSAGE_OVERHEAD = 4


def count(text: str) -> int:
    return len(_enc.encode(text, disallowed_special=()))


def count_messages(messages: list[BaseMessage]) -> int:
    return sum(count(m.text) + MESSAGE_OVERHEAD for m in messages)


def truncate(text: str, max_tokens: int) -> str:
    """Keep the end of the text: for a user message, the question is usually last."""
    tokens = _enc.encode(text, disallowed_special=())
    if len(tokens) <= max_tokens:
        return text
    return "…" + _enc.decode(tokens[-max(max_tokens - 1, 0) :])
