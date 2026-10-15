"""
Authorization Middleware for BaleChatCleaner.
Protects the administrative panel while allowing group/channel tracking.
"""

from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from src.config import Settings


class AdminAuthMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings):
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # If no admin IDs are specified, permit access (or restrict to first caller)
        admin_ids = self.settings.ADMIN_IDS
        if not admin_ids:
            return await handler(event, data)

        # Check if the interaction is a private chat message or callback
        user_id = None
        is_private = False

        if isinstance(event, Message):
            is_private = event.chat.type == "private"
            user_id = event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            is_private = event.message and event.message.chat.type == "private"
            user_id = event.from_user.id if event.from_user else None

        if is_private and user_id is not None:
            if user_id not in admin_ids:
                if isinstance(event, Message):
                    await event.reply("⛔ **Access Denied**\nYou are not authorized to use this bot.")
                elif isinstance(event, CallbackQuery):
                    await event.answer("⛔ Access Denied.", show_alert=True)
                return

        return await handler(event, data)
