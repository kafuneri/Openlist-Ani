"""Tests for BotBase abstract class and BotType enum."""

import pytest

from openlist_ani.core.notification.bot.base import BotBase, BotType


class TestBotType:
    def test_telegram_value(self):
        assert BotType.TELEGRAM.value == "telegram"

    def test_pushplus_value(self):
        assert BotType.PUSHPLUS.value == "pushplus"

    def test_from_string(self):
        assert BotType("telegram") == BotType.TELEGRAM

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError):
            BotType("unknown_service")


class TestBotBaseIsAbstract:
    def test_cannot_instantiate(self):
        """BotBase is abstract — direct instantiation should fail."""
        with pytest.raises(TypeError):
            BotBase()
