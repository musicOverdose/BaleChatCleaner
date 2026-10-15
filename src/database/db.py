"""
Async SQLite Database Manager for BaleChatCleaner.
Handles chats, tracked messages, and persistent job states.
"""

import os
import aiosqlite
import json
import logging
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from contextlib import asynccontextmanager
from src.database.models import ChatRecord, TrackedMessage, CleaningJob

logger = logging.getLogger(__name__)

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS chats (
    chat_id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    chat_type TEXT NOT NULL,
    username TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tracked_messages (
    chat_id INTEGER NOT NULL,
    message_id TEXT NOT NULL,
    date INTEGER NOT NULL,
    content_type TEXT NOT NULL,
    sender_id INTEGER,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (chat_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_lookup 
ON tracked_messages (chat_id, is_deleted, content_type);

CREATE INDEX IF NOT EXISTS idx_messages_date 
ON tracked_messages (chat_id, date);

CREATE TABLE IF NOT EXISTS cleaning_jobs (
    job_id TEXT PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    chat_title TEXT NOT NULL,
    chat_username TEXT,
    target_user_id INTEGER,
    status TEXT NOT NULL,
    filter_mode TEXT NOT NULL,
    filter_types TEXT NOT NULL,
    scope_type TEXT NOT NULL,
    start_id INTEGER,
    end_id INTEGER,
    target_count INTEGER DEFAULT 0,
    deleted_count INTEGER DEFAULT 0,
    skipped_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    speed_profile TEXT NOT NULL DEFAULT 'ultra_safe',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status 
ON cleaning_jobs (status);
"""


class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path

    @asynccontextmanager
    async def _connect(self):
        """Yields an aiosqlite connection configured with a 30s lock timeout and WAL busy handling."""
        async with aiosqlite.connect(self.db_path, timeout=30.0) as db:
            await db.execute("PRAGMA busy_timeout=30000;")
            yield db

    async def init_db(self):
        """Initializes tables, indices, and ensures migrations for existing schemas."""
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        async with self._connect() as db:
            await db.execute("PRAGMA journal_mode=WAL;")
            await db.execute("PRAGMA synchronous=NORMAL;")
            await db.executescript(CREATE_TABLES_SQL)
            # Safe column migration for existing databases
            try:
                await db.execute("ALTER TABLE chats ADD COLUMN username TEXT")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE cleaning_jobs ADD COLUMN chat_username TEXT")
            except Exception:
                pass
            try:
                await db.execute("ALTER TABLE cleaning_jobs ADD COLUMN target_user_id INTEGER")
            except Exception:
                pass
            await db.commit()
        logger.info(f"Database initialized at {self.db_path} with WAL mode")

    # ==================== CHAT OPERATIONS ====================

    async def upsert_chat(
        self, chat_id: int, title: str, chat_type: str, username: Optional[str] = None
    ) -> None:
        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO chats (chat_id, title, chat_type, username, is_active)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(chat_id) DO UPDATE SET
                    title=excluded.title,
                    chat_type=excluded.chat_type,
                    username=COALESCE(excluded.username, chats.username),
                    is_active=1
                """,
                (chat_id, title, chat_type, username),
            )
            await db.commit()

    async def get_chats(self, active_only: bool = True) -> List[ChatRecord]:
        query = "SELECT chat_id, title, chat_type, username, is_active, added_at FROM chats"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY added_at DESC"

        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                return [
                    ChatRecord(
                        chat_id=row["chat_id"],
                        title=row["title"],
                        chat_type=row["chat_type"],
                        username=row["username"] if "username" in row.keys() else None,
                        is_active=bool(row["is_active"]),
                    )
                    for row in rows
                ]

    async def get_chat(self, chat_id: int) -> Optional[ChatRecord]:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT chat_id, title, chat_type, username, is_active FROM chats WHERE chat_id = ?",
                (chat_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return ChatRecord(
                        chat_id=row["chat_id"],
                        title=row["title"],
                        chat_type=row["chat_type"],
                        username=row["username"] if "username" in row.keys() else None,
                        is_active=bool(row["is_active"]),
                    )
                return None

    # ==================== MESSAGE TRACKING ====================

    async def save_message(
        self,
        chat_id: int,
        message_id: Union[int, str],
        date: int,
        content_type: str,
        sender_id: Optional[int] = None,
    ) -> None:
        async with self._connect() as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO tracked_messages 
                (chat_id, message_id, date, content_type, sender_id, is_deleted)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (chat_id, str(message_id), date, content_type, sender_id),
            )
            await db.commit()

    async def get_tracked_messages_to_clean(
        self,
        chat_id: int,
        filter_mode: str,  # 'all', 'only', 'except'
        filter_types: List[str],
        limit: Optional[int] = None,
        start_id: Optional[int] = None,
        end_id: Optional[int] = None,
        target_user_id: Optional[int] = None,
    ) -> List[TrackedMessage]:
        query = "SELECT chat_id, message_id, date, content_type, sender_id FROM tracked_messages WHERE chat_id = ? AND is_deleted = 0"
        params: List[Any] = [chat_id]

        if target_user_id is not None:
            query += " AND sender_id = ?"
            params.append(target_user_id)

        if filter_mode == "only" and filter_types:
            placeholders = ",".join("?" for _ in filter_types)
            query += f" AND content_type IN ({placeholders})"
            params.extend(filter_types)
        elif filter_mode == "except" and filter_types:
            placeholders = ",".join("?" for _ in filter_types)
            query += f" AND content_type NOT IN ({placeholders})"
            params.extend(filter_types)

        if start_id is not None:
            query += " AND CAST(message_id AS INTEGER) >= ?"
            params.append(start_id)

        if end_id is not None:
            query += " AND CAST(message_id AS INTEGER) <= ?"
            params.append(end_id)

        query += " ORDER BY rowid DESC"

        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                return [
                    TrackedMessage(
                        chat_id=row["chat_id"],
                        message_id=row["message_id"],
                        date=row["date"],
                        content_type=row["content_type"],
                        sender_id=row["sender_id"],
                        is_deleted=False,
                    )
                    for row in rows
                ]

    async def mark_message_deleted(self, chat_id: int, message_id: Union[int, str]) -> None:
        async with self._connect() as db:
            await db.execute(
                """
                UPDATE tracked_messages 
                SET is_deleted = 1 
                WHERE chat_id = ? AND message_id = ?
                """,
                (chat_id, str(message_id)),
            )
            await db.commit()

    async def get_tracked_count(self, chat_id: int) -> Dict[str, int]:
        """Returns message counts by content_type for a given chat."""
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT content_type, COUNT(*) as cnt 
                FROM tracked_messages 
                WHERE chat_id = ? AND is_deleted = 0 
                GROUP BY content_type
                """,
                (chat_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return {row["content_type"]: row["cnt"] for row in rows}

    async def get_latest_message_id(self, chat_id: int) -> Optional[int]:
        """Finds the maximum positive integer message_id recorded for a chat."""
        async with self._connect() as db:
            async with db.execute(
                """
                SELECT message_id FROM tracked_messages 
                WHERE chat_id = ? AND CAST(message_id AS INTEGER) > 0 
                ORDER BY CAST(message_id AS INTEGER) DESC LIMIT 1
                """,
                (chat_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    try:
                        return int(row[0])
                    except (ValueError, TypeError):
                        return None
                return None

    # ==================== JOB OPERATIONS ====================

    async def create_job(self, job: CleaningJob) -> None:
        async with self._connect() as db:
            await db.execute(
                """
                INSERT INTO cleaning_jobs (
                    job_id, chat_id, chat_title, chat_username, target_user_id, status, filter_mode, filter_types,
                    scope_type, start_id, end_id, target_count, deleted_count,
                    skipped_count, failed_count, speed_profile
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.job_id,
                    job.chat_id,
                    job.chat_title,
                    job.chat_username,
                    job.target_user_id,
                    job.status,
                    job.filter_mode,
                    json.dumps(job.filter_types),
                    job.scope_type,
                    job.start_id,
                    job.end_id,
                    job.target_count,
                    job.deleted_count,
                    job.skipped_count,
                    job.failed_count,
                    job.speed_profile,
                ),
            )
            await db.commit()

    async def update_job_progress(
        self,
        job_id: str,
        status: Optional[str] = None,
        deleted_count: Optional[int] = None,
        skipped_count: Optional[int] = None,
        failed_count: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> None:
        updates = ["updated_at = CURRENT_TIMESTAMP"]
        params: List[Any] = []

        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if deleted_count is not None:
            updates.append("deleted_count = ?")
            params.append(deleted_count)
        if skipped_count is not None:
            updates.append("skipped_count = ?")
            params.append(skipped_count)
        if failed_count is not None:
            updates.append("failed_count = ?")
            params.append(failed_count)
        if error_message is not None:
            updates.append("error_message = ?")
            params.append(error_message)

        params.append(job_id)
        query = f"UPDATE cleaning_jobs SET {', '.join(updates)} WHERE job_id = ?"

        async with self._connect() as db:
            await db.execute(query, tuple(params))
            await db.commit()

    async def get_job(self, job_id: str) -> Optional[CleaningJob]:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM cleaning_jobs WHERE job_id = ?", (job_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return CleaningJob(
                    job_id=row["job_id"],
                    chat_id=row["chat_id"],
                    chat_title=row["chat_title"],
                    chat_username=row["chat_username"] if "chat_username" in row.keys() else None,
                    target_user_id=row["target_user_id"] if "target_user_id" in row.keys() else None,
                    status=row["status"],
                    filter_mode=row["filter_mode"],
                    filter_types=json.loads(row["filter_types"]),
                    scope_type=row["scope_type"],
                    start_id=row["start_id"],
                    end_id=row["end_id"],
                    target_count=row["target_count"],
                    deleted_count=row["deleted_count"],
                    skipped_count=row["skipped_count"],
                    failed_count=row["failed_count"],
                    speed_profile=row["speed_profile"],
                    error_message=row["error_message"],
                )

    async def get_active_jobs(self) -> List[CleaningJob]:
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM cleaning_jobs WHERE status IN ('running', 'paused') ORDER BY created_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    CleaningJob(
                        job_id=row["job_id"],
                        chat_id=row["chat_id"],
                        chat_title=row["chat_title"],
                        chat_username=row["chat_username"] if "chat_username" in row.keys() else None,
                        target_user_id=row["target_user_id"] if "target_user_id" in row.keys() else None,
                        status=row["status"],
                        filter_mode=row["filter_mode"],
                        filter_types=json.loads(row["filter_types"]),
                        scope_type=row["scope_type"],
                        start_id=row["start_id"],
                        end_id=row["end_id"],
                        target_count=row["target_count"],
                        deleted_count=row["deleted_count"],
                        skipped_count=row["skipped_count"],
                        failed_count=row["failed_count"],
                        speed_profile=row["speed_profile"],
                        error_message=row["error_message"],
                    )
                    for row in rows
                ]

    async def get_chat_senders(self, chat_id: int) -> List[Dict[str, Any]]:
        """Returns distinct senders and their active message count in a chat."""
        query = """
            SELECT sender_id, COUNT(*) as cnt 
            FROM tracked_messages 
            WHERE chat_id = ? AND sender_id IS NOT NULL AND is_deleted = 0 
            GROUP BY sender_id 
            ORDER BY cnt DESC
        """
        async with self._connect() as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, (chat_id,)) as cursor:
                rows = await cursor.fetchall()
                return [{"sender_id": row["sender_id"], "count": row["cnt"]} for row in rows]
