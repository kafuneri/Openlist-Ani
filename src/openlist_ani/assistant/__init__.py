"""
Assistant module for interactive chatbot integration.
"""

from .assistant import AniAssistant
from .telegram_assistant import TelegramAssistant

__all__ = ["AniAssistant", "TelegramAssistant"]
