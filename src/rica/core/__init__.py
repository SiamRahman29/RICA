"""Core functionality for the RICA."""

from .assistant import RICA
from .agent_manager import AgentManager
from .config import Config

__all__ = ["RICA", "AgentManager", "Config"]
