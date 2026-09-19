"""Model ladders (§5.3): try each rung in order, rebuilding context for its budget."""

import logging
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path

import yaml
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from rica.settings import Settings

log = logging.getLogger(__name__)

# Aliases the agent must never call: they route back to the agent (or to LiteLLM fallbacks)
FORBIDDEN_ALIASES = {"rica", "chat-auto"}
BUDGET_SAFETY = 0.9
LOCAL = "local"


class ModelSpec(BaseModel):
    input_budget: int
    max_output: int
    evidence_budget: int = 0  # 0 = whatever the input budget leaves
    timeout: float = 60
    params: dict = Field(default_factory=dict)


class LaddersConfig(BaseModel):
    models: dict[str, ModelSpec]
    ladders: dict[str, list[str]]


@dataclass(frozen=True)
class Rung:
    alias: str
    spec: ModelSpec

    @property
    def input_budget(self) -> int:
        return int(self.spec.input_budget * BUDGET_SAFETY)


class AllRungsFailed(Exception):
    def __init__(self, ladder: str, attempts: list[str]):
        super().__init__(f"all rungs of {ladder!r} failed: {attempts}")
        self.attempts = attempts


ModelFactory = Callable[[Rung], BaseChatModel]
BuildMessages = Callable[[Rung], list[BaseMessage]]


def _json_payload(text: str) -> str:
    """Models sometimes wrap JSON in code fences or add a sentence around it."""
    m = re.search(r"\{.*\}", text, re.S)
    return m.group(0) if m else text


class ModelLayer:
    def __init__(self, config: LaddersConfig, factory: ModelFactory):
        for name, aliases in config.ladders.items():
            bad = FORBIDDEN_ALIASES.intersection(aliases)
            if bad:
                raise ValueError(f"ladder {name!r} uses forbidden aliases {bad} (recursion guard)")
            missing = set(aliases) - set(config.models)
            if missing:
                raise ValueError(f"ladder {name!r} uses unknown aliases {missing}")
        self.config = config
        self._factory = factory

    @classmethod
    def from_settings(cls, settings: Settings) -> "ModelLayer":
        config = load_config(settings.ladders_file)

        def factory(rung: Rung) -> BaseChatModel:
            return ChatOpenAI(
                model=rung.alias,
                base_url=settings.litellm_base_url,
                api_key=settings.litellm_master_key,
                max_tokens=rung.spec.max_output,
                timeout=rung.spec.timeout,
                max_retries=0,  # the ladder is the retry policy
                **rung.spec.params,
            )

        return cls(config, factory)

    def ladder(self, name: str) -> list[Rung]:
        return [Rung(a, self.config.models[a]) for a in self.config.ladders[name]]

    def model(self, alias: str) -> BaseChatModel:
        return self._factory(Rung(alias, self.config.models[alias]))

    async def structured[T: BaseModel](
        self, ladder: str, build: BuildMessages, schema: type[T], attempts: list[str]
    ) -> tuple[T, str]:
        """Returns (validated output, alias). Invalid output advances to the next rung."""
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()},
        }
        for rung in self.ladder(ladder):
            try:
                model = self._factory(rung).bind(response_format=response_format)
                msg = await model.ainvoke(build(rung))
                result = schema.model_validate_json(_json_payload(msg.text))
            except Exception as e:
                log.warning("%s: %s failed: %s: %s", ladder, rung.alias, type(e).__name__, str(e)[:300])
                attempts.append(f"{rung.alias}:{type(e).__name__}")
                continue
            attempts.append(f"{rung.alias}:ok")
            return result, rung.alias
        raise AllRungsFailed(ladder, attempts)

    async def stream(
        self, ladder: str, build: BuildMessages, attempts: list[str]
    ) -> AsyncIterator[tuple[str, str]]:
        """Yields (alias, text). Falls back only before the first token: once text has
        reached the user, a failure is raised instead of mixing two models' answers."""
        for rung in self.ladder(ladder):
            started = False
            try:
                async for chunk in self._factory(rung).astream(build(rung)):
                    if text := chunk.text:
                        started = True
                        yield rung.alias, text
            except Exception as e:
                if started:
                    attempts.append(f"{rung.alias}:cut:{type(e).__name__}")
                    raise
                log.warning("%s: %s failed: %s: %s", ladder, rung.alias, type(e).__name__, str(e)[:300])
                attempts.append(f"{rung.alias}:{type(e).__name__}")
                continue
            if started:
                attempts.append(f"{rung.alias}:ok")
                return
            log.warning("%s: %s returned an empty answer", ladder, rung.alias)
            attempts.append(f"{rung.alias}:empty")
        raise AllRungsFailed(ladder, attempts)


def load_config(path: Path) -> LaddersConfig:
    return LaddersConfig.model_validate(yaml.safe_load(path.read_text()))
