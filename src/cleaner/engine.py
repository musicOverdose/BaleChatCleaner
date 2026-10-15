"""
Anti-Glitch Deletion Engine for BaleChatCleaner.
Implements token-bucket pacing, socket-flush heartbeat pauses,
automatic 429 backoff, and async pause/resume/abort state controls.
"""

import asyncio
import logging
import time
from typing import List, Optional, Callable, Awaitable, Dict
from aiogram import Bot
from aiogram.exceptions import (
    TelegramRetryAfter,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNotFound,
    TelegramAPIError,
)

from src.database.db import DatabaseManager
from src.database.models import CleaningJob, TrackedMessage
from src.cleaner.filters import matches_filter
from src.cleaner.prober import MessageProber

logger = logging.getLogger(__name__)

SPEED_PROFILES = {
    "ultra_safe": {"delay": 0.18, "sync_interval": 20, "sync_pause": 2.0},
    "balanced": {"delay": 0.10, "sync_interval": 30, "sync_pause": 1.2},
    "fast": {"delay": 0.05, "sync_interval": 50, "sync_pause": 0.8},
}


class DeletionTask:
    def __init__(self, job: CleaningJob):
        self.job = job
        self.pause_event = asyncio.Event()
        self.pause_event.set()  # Initially unpaused
        self.abort_event = asyncio.Event()
        self.current_speed = SPEED_PROFILES.get(job.speed_profile, SPEED_PROFILES["ultra_safe"])

    def pause(self):
        self.pause_event.clear()
        self.job.status = "paused"

    def resume(self):
        self.pause_event.set()
        self.job.status = "running"

    def abort(self):
        self.abort_event.set()
        self.pause_event.set()  # Unblock if currently paused so it exits immediately
        self.job.status = "aborted"


