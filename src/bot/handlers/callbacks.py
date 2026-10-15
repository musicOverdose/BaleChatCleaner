"""
Callback Query Handlers for the BaleChatCleaner Inline Panel.
"""

import asyncio
import logging
import uuid
from typing import List, Dict, Any
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from src.database.db import DatabaseManager
from src.database.models import CleaningJob, TrackedMessage
from src.cleaner.engine import AntiGlitchEngine, SPEED_PROFILES
from src.bot.handlers.admin import CustomRangeState
from src.bot.keyboards import (
    main_menu_keyboard,
    chats_list_keyboard,
    chat_action_keyboard,
    scope_keyboard,
    filter_mode_keyboard,
    filter_types_keyboard,
    speed_keyboard,
    job_confirm_keyboard,
    job_control_keyboard,
)

logger = logging.getLogger(__name__)
callbacks_router = Router(name="callbacks")

# In-memory dictionary for active wizard filter selections: {user_id: set_of_types}
USER_FILTER_SELECTIONS: Dict[int, List[str]] = {}


@callbacks_router.callback_query(F.data == "menu:main")
async def cb_main_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text(
        "🛡️ **BaleChatCleaner Dashboard**\n\n"
        "Select an option to manage your channels and cleaning operations:",
        reply_markup=main_menu_keyboard(),
    )
    await call.answer()


@callbacks_router.callback_query(F.data == "menu:chats")
async def cb_list_chats(call: CallbackQuery, db: DatabaseManager):
    chats = await db.get_chats(active_only=True)
    if not chats:
        await call.message.edit_text(
            "⚠️ **No Registered Chats Found**\n\n"
            "To use this bot:\n"
            "1. Add this bot to your channel or group as an **Administrator**.\n"
            "2. Ensure the **Delete Messages** permission is enabled.\n"
            "3. Send or post a test message so the bot registers the chat.",
            reply_markup=main_menu_keyboard(),
        )
        await call.answer()
        return

    await call.message.edit_text(
        "📢 **Select a Channel or Group to Manage:**",
        reply_markup=chats_list_keyboard(chats),
    )
    await call.answer()


@callbacks_router.callback_query(F.data == "menu:jobs")
async def cb_list_jobs(call: CallbackQuery, db: DatabaseManager):
    active_jobs = await db.get_active_jobs()
    if not active_jobs:
        await call.message.edit_text(
            "📋 **Job Status**\n\nNo active cleaning jobs currently running.",
            reply_markup=main_menu_keyboard(),
        )
        await call.answer()
        return

    text = "🔄 **Active Cleaning Jobs:**\n\n"
    for j in active_jobs:
        pct = int(((j.deleted_count + j.skipped_count) / max(1, j.target_count)) * 100)
        text += (
            f"• **{j.chat_title}** [{j.status.upper()}]\n"
            f"  Progress: {pct}% ({j.deleted_count}/{j.target_count} deleted)\n"
            f"  Speed: `{j.speed_profile}`\n\n"
        )

    await call.message.edit_text(text, reply_markup=main_menu_keyboard())
    await call.answer()


@callbacks_router.callback_query(F.data == "menu:guide")
async def cb_guide(call: CallbackQuery):
    guide_text = (
        "🛡️ **Anti-Glitch Guide & Best Practices**\n\n"
        "**Why do channels glitch during mass deletion?**\n"
        "When bots delete messages too quickly, messenger push gateways drop sync packets, "
        "causing deleted messages to remain visible on some subscribers' devices while gone for others.\n\n"
        "**How BaleChatCleaner solves this:**\n"
        "1. **Paced Token-Bucket**: Enforces a steady 100–180ms delay between delete requests.\n"
        "2. **Socket Flush Pauses**: Every 20–30 messages, the bot pauses for 1.5–2s to allow all subscriber client sockets to catch up.\n"
        "3. **Automatic 429 Backoff**: Dynamically cools down if the server requests throttling.\n\n"
        "💡 *Recommendation:* For channels with over 1,000 members, always use the **Ultra-Safe** profile."
    )
    await call.message.edit_text(guide_text, reply_markup=main_menu_keyboard())
    await call.answer()


