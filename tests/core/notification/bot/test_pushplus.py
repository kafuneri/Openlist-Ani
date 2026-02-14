"""Tests for PushPlusBot and PushPlusChannel."""

import pytest

from openlist_ani.core.notification.bot.base import BotBase
from openlist_ani.core.notification.bot.pushplus import PushPlusBot, PushPlusChannel


class TestPushPlusBot:
    def test_init_defaults_to_wechat(self):
        bot = PushPlusBot(user_token="tok")
        assert bot.channel == PushPlusChannel.WECHAT

    def test_init_with_valid_channel(self):
        bot = PushPlusBot(user_token="tok", channel="webhook")
        assert bot.channel == PushPlusChannel.WEBHOOK

    def test_init_with_invalid_channel_raises(self):
        with pytest.raises(ValueError, match="Invalid channel"):
            PushPlusBot(user_token="tok", channel="invalid_channel")

    def test_is_instance_of_base(self):
        bot = PushPlusBot(user_token="tok")
        assert isinstance(bot, BotBase)


class TestPushPlusChannel:
    def test_all_channels(self):
        assert PushPlusChannel.WECHAT.value == "wechat"
        assert PushPlusChannel.WEBHOOK.value == "webhook"
        assert PushPlusChannel.CP.value == "cp"
        assert PushPlusChannel.MAIL.value == "mail"
