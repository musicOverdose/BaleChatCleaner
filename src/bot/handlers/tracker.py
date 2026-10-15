"""
Background Message Tracker and Forward Listener Handler.
Supports both direct channel/group message indexing and instant forward-to-register.
"""

import logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, ChatMemberUpdated
from src.database.db import DatabaseManager
from src.cleaner.filters import get_message_content_type

logger = logging.getLogger(__name__)
tracker_router = Router(name="tracker")


@tracker_router.message(Command("check", "ping", "status"), F.chat.type.in_({"group", "supergroup", "channel"}))
@tracker_router.channel_post(Command("check", "ping", "status"))
async def check_group_status(message: Message, db: DatabaseManager):
    """
    Replies in chat to confirm bot presence, log current message ID, and report stats.
    """
    chat_id = message.chat.id
    chat_title = message.chat.title or f"Chat {chat_id}"
    chat_username = message.chat.username
    uname_str = f"@{chat_username}" if chat_username else f"ID: {chat_id}"

    await db.upsert_chat(chat_id=chat_id, title=chat_title, chat_type=message.chat.type, username=chat_username)
    await db.save_message(
        chat_id=chat_id,
        message_id=str(message.message_id),
        date=int(message.date.timestamp()) if message.date else 0,
        content_type="text",
        sender_id=message.from_user.id if message.from_user else None,
    )
    stats = await db.get_tracked_count(chat_id)
    total = sum(stats.values())
    stats_breakdown = ", ".join(f"{k}: {v}" for k, v in stats.items()) or "None"

    try:
        await message.reply(
            f"🤖 **BaleChatCleaner Status**\n\n"
            f"• **Chat:** {chat_title} (`{uname_str}`)\n"
            f"• **Chat ID:** `{chat_id}`\n"
            f"• **Latest Message ID:** `{message.message_id}`\n"
            f"• **Tracked Messages:** `{total}` ({stats_breakdown})\n\n"
            "🧹 *To configure cleaning, message the bot in private chat: `/panel` or `/clean`.*"
        )
    except Exception as e:
        logger.warning(f"Could not send reply in chat {chat_id}: {e}")


@tracker_router.channel_post()
@tracker_router.message(F.chat.type.in_({"group", "supergroup", "channel"}))
async def track_chat_message(message: Message, db: DatabaseManager):
    """
    Indexes messages posted in channels or groups where the bot is present.
    In Bale, channel posts can arrive under either message or channel_post.
    """
    chat_id = message.chat.id
    chat_title = message.chat.title or f"Chat {chat_id}"
    chat_type = message.chat.type
    chat_username = message.chat.username

    # Ensure chat is recorded with username
    await db.upsert_chat(chat_id=chat_id, title=chat_title, chat_type=chat_type, username=chat_username)

    # Detect primary content type
    content_type = get_message_content_type(message)
    sender_id = message.from_user.id if message.from_user else None
    msg_date = int(message.date.timestamp()) if message.date else 0

    await db.save_message(
        chat_id=chat_id,
        message_id=str(message.message_id),
        date=msg_date,
        content_type=content_type,
        sender_id=sender_id,
    )
    logger.info(f"✅ Tracked msg {message.message_id} in {chat_title} (@{chat_username}) [{content_type}]")


@tracker_router.message(F.chat.type == "private", F.forward_from_chat)
async def track_forwarded_message(message: Message, db: DatabaseManager):
    """
    Registers a channel/group and its message ID when an admin forwards a post to the bot.
    This is the most reliable way in Bale to discover channels and extract exact message IDs.
    """
    f_chat = message.forward_from_chat
    orig_msg_id = message.forward_from_message_id
    chat_id = f_chat.id
    chat_title = f_chat.title or f"Chat {chat_id}"
    chat_type = f_chat.type
    chat_username = f_chat.username

    # Upsert the chat into database
    await db.upsert_chat(chat_id=chat_id, title=chat_title, chat_type=chat_type, username=chat_username)

    # Detect content type
    content_type = get_message_content_type(message)
    msg_date = int(message.forward_date.timestamp()) if message.forward_date else 0

    if orig_msg_id is not None:
        await db.save_message(
            chat_id=chat_id,
            message_id=str(orig_msg_id),
            date=msg_date,
            content_type=content_type,
            sender_id=None,
        )

    uname_str = f"@{chat_username}" if chat_username else f"ID: {chat_id}"
    logger.info(f"Channel {chat_title} ({uname_str}) registered via forwarded message {orig_msg_id}")

    await message.reply(
        f"✅ **Channel Detected & Registered!**\n\n"
        f"• **Title:** {chat_title}\n"
        f"• **Channel Handle:** `{uname_str}`\n"
        f"• **Channel ID:** `{chat_id}`\n"
        f"• **Extracted Message ID:** `{orig_msg_id}`\n"
        f"• **Detected Type:** `{content_type}`\n\n"
        "💡 *You can now open `/panel` or `/clean` to configure cleaning for this channel.*"
    )


@tracker_router.my_chat_member()
async def track_bot_membership(event: ChatMemberUpdated, db: DatabaseManager):
    """
    Detects when the bot is added or promoted to admin in a channel or group.
    """
    chat = event.chat
    new_status = event.new_chat_member.status

    if new_status in ("administrator", "member"):
        title = chat.title or f"Chat {chat.id}"
        await db.upsert_chat(chat_id=chat.id, title=title, chat_type=chat.type, username=chat.username)
        logger.info(f"Bot registered in chat {title} (@{chat.username}) with status '{new_status}'")

