"""
Telegram bot integration for assistant.
"""

import asyncio
from typing import Dict, List

import aiohttp

from ..config import config
from ..core.download import DownloadManager
from ..logger import logger
from .assistant import AniAssistant


class TelegramAssistant:
    """Telegram bot that integrates with AniAssistant."""

    def __init__(self, download_manager: DownloadManager):
        """Initialize Telegram assistant.

        Args:
            download_manager: DownloadManager instance
        """
        self.download_manager = download_manager
        self.assistant = AniAssistant(download_manager)
        self.bot_token = config.assistant.telegram.bot_token
        self.allowed_users = set(config.assistant.telegram.allowed_users)
        self.api_base = f"https://api.telegram.org/bot{self.bot_token}"

        # Shared HTTP session for all API calls
        self.session = None

        # Store conversation history for each user
        self.user_histories: Dict[int, List[dict]] = {}

        # Store status message IDs for each chat
        self.status_messages: Dict[int, int] = {}

        # Offset for long polling
        self.update_offset = 0

        logger.info(
            f"Telegram assistant initialized. Allowed users: {self.allowed_users}"
        )

    async def send_message(self, chat_id: int, text: str) -> int:
        """Send message to Telegram user.

        Args:
            chat_id: Telegram chat ID
            text: Message text

        Returns:
            Message ID if successful, 0 otherwise
        """
        url = f"{self.api_base}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
        }

        try:
            async with self.session.post(url, json=payload, timeout=30) as response:
                response.raise_for_status()
                data = await response.json()
                if data.get("ok"):
                    return data.get("result", {}).get("message_id", 0)
                return 0
        except Exception as e:
            logger.error(f"Failed to send Telegram message to {chat_id}: {e}")
            return 0

    async def edit_message(self, chat_id: int, message_id: int, text: str) -> bool:
        """Edit an existing message.

        Args:
            chat_id: Telegram chat ID
            message_id: Message ID to edit
            text: New message text

        Returns:
            True if successful
        """
        url = f"{self.api_base}/editMessageText"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }

        try:
            async with self.session.post(url, json=payload, timeout=30) as response:
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(
                f"Failed to edit Telegram message {message_id} in chat {chat_id}: {e}"
            )
            return False

    async def get_updates(self, timeout: int = 30) -> List[dict]:
        """Get updates from Telegram using long polling.

        Args:
            timeout: Long polling timeout in seconds

        Returns:
            List of update objects
        """
        url = f"{self.api_base}/getUpdates"
        params = {
            "offset": self.update_offset,
            "timeout": timeout,
        }

        try:
            async with self.session.get(
                url, params=params, timeout=timeout + 10
            ) as response:
                response.raise_for_status()
                data = await response.json()

                if data.get("ok"):
                    return data.get("result", [])
                else:
                    logger.error(f"Telegram API error: {data}")
                    return []
        except asyncio.TimeoutError:
            # Timeout is expected with long polling
            return []
        except Exception as e:
            logger.error(f"Failed to get Telegram updates: {e}")
            return []

    async def process_update(self, update: dict) -> None:
        """Process a single Telegram update.

        Args:
            update: Telegram update object
        """
        update_id = update.get("update_id")
        if update_id:
            self.update_offset = max(self.update_offset, update_id + 1)

        message = update.get("message")
        if not message:
            return

        chat_id = message.get("chat", {}).get("id")
        user_id = message.get("from", {}).get("id")
        text = message.get("text")

        if not chat_id or not text:
            return

        # Check if user is allowed
        if self.allowed_users and user_id not in self.allowed_users:
            logger.warning(f"Unauthorized user {user_id} tried to use bot")
            await self.send_message(
                chat_id, "❌ You are not authorized to use this bot"
            )
            return

        logger.info(f"Received message from {user_id}: {text}")

        # Handle /start command
        if text == "/start":
            welcome_msg = """👋 Hello! I'm an anime resource download assistant.

I can help you:
1️⃣ Download anime resources from RSS feeds
2️⃣ Search for resources on mikan.moe, dmhy, acg.rip and other websites
3️⃣ View search results and decide what to download

Usage examples:
- "Search for Frieren"
- "Search for Oshi no Ko on mikan"
- "Download this RSS: https://mikan.moe/RSS/..."

Note: I will respond in the same language you use to communicate with me!

Start chatting with me!"""
            await self.send_message(chat_id, welcome_msg)
            return

        # Handle /clear command to clear history
        if text == "/clear":
            if user_id in self.user_histories:
                del self.user_histories[user_id]
            await self.send_message(chat_id, "✅ Conversation history cleared")
            return

        # Get user's conversation history
        if user_id not in self.user_histories:
            self.user_histories[user_id] = []

        history = self.user_histories[user_id]

        # Process message with assistant
        try:
            # Create status callback for this chat
            async def status_callback(status: str):
                """Update status message in chat."""
                if chat_id in self.status_messages:
                    # Edit existing status message
                    await self.edit_message(
                        chat_id, self.status_messages[chat_id], status
                    )
                else:
                    # Send new status message
                    msg_id = await self.send_message(chat_id, status)
                    if msg_id:
                        self.status_messages[chat_id] = msg_id

            # Process message with status updates
            response = await self.assistant.process_message(
                text, history, status_callback
            )

            # Delete status message if exists
            if chat_id in self.status_messages:
                await self._delete_message(chat_id, self.status_messages[chat_id])
                del self.status_messages[chat_id]

            # Update history
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": response})

            # Limit history size
            max_history = self.assistant.max_history * 2  # user + assistant pairs
            if len(history) > max_history:
                history[:] = history[-max_history:]

            # Send response
            await self.send_message(chat_id, response)

        except Exception as e:
            logger.exception(f"Error processing message from {user_id}")
            await self.send_message(chat_id, f"❌ Error processing message: {str(e)}")

    async def _delete_message(self, chat_id: int, message_id: int) -> bool:
        """Delete a message.

        Args:
            chat_id: Telegram chat ID
            message_id: Message ID to delete

        Returns:
            True if successful
        """
        url = f"{self.api_base}/deleteMessage"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
        }

        try:
            async with self.session.post(url, json=payload, timeout=5) as response:
                response.raise_for_status()
                return True
        except Exception:
            return False  # Not critical if this fails

    async def run(self) -> None:
        """Run the Telegram bot (long polling loop)."""
        logger.info("Starting Telegram assistant...")

        if not self.bot_token:
            logger.error("Telegram bot token not configured")
            return

        async with aiohttp.ClientSession(trust_env=True) as self.session:
            await self._run_polling_loop()

    async def _run_polling_loop(self) -> None:
        # Get bot info
        try:
            async with self.session.get(
                f"{self.api_base}/getMe", timeout=10
            ) as response:
                response.raise_for_status()
                data = await response.json()
                if data.get("ok"):
                    bot_info = data.get("result", {})
                    logger.info(
                        f"Bot started: @{bot_info.get('username')} ({bot_info.get('first_name')})"
                    )
        except Exception as e:
            logger.error(f"Failed to get bot info: {e}")
            return

        # Main polling loop
        while True:
            try:
                updates = await self.get_updates()

                for update in updates:
                    try:
                        await self.process_update(update)
                    except Exception as e:
                        logger.exception(f"Error processing update: {e}")

            except Exception as e:
                logger.exception(f"Error in Telegram polling loop: {e}")
                await asyncio.sleep(5)  # Wait before retrying
