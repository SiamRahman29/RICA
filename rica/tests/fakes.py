from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from rica.llm import LaddersConfig, ModelLayer, ModelSpec


class Scripted(BaseChatModel):
    """Replies with a fixed text, or raises; records what it was sent."""

    reply: str = ""
    error: bool = False
    fail_after_first: bool = False
    calls: list = []

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, messages, stop=None, run_manager=None, **kw):
        self.calls.append(messages)
        if self.error:
            raise RuntimeError("provider down")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(self.reply))])

    async def _astream(self, messages, stop=None, run_manager=None, **kw):
        self.calls.append(messages)
        if self.error:
            raise RuntimeError("provider down")
        for i, word in enumerate(self.reply.split(" ")):
            if i == 1 and self.fail_after_first:
                raise RuntimeError("connection reset")
            yield ChatGenerationChunk(message=AIMessageChunk(content=word if i == 0 else " " + word))


CONFIG = LaddersConfig(
    models={
        "groq-fast": ModelSpec(input_budget=3000, max_output=400),
        "groq-smart": ModelSpec(input_budget=6000, max_output=1500),
        "gemini-flash": ModelSpec(input_budget=60000, max_output=2048),
        "gemini-lite": ModelSpec(input_budget=30000, max_output=1024),
        "local": ModelSpec(input_budget=3000, max_output=768),
    },
    ladders={
        "understand": ["groq-fast", "gemini-lite", "local"],
        "answer": ["groq-smart", "gemini-flash", "local"],
        "answer_long": ["gemini-flash", "groq-smart", "local"],
    },
)


def layer(**models: Scripted) -> ModelLayer:
    """Aliases not given fail. Pass e.g. groq_smart=Scripted(reply=...)."""
    by_alias = {k.replace("_", "-"): v for k, v in models.items()}
    return ModelLayer(CONFIG, lambda rung: by_alias.get(rung.alias) or Scripted(error=True))
