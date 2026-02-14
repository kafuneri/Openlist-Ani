"""Tests for BotFactory."""

from unittest.mock import MagicMock

import pytest

from openlist_ani.core.notification.bot.base import BotType
from openlist_ani.core.notification.bot.factory import BotFactory
from openlist_ani.core.notification.bot.pushplus import PushPlusBot, PushPlusChannel
from openlist_ani.core.notification.bot.telegram import TelegramBot


class TestBotFactory:
    def test_create_telegram_bot(self):
        bot = BotFactory.create_bot(
            BotType.TELEGRAM,
            {"bot_token": "tok", "user_id": 123},
        )
        assert isinstance(bot, TelegramBot)
        assert bot.bot_token == "tok"
        assert bot.user_id == 123

    def test_create_pushplus_bot(self):
        bot = BotFactory.create_bot(
            BotType.PUSHPLUS,
            {"user_token": "tok"},
        )
        assert isinstance(bot, PushPlusBot)

    def test_create_pushplus_with_channel(self):
        bot = BotFactory.create_bot(
            BotType.PUSHPLUS,
            {"user_token": "tok", "channel": "mail"},
        )
        assert bot.channel == PushPlusChannel.MAIL

    def test_telegram_missing_token_raises(self):
        with pytest.raises(ValueError, match="bot_token"):
            BotFactory.create_bot(BotType.TELEGRAM, {"user_id": 1})

    def test_telegram_missing_user_id_raises(self):
        with pytest.raises(ValueError, match="user_id"):
            BotFactory.create_bot(BotType.TELEGRAM, {"bot_token": "t"})

    def test_pushplus_missing_token_raises(self):
        with pytest.raises(ValueError, match="user_token"):
            BotFactory.create_bot(BotType.PUSHPLUS, {})

    def test_unknown_bot_type_raises(self):
        """Passing an invalid BotType-like value should raise ValueError."""
        fake_type = MagicMock()
        fake_type.__eq__ = lambda self, other: False
        with pytest.raises(ValueError, match="Unknown bot type"):
            BotFactory.create_bot(fake_type, {})
