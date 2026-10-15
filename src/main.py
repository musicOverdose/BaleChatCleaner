"""
Main application entry point for BaleChatCleaner.
Initializes logging, database, anti-glitch engine, and bot polling with graceful shutdown.
"""

import asyncio
import logging
import signal
import sys
from src.config import Settings
from src.database.db import DatabaseManager
from src.cleaner.engine import AntiGlitchEngine
from src.cleaner.prober import MessageProber
from src.bot.client import create_bot_and_dispatcher
from src.bot.middlewares import AdminAuthMiddleware
from src.bot.handlers.admin import admin_router
from src.bot.handlers.callbacks import callbacks_router
from src.bot.handlers.tracker import tracker_router


def setup_logging(level: str):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )


async def main():
    try:
        settings = Settings()
    except Exception as e:
        print(f"FATAL: Configuration error. Please check your .env or environment variables: {e}")
        sys.exit(1)

    setup_logging(settings.LOG_LEVEL)
    logger = logging.getLogger("main")
    logger.info("Initializing BaleChatCleaner...")

    # Initialize Database
    db = DatabaseManager(settings.DB_PATH)
    await db.init_db()

    # Initialize Bot & Dispatcher
    bot, dp = create_bot_and_dispatcher(settings)

    # Initialize Message Prober and Anti-Glitch Engine
    scratch_id = settings.PROBE_SCRATCH_CHAT_ID or (settings.ADMIN_IDS[0] if settings.ADMIN_IDS else None)
    prober = MessageProber(bot, scratch_chat_id=scratch_id)
    engine = AntiGlitchEngine(bot, db, prober=prober)

    # Register Middlewares
    admin_middleware = AdminAuthMiddleware(settings)
    dp.message.middleware(admin_middleware)
    dp.callback_query.middleware(admin_middleware)

    # Register Routers
    dp.include_router(admin_router)
    dp.include_router(callbacks_router)
    dp.include_router(tracker_router)

    # Dependency Injection into handlers
    dp["db"] = db
    dp["engine"] = engine
    dp["settings"] = settings

    # Graceful Shutdown Handler
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def shutdown_signal():
        logger.info("Received termination signal. Shutting down gracefully...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown_signal)
        except NotImplementedError:
            # Not supported on some platforms (e.g. Windows)
            pass

    try:
        logger.info(f"Connecting to Bale Bot API at {settings.BALE_API_ENDPOINT}...")
        bot_info = await bot.get_me()
        logger.info(f"Bot connected successfully as @{bot_info.username} ({bot_info.id})")
        logger.info(f"Authorized Admins: {settings.ADMIN_IDS or 'Open / Not specified'}")

        # Start Long Polling (explicitly requesting message, channel_post, callback_query)
        allowed_updates = ["message", "edited_message", "channel_post", "edited_channel_post", "callback_query", "my_chat_member"]
        polling_task = asyncio.create_task(dp.start_polling(bot, allowed_updates=allowed_updates))

        # Wait until stop_event is signaled
        await stop_event.wait()

        # Stop polling gracefully
        await dp.stop_polling()
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass

    except Exception as e:
        logger.exception(f"Fatal error during bot execution: {e}")
    finally:
        logger.info("Closing bot session...")
        await bot.session.close()
        logger.info("BaleChatCleaner stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
