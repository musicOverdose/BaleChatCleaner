"""
Data models and type definitions for BaleChatCleaner.
"""

from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime


@dataclass
class ChatRecord:
    chat_id: int
    title: str
    chat_type: str  # 'channel', 'supergroup', 'group'
    is_active: bool = True
    added_at: Optional[datetime] = None


@dataclass
class TrackedMessage:
    chat_id: int
    message_id: int
    date: int  # Unix timestamp
    content_type: str  # text, photo, video, audio, document, voice, sticker, animation, etc.
    sender_id: Optional[int] = None
    is_deleted: bool = False


@dataclass
class CleaningJob:
    job_id: str
    chat_id: int
    chat_title: str
    status: str  # pending, running, paused, completed, aborted, failed
    filter_mode: str  # all, only, except
    filter_types: List[str]  # e.g. ['audio', 'document']
    scope_type: str  # last_n, id_range, all_tracked
    start_id: Optional[int] = None
    end_id: Optional[int] = None
    target_count: int = 0
    deleted_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    speed_profile: str = "ultra_safe"  # ultra_safe, balanced, fast
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    error_message: Optional[str] = None
