"""
Admin Commands and Panel Handlers for BaleChatCleaner.
"""

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from src.database.db import DatabaseManager
from src.bot.keyboards import main_menu_keyboard, filter_mode_keyboard

admin_router = Router(name="admin")


class CustomRangeState(StatesGroup):
    waiting_for_range = State()


class UserSpecificState(StatesGroup):
    waiting_for_user_id = State()


@admin_router.message(CommandStart(), F.chat.type == "private")
@admin_router.message(Command("panel"), F.chat.type == "private")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    text = (
        "🛡️ **Welcome to BaleChatCleaner**\n\n"
        "Advanced, anti-glitch message cleaner for Bale channels and groups.\n\n"
        "✨ **Features:**\n"
        "• Paced token-bucket rate limiting (prevents channel glitches & desync).\n"
        "• Filter by specific message types (Audio, Video, Photo, Docs, etc.).\n"
        "• **Negation Filter**: Delete all messages *except* your chosen types (e.g. keep audio & files).\n"
        "• **User-Specific Cleaning**: Target messages sent by a specific user.\n"
        "• Live real-time control (Pause, Resume, Abort) with progress tracking.\n\n"
        "Select an option below to manage your chats:"
    )
    await message.reply(text, reply_markup=main_menu_keyboard())


@admin_router.message(Command("clean"), F.chat.type == "private")
async def cmd_clean(message: Message, db: DatabaseManager, state: FSMContext):
    await state.clear()
    from src.bot.keyboards import chats_list_keyboard
    chats = await db.get_chats(active_only=True)
    if not chats:
        await message.reply(
            "⚠️ **No Chats Found**\n\n"
            "The bot has not been added to any channels or groups yet.\n"
            "Add the bot as an administrator with **Delete Messages** permissions, "
            "then send or post a test message to register it.",
            reply_markup=main_menu_keyboard(),
        )
        return
    await message.reply("📢 **Select Target Chat to Clean:**", reply_markup=chats_list_keyboard(chats))


@admin_router.message(Command("status"), F.chat.type == "private")
async def cmd_status(message: Message, db: DatabaseManager):
    active_jobs = await db.get_active_jobs()
    if not active_jobs:
        await message.reply("✅ **No active cleaning jobs currently running.**", reply_markup=main_menu_keyboard())
        return

    lines = ["🔄 **Active Cleaning Jobs:**\n"]
    for j in active_jobs:
        pct = int(((j.deleted_count + j.skipped_count) / max(1, j.target_count)) * 100)
        lines.append(
            f"• **{j.chat_title}** [{j.status.upper()}]\n"
            f"  Progress: {pct}% (`{j.deleted_count}` deleted, `{j.skipped_count}` skipped)\n"
            f"  Filter: `{j.filter_mode}` ({', '.join(j.filter_types) if j.filter_types else 'All'})\n"
        )
    await message.reply("\n".join(lines), reply_markup=main_menu_keyboard())


@admin_router.message(CustomRangeState.waiting_for_range, F.chat.type == "private")
async def process_custom_range(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data.get("chat_id")
    text = message.text.strip().replace("-", " ").replace(":", " ")
    parts = text.split()

    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        await message.reply(
            "❌ **Invalid Format**\n"
            "Please send two numbers representing the start and end Message IDs.\n"
            "Example: `100 500`"
        )
        return

    start_id = min(int(parts[0]), int(parts[1]))
    end_id = max(int(parts[0]), int(parts[1]))

    scope_str = f"range_{start_id}_{end_id}"
    await state.update_data(scope=scope_str, start_id=start_id, end_id=end_id)

    prompt = (
        f"🎯 **Target Scope Set:** Messages from ID `{start_id}` to `{end_id}`\n\n"
        "Now choose your **Filter Mode**:"
    )
    await message.reply(prompt, reply_markup=filter_mode_keyboard(chat_id, scope_str))


@admin_router.message(UserSpecificState.waiting_for_user_id, F.chat.type == "private")
async def process_user_id(message: Message, state: FSMContext):
    data = await state.get_data()
    chat_id = data.get("chat_id")
    scope = data.get("scope", "all")
    text = message.text.strip()
    if not text.isdigit():
        await message.reply(
            "❌ **Invalid User ID**\n"
            "Please send a numerical User ID.\n"
            "Example: `1194790059`"
        )
        return

    target_user_id = int(text)
    await state.update_data(target_user_id=target_user_id)
    from src.bot.keyboards import user_action_keyboard
    prompt = (
        f"👤 **Target User ID Selected:** `{target_user_id}`\n\n"
        "Choose an action for this user's messages:"
    )
    await message.reply(prompt, reply_markup=user_action_keyboard(chat_id, scope, target_user_id))
