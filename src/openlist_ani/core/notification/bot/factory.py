from typing import Any

from .base import BotBase, BotType
from .pushplus import PushPlusBot
from .telegram import TelegramBot


class BotFactory:
    """Factory for creating notification bot instances."""

    @staticmethod
    def create_bot(bot_type: BotType, config: dict[str, Any]) -> BotBase:
        """
        Create a bot instance based on type and configuration.

        Args:
            bot_type: Type of bot to create (telegram or pushplus)
            config: Configuration dictionary with bot-specific parameters

        Returns:
            Bot instance

        Raises:
            ValueError: If bot_type is unknown or required config is missing
        """
        if bot_type == BotType.TELEGRAM:
            bot_token = config.get("bot_token")
            user_id = config.get("user_id")
            if not bot_token or not user_id:
                raise ValueError(
                    "Telegram bot requires 'bot_token' and 'user_id' in config"
                )
            return TelegramBot(bot_token=bot_token, user_id=user_id)

        elif bot_type == BotType.PUSHPLUS:
            user_token = config.get("user_token")
            if not user_token:
                raise ValueError("PushPlus bot requires 'user_token' in config")
            channel = config.get("channel")
            return PushPlusBot(user_token=user_token, channel=channel)

        else:
            raise ValueError(f"Unknown bot type: {bot_type}")
