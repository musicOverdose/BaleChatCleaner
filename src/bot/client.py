"""
Bot and Dispatcher initialization for BaleChatCleaner.
Connects aiogram to Bale Bot API endpoint (https://tapi.bale.ai).
"""

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage
from src.config import Settings


def create_bot_and_dispatcher(settings: Settings):
    """
    Creates the Bot instance configured with the Bale API endpoint and a Dispatcher.
    """
    session = AiohttpSession(
        api=TelegramAPIServer.from_base(settings.BALE_API_ENDPOINT)
    )
    bot = Bot(token=settings.BOT_TOKEN, session=session)
    dp = Dispatcher(storage=MemoryStorage())
    return bot, dp