@callbacks_router.callback_query(F.data == "menu:settings")
async def cb_settings(call: CallbackQuery):
    from src.config import settings
    text = (
        "⚙️ **System Configuration**\n\n"
        f"• **API Base:** `{settings.BALE_API_ENDPOINT if settings else 'Default'}`\n"
        f"• **Database:** `{settings.DB_PATH if settings else 'data/cleaner.db'}`\n"
        f"• **Channel Delay:** `{settings.DEFAULT_CHANNEL_DELAY if settings else 0.12}s`\n"
        f"• **Group Delay:** `{settings.DEFAULT_GROUP_DELAY if settings else 0.06}s`\n"
        f"• **Sync Flush:** Every `{settings.SYNC_PAUSE_INTERVAL if settings else 25}` msgs for `{settings.SYNC_PAUSE_DURATION if settings else 1.5}s`"
    )
    await call.message.edit_text(text, reply_markup=main_menu_keyboard())
    await call.answer()


@callbacks_router.callback_query(F.data == "menu:add_info")
async def cb_add_info(call: CallbackQuery):
    text = (
        "➕ **Adding the Bot to Channels & Groups**\n\n"
        "1. Open your Channel or Group settings in Bale.\n"
        "2. Go to **Administrators** -> **Add Administrator**.\n"
        "3. Search for your bot username and select it.\n"
        "4. Enable the **Delete Messages** permission.\n"
        "5. Post or send one message in the chat.\n"
        "6. Return to this panel and click **Manage Chats**."
    )
    await call.message.edit_text(text, reply_markup=main_menu_keyboard())
    await call.answer()


@callbacks_router.callback_query(F.data.startswith("chat:"))
async def cb_chat_detail(call: CallbackQuery, db: DatabaseManager):
    chat_id = int(call.data.split(":")[1])
    chat = await db.get_chat(chat_id)
    if not chat:
        await call.answer("Chat not found in database.", show_alert=True)
        return

    stats = await db.get_tracked_count(chat_id)
    total_tracked = sum(stats.values())
    stats_breakdown = ", ".join(f"{k}: {v}" for k, v in stats.items()) or "None"

    icon = "📢 Channel" if chat.chat_type == "channel" else "👥 Group"
    text = (
        f"{icon}: **{chat.title}**\n"
        f"ID: `{chat.chat_id}`\n\n"
        f"📦 **Tracked Messages:** `{total_tracked}`\n"
        f"Details: {stats_breakdown}\n\n"
        "Choose an action:"
    )
    await call.message.edit_text(text, reply_markup=chat_action_keyboard(chat_id))
    await call.answer()


@callbacks_router.callback_query(F.data.startswith("chat_stats:"))
async def cb_chat_stats(call: CallbackQuery, db: DatabaseManager):
    chat_id = int(call.data.split(":")[1])
    chat = await db.get_chat(chat_id)
    stats = await db.get_tracked_count(chat_id)

    lines = [f"📊 **Statistics for {chat.title if chat else chat_id}:**\n"]
    if not stats:
        lines.append("No tracked messages recorded yet.")
    else:
        for ctype, count in stats.items():
            lines.append(f"• **{ctype.capitalize()}**: `{count}` messages")

    await call.message.edit_text("\n".join(lines), reply_markup=chat_action_keyboard(chat_id))
    await call.answer()


@callbacks_router.callback_query(F.data.startswith("clean_start:"))
async def cb_clean_start(call: CallbackQuery):
    chat_id = int(call.data.split(":")[1])
    await call.message.edit_text(
        "🎯 **Step 1: Choose Cleaning Scope**\n\n"
        "Select how many messages you would like to target for cleaning:",
        reply_markup=scope_keyboard(chat_id),
    )
    await call.answer()


