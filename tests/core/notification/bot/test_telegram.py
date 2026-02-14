"""Tests for TelegramBot."""

from openlist_ani.core.notification.bot.base import BotBase
from openlist_ani.core.notification.bot.telegram import TelegramBot


class TestTelegramBot:
    def test_init(self):
        bot = TelegramBot(bot_token="tok123", user_id=42)
        assert bot.bot_token == "tok123"
        assert bot.user_id == 42
        assert bot.support_markdown is True

    def test_is_instance_of_base(self):
        bot = TelegramBot(bot_token="t", user_id=1)
        assert isinstance(bot, BotBase)
