"""
Background Message Tracker Handler.
Passively logs incoming messages in channels and groups for accurate historical cleaning.
"""

import logging
from aiogram import Router, F
from aiogram.types import Message, ChatMemberUpdated
from src.database.db import DatabaseManager
from src.cleaner.filters import get_message_content_type

logger = logging.getLogger(__name__)
tracker_router = Router(name="tracker")


@tracker_router.channel_post()
@tracker_router.message(F.chat.type.in_({"group", "supergroup"}))
async def track_chat_message(message: Message, db: DatabaseManager):
    """
    Indexes messages posted in channels or groups where the bot is present.
    """
    chat_id = message.chat.id
    chat_title = message.chat.title or f"Chat {chat_id}"
    chat_type = message.chat.type

    # Ensure chat is recorded
    await db.upsert_chat(chat_id=chat_id, title=chat_title, chat_type=chat_type)

    # Detect primary content type
    content_type = get_message_content_type(message)
    sender_id = message.from_user.id if message.from_user else None
    msg_date = int(message.date.timestamp()) if message.date else 0

    await db.save_message(
        chat_id=chat_id,
        message_id=message.message_id,
        date=msg_date,
        content_type=content_type,
        sender_id=sender_id,
    )
    logger.debug(f"Tracked msg {message.message_id} in {chat_title} [{content_type}]")


@tracker_router.my_chat_member()
async def track_bot_membership(event: ChatMemberUpdated, db: DatabaseManager):
    """
    Detects when the bot is added or promoted to admin in a channel or group.
    """
    chat = event.chat
    new_status = event.new_chat_member.status

    if new_status in ("administrator", "member"):
        title = chat.title or f"Chat {chat.id}"
        await db.upsert_chat(chat_id=chat.id, title=title, chat_type=chat.type)
        logger.info(f"Bot registered in chat {title} ({chat.id}) with status '{new_status}'")
