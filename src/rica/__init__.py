"""RICA - A Rather Intelligent Conversational Assistant."""

__version__ = "0.1.0"
__author__ = "Siam Rahman"
__email__ = "siam@graduate.utm.my"

from .core.assistant import RICA
from .core.agent_manager import AgentManager

__all__ = ["RICA", "AgentManager"]