class AntiGlitchEngine:
    def __init__(self, bot: Bot, db: DatabaseManager, prober: Optional[MessageProber] = None):
        self.bot = bot
        self.db = db
        self.prober = prober
        self.active_tasks: Dict[str, DeletionTask] = {}

    def get_task(self, job_id: str) -> Optional[DeletionTask]:
        return self.active_tasks.get(job_id)

    async def detect_latest_message_id(self, chat_id: int) -> Optional[int]:
        """
        Attempts to detect the current head message ID in the target chat.
        Sends a momentary probe message and immediately deletes it.
        Returns the message_id or None if permission denied.
        """
        try:
            msg = await self.bot.send_message(chat_id=chat_id, text="🔍", disable_notification=True)
            head_id = msg.message_id
            try:
                await self.bot.delete_message(chat_id=chat_id, message_id=head_id)
            except Exception:
                pass
            return head_id
        except Exception as e:
            logger.debug(f"Could not auto-detect latest message ID via probe in chat {chat_id}: {e}")
            return None

    async def execute_job(
        self,
        job: CleaningJob,
        messages_to_clean: List[TrackedMessage],
        on_progress: Optional[Callable[[CleaningJob, str], Awaitable[None]]] = None,
    ) -> CleaningJob:
        """
        Executes a cleaning job against a list of messages with rate-pacing and anti-glitch protection.
        """
        task = DeletionTask(job)
        self.active_tasks[job.job_id] = task

        job.status = "running"
        job.target_count = len(messages_to_clean)
        await self.db.update_job_progress(job.job_id, status="running")

        speed = task.current_speed
        delay = speed["delay"]
        sync_interval = speed["sync_interval"]
        sync_pause = speed["sync_pause"]

        processed_since_sync = 0
        last_progress_update = time.time()
        start_time = time.time()

        logger.info(
            f"Starting Anti-Glitch job {job.job_id} on chat {job.chat_id} "
            f"({len(messages_to_clean)} messages, profile={job.speed_profile})"
        )

        try:
            for item in messages_to_clean:
                # 1. Check for abort
                if task.abort_event.is_set():
                    job.status = "aborted"
                    break

                # 2. Check for pause (blocks until resume() is called)
                if not task.pause_event.is_set():
                    logger.info(f"Job {job.job_id} paused. Waiting for resume...")
                    await self.db.update_job_progress(job.job_id, status="paused")
                    if on_progress:
                        await on_progress(job, "⏸ Task is Paused.")
                    await task.pause_event.wait()
                    if task.abort_event.is_set():
                        job.status = "aborted"
                        break
                    logger.info(f"Job {job.job_id} resumed.")
                    await self.db.update_job_progress(job.job_id, status="running")

                # 2.5 Check target user match if specified
                if job.target_user_id is not None:
                    if item.sender_id != job.target_user_id:
                        job.skipped_count += 1
                        continue

                # 3. Check filter match (if item has content_type)
                should_delete = matches_filter(item.content_type, job.filter_mode, job.filter_types)

                # If content_type is unknown and prober is available, probe it
                if item.content_type == "unknown" and self.prober and job.filter_mode != "all":
                    probed_type = await self.prober.probe_message_type(item.chat_id, item.message_id)
                    if probed_type:
                        item.content_type = probed_type
                        should_delete = matches_filter(probed_type, job.filter_mode, job.filter_types)
                    else:
                        should_delete = False

                if not should_delete:
                    job.skipped_count += 1
                    continue

                # 4. Attempt Deletion with Automatic Retry & Glitch Avoidance
                deleted_successfully = False
                attempts = 0

                # Determine target chat identifier:
                # In Bale, groups require numeric chat_id. Channels with @username prefer @username.
                primary_chat = job.chat_id
                secondary_chat = None

                if getattr(job, "chat_username", None):
                    uname = job.chat_username.strip()
                    if uname:
                        formatted_uname = uname if uname.startswith("@") else f"@{uname}"
                        if str(job.chat_id).startswith("-"):
                            primary_chat = formatted_uname
                            secondary_chat = job.chat_id
                        else:
                            primary_chat = job.chat_id
                            secondary_chat = formatted_uname

                while not deleted_successfully and attempts < 3:
                    attempts += 1
                    try:
                        try:
                            await self.bot.delete_message(chat_id=primary_chat, message_id=item.message_id)
                        except (TelegramBadRequest, TelegramNotFound, TelegramAPIError) as sub_e:
                            if secondary_chat and ("not found" in str(sub_e).lower() or "bad request" in str(sub_e).lower()):
                                # Fallback to secondary identifier
                                await self.bot.delete_message(chat_id=secondary_chat, message_id=item.message_id)
                            else:
                                raise sub_e

                        job.deleted_count += 1
                        await self.db.mark_message_deleted(job.chat_id, item.message_id)
                        deleted_successfully = True

                    except TelegramRetryAfter as e:
                        # HTTP 429: Respect rate limiter + extra jitter
                        sleep_time = e.retry_after + 0.8
                        logger.warning(f"Rate limited by server! Sleeping for {sleep_time:.2f}s...")
                        if on_progress:
                            await on_progress(job, f"⚠️ Rate limited. Cooling down for {int(sleep_time)}s...")
                        await asyncio.sleep(sleep_time)

                    except (TelegramBadRequest, TelegramNotFound, TelegramAPIError) as e:
                        err_text = str(e).lower()
                        if "message to delete not found" in err_text or "not found" in err_text:
                            # Message already deleted by admin/user or non-existent
                            job.skipped_count += 1
                            deleted_successfully = True
                        elif "message can't be deleted" in err_text:
                            # Permission or age limit (>48h in group)
                            logger.debug(f"Message {item.message_id} cannot be deleted: {e}")
                            job.skipped_count += 1
                            deleted_successfully = True
                        elif "permission_denied" in err_text or "forbidden" in err_text:
                            logger.error(f"Permission denied deleting {item.message_id}: {e}")
                            job.status = "failed"
                            job.error_message = "Bot lacks delete rights or was removed from chat."
                            break
                        else:
                            logger.warning(f"Bad request deleting {item.message_id}: {e}")
                            job.failed_count += 1
                            deleted_successfully = True  # Move to next message

                    except TelegramForbiddenError as e:
                        logger.error(f"Permission denied deleting in chat {job.chat_id}: {e}")
                        job.status = "failed"
                        job.error_message = "Bot lacks delete rights or was removed from chat."
                        break

                    except Exception as e:
                        err_text = str(e).lower()
                        if "not found" in err_text:
                            job.skipped_count += 1
                            deleted_successfully = True
                        else:
                            logger.error(f"Unexpected error deleting {item.message_id}: {e}")
                            job.failed_count += 1
                            deleted_successfully = True

                if job.status == "failed":
                    break

                # 5. Anti-Glitch Inter-Message Pacing
                await asyncio.sleep(delay)
                processed_since_sync += 1

                # 6. Anti-Glitch Socket Flush Heartbeat
                if processed_since_sync >= sync_interval:
                    logger.debug(f"Flushing socket sync buffer (pause {sync_pause}s)...")
                    await asyncio.sleep(sync_pause)
                    processed_since_sync = 0

                # 7. Progress notification update (throttled to every 6s)
                now = time.time()
                if now - last_progress_update >= 6.0:
                    last_progress_update = now
                    elapsed = max(1.0, now - start_time)
                    speed_rate = (job.deleted_count + job.skipped_count) / elapsed
                    pct = int(((job.deleted_count + job.skipped_count + job.failed_count) / max(1, job.target_count)) * 100)
                    progress_text = (
                        f"⏳ **Cleaning in Progress...**\n"
                        f"📊 Progress: {pct}% ({job.deleted_count + job.skipped_count}/{job.target_count})\n"
                        f"🗑 Deleted: `{job.deleted_count}` | ⏭ Skipped: `{job.skipped_count}`\n"
                        f"⚡ Speed: `{speed_rate:.1f} msg/s`"
                    )
                    await self.db.update_job_progress(
                        job.job_id,
                        deleted_count=job.deleted_count,
                        skipped_count=job.skipped_count,
                        failed_count=job.failed_count,
                    )
                    if on_progress:
                        await on_progress(job, progress_text)

            # Final status resolution
            if job.status not in ("aborted", "failed"):
                job.status = "completed"

        except Exception as e:
            logger.exception(f"Fatal error in cleaning job {job.job_id}: {e}")
            job.status = "failed"
            job.error_message = str(e)

        finally:
            self.active_tasks.pop(job.job_id, None)
            await self.db.update_job_progress(
                job.job_id,
                status=job.status,
                deleted_count=job.deleted_count,
                skipped_count=job.skipped_count,
                failed_count=job.failed_count,
                error_message=job.error_message,
            )
            logger.info(
                f"Job {job.job_id} finished with status={job.status} "
                f"(Deleted: {job.deleted_count}, Skipped: {job.skipped_count}, Failed: {job.failed_count})"
            )

        return job
