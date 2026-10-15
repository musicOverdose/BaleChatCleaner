"""
Message Probing Engine for Retroactive Message Type Inspection.
Allows inspecting the content_type of historic messages posted before the bot was added.
"""

import logging
from typing import Optional
from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNotFound,
    TelegramAPIError,
)
from src.cleaner.filters import get_message_content_type

logger = logging.getLogger(__name__)


class MessageProber:
    def __init__(self, bot: Bot, scratch_chat_id: Optional[int] = None):
        self.bot = bot
        self.scratch_chat_id = scratch_chat_id

    async def probe_message_type(self, source_chat_id: int, message_id: int) -> Optional[str]:
        """
        Attempts to forward the message to a scratch chat to inspect its content_type.
        Immediately deletes the forwarded copy.
        Returns the content_type string ('text', 'photo', etc.) or None if message does not exist.
        """
        if not self.scratch_chat_id:
            logger.debug("No scratch_chat_id configured for probing; cannot inspect historical type.")
            return None

        try:
            forwarded = await self.bot.forward_message(
                chat_id=self.scratch_chat_id,
                from_chat_id=source_chat_id,
                message_id=message_id,
            )
            content_type = get_message_content_type(forwarded)

            # Cleanup the scratch message immediately
            try:
                await self.bot.delete_message(
                    chat_id=self.scratch_chat_id,
                    message_id=forwarded.message_id,
                )
            except Exception as e:
                logger.debug(f"Failed to delete scratch probe message: {e}")

            return content_type

        except (TelegramBadRequest, TelegramNotFound, TelegramAPIError) as e:
            err_msg = str(e).lower()
            if "not found" in err_msg or "message to forward not found" in err_msg or "message to be replied not found" in err_msg:
                logger.debug(f"Message {message_id} not found during probe: {e}")
                return None
            if "permission_denied" in err_msg or "forbidden" in err_msg or "chat not found" in err_msg:
                logger.debug(f"Cannot forward message {message_id} for probe: {e}")
                return None
            logger.warning(f"API error probing message {message_id}: {e}")
            return None
        except TelegramForbiddenError:
            logger.debug(f"Forbidden from forwarding message {message_id} to scratch chat.")
            return None
        except Exception as e:
            err_msg = str(e).lower()
            if "not found" in err_msg:
                logger.debug(f"Message {message_id} not found during probe: {e}")
                return None
            logger.warning(f"Unexpected error probing message {message_id}: {e}")
            return None
