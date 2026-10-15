"""
Dynamic Inline Keyboards for the BaleChatCleaner Admin Panel.
"""

from typing import List, Set
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from src.database.models import ChatRecord
from src.cleaner.filters import SUPPORTED_CONTENT_TYPES


def main_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📢 Manage Chats & Channels", callback_data="menu:chats")],
        [InlineKeyboardButton(text="🔄 Active & Recent Jobs", callback_data="menu:jobs")],
        [
            InlineKeyboardButton(text="🛡️ Anti-Glitch Guide", callback_data="menu:guide"),
            InlineKeyboardButton(text="⚙️ Settings", callback_data="menu:settings"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def chats_list_keyboard(chats: List[ChatRecord]) -> InlineKeyboardMarkup:
    buttons = []
    for c in chats:
        icon = "📢" if c.chat_type == "channel" else "👥"
        title = (c.title[:25] + "..") if len(c.title) > 27 else c.title
        buttons.append([InlineKeyboardButton(text=f"{icon} {title}", callback_data=f"chat:{c.chat_id}")])

    buttons.append([InlineKeyboardButton(text="➕ How to Add a Channel/Group", callback_data="menu:add_info")])
    buttons.append([InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def chat_action_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🧹 Start Cleaning Job", callback_data=f"clean_start:{chat_id}")],
        [InlineKeyboardButton(text="📊 Tracked Messages Statistics", callback_data=f"chat_stats:{chat_id}")],
        [InlineKeyboardButton(text="🔙 Back to Chats", callback_data="menu:chats")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def scope_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="Last 50", callback_data=f"scope:{chat_id}:50"),
            InlineKeyboardButton(text="Last 100", callback_data=f"scope:{chat_id}:100"),
        ],
        [
            InlineKeyboardButton(text="Last 500", callback_data=f"scope:{chat_id}:500"),
            InlineKeyboardButton(text="Last 1,000", callback_data=f"scope:{chat_id}:1000"),
        ],
        [InlineKeyboardButton(text="📦 All Tracked Messages", callback_data=f"scope:{chat_id}:all")],
        [InlineKeyboardButton(text="🔢 Custom ID Range", callback_data=f"scope:{chat_id}:custom")],
        [InlineKeyboardButton(text="🔙 Cancel", callback_data=f"chat:{chat_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def filter_mode_keyboard(chat_id: int, scope: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🎵 Keep ONLY Audio & Files (Delete Rest)", callback_data=f"fkeepfiles:{chat_id}:{scope}")],
        [InlineKeyboardButton(text="🗑 Delete EVERYTHING (All Types)", callback_data=f"fmode:{chat_id}:{scope}:all")],
        [InlineKeyboardButton(text="🎯 Delete ONLY Selected Types...", callback_data=f"fmode:{chat_id}:{scope}:only")],
        [InlineKeyboardButton(text="🛡 Delete ALL EXCEPT (Keep Selected)...", callback_data=f"fmode:{chat_id}:{scope}:except")],
        [InlineKeyboardButton(text="👤 Delete by Specific User...", callback_data=f"fuser_menu:{chat_id}:{scope}")],
        [InlineKeyboardButton(text="🔙 Back", callback_data=f"clean_start:{chat_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def chat_senders_keyboard(chat_id: int, scope: str, senders: list) -> InlineKeyboardMarkup:
    buttons = []
    for s in senders[:8]:  # Show top 8 senders
        sid = s["sender_id"]
        cnt = s["count"]
        buttons.append([InlineKeyboardButton(text=f"👤 User ID: {sid} ({cnt} msgs)", callback_data=f"fusersel:{chat_id}:{scope}:{sid}")])

    buttons.append([InlineKeyboardButton(text="✏️ Enter User ID Manually", callback_data=f"fusermanual:{chat_id}:{scope}")])
    buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data=f"scope_back:{chat_id}:{scope}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def user_action_keyboard(chat_id: int, scope: str, target_user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🗑 Delete ALL messages by this user", callback_data=f"fuaction:{chat_id}:{scope}:{target_user_id}:all")],
        [InlineKeyboardButton(text="🎵 Keep Audio & Files (Delete rest by user)", callback_data=f"fuaction:{chat_id}:{scope}:{target_user_id}:keepfiles")],
        [InlineKeyboardButton(text="🎯 Delete specific types by user...", callback_data=f"fuaction:{chat_id}:{scope}:{target_user_id}:custom")],
        [InlineKeyboardButton(text="🔙 Back to Senders", callback_data=f"fuser_menu:{chat_id}:{scope}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def filter_types_keyboard(
    chat_id: int, scope: str, mode: str, selected_types: List[str]
) -> InlineKeyboardMarkup:
    buttons = []
    selected_set: Set[str] = set(selected_types)

    row = []
    for key, label in SUPPORTED_CONTENT_TYPES.items():
        box = "✅" if key in selected_set else "⬜"
        btn_text = f"{box} {label}"
        row.append(InlineKeyboardButton(text=btn_text, callback_data=f"ftoggle:{chat_id}:{scope}:{mode}:{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Preset shortcut buttons
    buttons.append([
        InlineKeyboardButton(text="Select: Media (Photo/Video)", callback_data=f"fpreset:{chat_id}:{scope}:{mode}:media"),
        InlineKeyboardButton(text="Select: Audio & Docs", callback_data=f"fpreset:{chat_id}:{scope}:{mode}:files"),
    ])

    buttons.append([
        InlineKeyboardButton(text="➡️ Continue to Speed Selection", callback_data=f"fconfirm:{chat_id}:{scope}:{mode}")
    ])
    buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data=f"fmode_back:{chat_id}:{scope}")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def speed_keyboard(chat_id: int, scope: str, mode: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🛡️ Ultra-Safe (Recommended / 180ms + 2s sync)", callback_data=f"speed:{chat_id}:{scope}:{mode}:ultra_safe")],
        [InlineKeyboardButton(text="⚖️ Balanced (100ms + 1.2s sync)", callback_data=f"speed:{chat_id}:{scope}:{mode}:balanced")],
        [InlineKeyboardButton(text="⚡ Fast (50ms + adaptive)", callback_data=f"speed:{chat_id}:{scope}:{mode}:fast")],
        [InlineKeyboardButton(text="🔙 Back", callback_data=f"speed_back:{chat_id}:{scope}:{mode}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def job_confirm_keyboard(chat_id: int, scope: str, mode: str, speed: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="🚀 CONFIRM & START CLEANING", callback_data=f"launch:{chat_id}:{scope}:{mode}:{speed}")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data=f"chat:{chat_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def job_control_keyboard(job_id: str, status: str) -> InlineKeyboardMarkup:
    buttons = []
    if status == "running":
        buttons.append([
            InlineKeyboardButton(text="⏸ Pause", callback_data=f"job_pause:{job_id}"),
            InlineKeyboardButton(text="⏹ Abort", callback_data=f"job_abort:{job_id}"),
        ])
    elif status == "paused":
        buttons.append([
            InlineKeyboardButton(text="▶️ Resume", callback_data=f"job_resume:{job_id}"),
            InlineKeyboardButton(text="⏹ Abort", callback_data=f"job_abort:{job_id}"),
        ])

    buttons.append([InlineKeyboardButton(text="🔄 Refresh Status", callback_data=f"job_refresh:{job_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