@callbacks_router.callback_query(F.data.startswith("scope:"))
async def cb_scope_selected(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    chat_id = int(parts[1])
    scope = parts[2]

    if scope == "custom":
        await state.set_state(CustomRangeState.waiting_for_range)
        await state.update_data(chat_id=chat_id)
        await call.message.edit_text(
            "🔢 **Custom ID Range**\n\n"
            "Send the starting and ending message IDs as two numbers separated by a space.\n"
            "Example: `150 600`"
        )
        await call.answer()
        return

    await call.message.edit_text(
        f"🎯 **Target Scope:** `{scope}` messages\n\n"
        "**Step 2: Choose Filter Mode**\n\n"
        "• **Delete EVERYTHING**: Wipes all message types in the scope.\n"
        "• **Delete ONLY Selected**: E.g. delete only voice notes and photos.\n"
        "• **Delete ALL EXCEPT (Inverted)**: Delete everything **except** audio and documents.",
        reply_markup=filter_mode_keyboard(chat_id, scope),
    )
    await call.answer()


@callbacks_router.callback_query(F.data.startswith("fmode:"))
async def cb_fmode_selected(call: CallbackQuery):
    parts = call.data.split(":")
    chat_id = int(parts[1])
    scope = parts[2]
    mode = parts[3]

    if mode == "all":
        # Skip type selection, go straight to speed
        USER_FILTER_SELECTIONS[call.from_user.id] = []
        await call.message.edit_text(
            "⚡ **Step 3: Choose Anti-Glitch Speed Profile**\n\n"
            "Pacing prevents client-side desync and rate limits:",
            reply_markup=speed_keyboard(chat_id, scope, mode),
        )
        await call.answer()
        return

    # Initialize empty selection for 'only' or 'except'
    USER_FILTER_SELECTIONS[call.from_user.id] = []
    mode_desc = "select types to **DELETE**" if mode == "only" else "select types to **KEEP (DO NOT DELETE)**"
    await call.message.edit_text(
        f"🧩 **Step 2.1: Configure Filters ({mode.upper()})**\n\n"
        f"Toggle the checkboxes below to {mode_desc}:",
        reply_markup=filter_types_keyboard(chat_id, scope, mode, []),
    )
    await call.answer()


@callbacks_router.callback_query(F.data.startswith("ftoggle:"))
async def cb_ftoggle(call: CallbackQuery):
    parts = call.data.split(":")
    chat_id = int(parts[1])
    scope = parts[2]
    mode = parts[3]
    toggled_type = parts[4]

    user_id = call.from_user.id
    current_selected = USER_FILTER_SELECTIONS.get(user_id, [])

    if toggled_type in current_selected:
        current_selected.remove(toggled_type)
    else:
        current_selected.append(toggled_type)

    USER_FILTER_SELECTIONS[user_id] = current_selected

    await call.message.edit_reply_markup(
        reply_markup=filter_types_keyboard(chat_id, scope, mode, current_selected)
    )
    await call.answer()


@callbacks_router.callback_query(F.data.startswith("fpreset:"))
async def cb_fpreset(call: CallbackQuery):
    parts = call.data.split(":")
    chat_id = int(parts[1])
    scope = parts[2]
    mode = parts[3]
    preset = parts[4]

    user_id = call.from_user.id
    if preset == "media":
        USER_FILTER_SELECTIONS[user_id] = ["photo", "video", "animation"]
    elif preset == "files":
        USER_FILTER_SELECTIONS[user_id] = ["audio", "document"]

    await call.message.edit_reply_markup(
        reply_markup=filter_types_keyboard(chat_id, scope, mode, USER_FILTER_SELECTIONS[user_id])
    )
    await call.answer(f"Preset applied: {preset}")


@callbacks_router.callback_query(F.data.startswith("fconfirm:"))
async def cb_fconfirm(call: CallbackQuery):
    parts = call.data.split(":")
    chat_id = int(parts[1])
    scope = parts[2]
    mode = parts[3]

    selected = USER_FILTER_SELECTIONS.get(call.from_user.id, [])
    if not selected and mode != "all":
        await call.answer("⚠️ Please select at least one message type or use 'All' mode.", show_alert=True)
        return

    await call.message.edit_text(
        "⚡ **Step 3: Select Anti-Glitch Speed Profile**\n\n"
        "Controls deletion delay and socket heartbeat pause intervals:",
        reply_markup=speed_keyboard(chat_id, scope, mode),
    )
    await call.answer()


@callbacks_router.callback_query(F.data.startswith("speed:"))
async def cb_speed_selected(call: CallbackQuery, db: DatabaseManager):
    parts = call.data.split(":")
    chat_id = int(parts[1])
    scope = parts[2]
    mode = parts[3]
    speed = parts[4]

    chat = await db.get_chat(chat_id)
    chat_title = chat.title if chat else f"Chat {chat_id}"
    selected_types = USER_FILTER_SELECTIONS.get(call.from_user.id, [])

    if mode == "all":
        filter_summary = "All message types (Full Wipe)"
    elif mode == "only":
        filter_summary = f"Only delete: {', '.join(selected_types)}"
    else:
        filter_summary = f"Delete all EXCEPT: {', '.join(selected_types)}"

    profile_info = SPEED_PROFILES.get(speed, SPEED_PROFILES["ultra_safe"])

    summary_text = (
        "⚠️ **Review & Confirmation**\n\n"
        f"• **Target:** `{chat_title}`\n"
        f"• **Scope:** `{scope}` messages\n"
        f"• **Filter:** {filter_summary}\n"
        f"• **Profile:** `{speed.upper()}` ({int(profile_info['delay']*1000)}ms delay + {profile_info['sync_pause']}s sync pause)\n\n"
        "⚠️ *This action permanently deletes messages. Are you sure you want to start?*"
    )
    await call.message.edit_text(summary_text, reply_markup=job_confirm_keyboard(chat_id, scope, mode, speed))
    await call.answer()


@callbacks_router.callback_query(F.data.startswith("launch:"))
async def cb_launch_job(call: CallbackQuery, db: DatabaseManager, engine: AntiGlitchEngine):
    parts = call.data.split(":")
    chat_id = int(parts[1])
    scope = parts[2]
    mode = parts[3]
    speed = parts[4]

    chat = await db.get_chat(chat_id)
    chat_title = chat.title if chat else f"Chat {chat_id}"
    selected_types = USER_FILTER_SELECTIONS.get(call.from_user.id, [])

    # Fetch messages to clean
    limit = int(scope) if scope.isdigit() else None
    start_id = None
    end_id = None
    if scope.startswith("range_"):
        r_parts = scope.split("_")
        start_id = int(r_parts[1])
        end_id = int(r_parts[2])

    # Fetch any already tracked messages in SQLite
    tracked = await db.get_tracked_messages_to_clean(
        chat_id=chat_id,
        filter_mode=mode,
        filter_types=selected_types,
        limit=limit,
        start_id=start_id,
        end_id=end_id,
    )

    tracked_map = {int(m.message_id): m for m in tracked if str(m.message_id).isdigit()}

    # Case A: Custom ID Range
    if start_id is not None and end_id is not None:
        messages = []
        for mid in range(max(1, start_id), end_id + 1):
            if mid in tracked_map:
                messages.append(tracked_map[mid])
            else:
                messages.append(
                    TrackedMessage(
                        chat_id=chat_id,
                        message_id=mid,
                        date=0,
                        content_type="all" if mode == "all" else "unknown",
                    )
                )
        messages.sort(key=lambda m: int(m.message_id) if str(m.message_id).isdigit() else 0, reverse=True)

    # Case B: Numeric Limit (e.g. Last 50 / 100)
    elif limit is not None:
        latest_id = await db.get_latest_message_id(chat_id)
        if latest_id:
            start_seq = max(1, latest_id - limit + 1)
            messages = []
            for mid in range(start_seq, latest_id + 1):
                if mid in tracked_map:
                    messages.append(tracked_map[mid])
                else:
                    messages.append(
                        TrackedMessage(
                            chat_id=chat_id,
                            message_id=mid,
                            date=0,
                            content_type="all" if mode == "all" else "unknown",
                        )
                    )
            messages.sort(key=lambda m: int(m.message_id) if str(m.message_id).isdigit() else 0, reverse=True)
            messages = messages[:limit]
        else:
            messages = tracked

    # Case C: All Tracked
    else:
        messages = tracked

    if not messages:
        await call.answer(
            "⚠️ No messages found to clean. Send /check in your chat first so the bot knows the current ID, or use Custom ID Range.",
            show_alert=True,
        )
        return

    job_id = str(uuid.uuid4())[:8]
    job = CleaningJob(
        job_id=job_id,
        chat_id=chat_id,
        chat_title=chat_title,
        chat_username=chat.username if chat else None,
        status="pending",
        filter_mode=mode,
        filter_types=selected_types,
        scope_type=scope,
        start_id=start_id,
        end_id=end_id,
        target_count=len(messages),
        speed_profile=speed,
    )

    await db.create_job(job)

    status_message = await call.message.edit_text(
        f"🚀 **Cleaning Job `{job_id}` Launched!**\n\n"
        f"Target: `{chat_title}`\n"
        f"Messages: `{len(messages)}`\n"
        "Initializing anti-glitch queue...",
        reply_markup=job_control_keyboard(job_id, "running"),
    )

    async def progress_callback(updated_job: CleaningJob, text: str):
        try:
            await status_message.edit_text(
                f"🛡️ **Job `{updated_job.job_id}` - {updated_job.chat_title}**\n\n{text}",
                reply_markup=job_control_keyboard(updated_job.job_id, updated_job.status),
            )
        except Exception as e:
            logger.debug(f"Progress edit throttled or skipped: {e}")

    # Launch background cleaning task
    asyncio.create_task(engine.execute_job(job, messages, on_progress=progress_callback))
    await call.answer("Job started!")


@callbacks_router.callback_query(F.data.startswith("job_pause:"))
async def cb_job_pause(call: CallbackQuery, engine: AntiGlitchEngine):
    job_id = call.data.split(":")[1]
    task = engine.get_task(job_id)
    if task:
        task.pause()
        await call.answer("⏸ Job paused.")
        await call.message.edit_reply_markup(reply_markup=job_control_keyboard(job_id, "paused"))
    else:
        await call.answer("Task not active or already finished.", show_alert=True)


@callbacks_router.callback_query(F.data.startswith("job_resume:"))
async def cb_job_resume(call: CallbackQuery, engine: AntiGlitchEngine):
    job_id = call.data.split(":")[1]
    task = engine.get_task(job_id)
    if task:
        task.resume()
        await call.answer("▶️ Job resumed.")
        await call.message.edit_reply_markup(reply_markup=job_control_keyboard(job_id, "running"))
    else:
        await call.answer("Task not active or already finished.", show_alert=True)


@callbacks_router.callback_query(F.data.startswith("job_abort:"))
async def cb_job_abort(call: CallbackQuery, engine: AntiGlitchEngine):
    job_id = call.data.split(":")[1]
    task = engine.get_task(job_id)
    if task:
        task.abort()
        await call.answer("⏹ Job aborted.")
        await call.message.edit_reply_markup(reply_markup=job_control_keyboard(job_id, "aborted"))
    else:
        await call.answer("Task already completed or stopped.", show_alert=True)


@callbacks_router.callback_query(F.data.startswith("job_refresh:"))
async def cb_job_refresh(call: CallbackQuery, db: DatabaseManager):
    job_id = call.data.split(":")[1]
    job = await db.get_job(job_id)
    if not job:
        await call.answer("Job record not found.", show_alert=True)
        return

    pct = int(((job.deleted_count + job.skipped_count) / max(1, job.target_count)) * 100)
    text = (
        f"🛡️ **Job `{job.job_id}` Status: {job.status.upper()}**\n\n"
        f"• Chat: **{job.chat_title}**\n"
        f"• Progress: `{pct}%` ({job.deleted_count + job.skipped_count}/{job.target_count})\n"
        f"• Deleted: `{job.deleted_count}`\n"
        f"• Skipped: `{job.skipped_count}`\n"
        f"• Failed: `{job.failed_count}`\n"
        f"• Speed: `{job.speed_profile}`"
    )
    if job.error_message:
        text += f"\n• Error: `{job.error_message}`"

    await call.message.edit_text(text, reply_markup=job_control_keyboard(job_id, job.status))
    await call.answer("Refreshed!")
