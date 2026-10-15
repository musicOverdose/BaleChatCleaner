"""
Unit tests for the AntiGlitchEngine and DeletionTask state controller.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from src.database.models import CleaningJob, TrackedMessage
from src.cleaner.engine import AntiGlitchEngine, DeletionTask


def test_deletion_task_states():
    job = CleaningJob(
        job_id="task-123",
        chat_id=12345,
        chat_title="My Chat",
        status="pending",
        filter_mode="all",
        filter_types=[],
        scope_type="50",
    )
    task = DeletionTask(job)

    # Initial state
    assert task.pause_event.is_set() is True
    assert task.abort_event.is_set() is False

    # Pause
    task.pause()
    assert task.pause_event.is_set() is False
    assert job.status == "paused"

    # Resume
    task.resume()
    assert task.pause_event.is_set() is True
    assert job.status == "running"

    # Abort
    task.abort()
    assert task.abort_event.is_set() is True
    assert task.pause_event.is_set() is True
    assert job.status == "aborted"


@pytest.mark.asyncio
async def test_engine_abort_flow(tmp_path):
    mock_bot = MagicMock()
    mock_db = MagicMock()
    mock_db.update_job_progress = AsyncMock()
    mock_db.mark_message_deleted = AsyncMock()

    engine = AntiGlitchEngine(bot=mock_bot, db=mock_db)

    job = CleaningJob(
        job_id="job-abort",
        chat_id=12345,
        chat_title="Channel",
        status="pending",
        filter_mode="all",
        filter_types=[],
        scope_type="10",
        speed_profile="fast",
    )

    messages = [
        TrackedMessage(chat_id=12345, message_id=i, date=1000, content_type="text")
        for i in range(1, 11)
    ]

    async def async_delete(chat_id, message_id):
        task = engine.get_task(job.job_id)
        if task and message_id >= 2:
            task.abort()
        return True

    mock_bot.delete_message = AsyncMock(side_effect=async_delete)

    final_job = await engine.execute_job(job, messages)
    assert final_job.status == "aborted"
    assert final_job.deleted_count <= 3


@pytest.mark.asyncio
async def test_engine_target_user_filter():
    mock_bot = MagicMock()
    mock_bot.delete_message = AsyncMock(return_value=True)
    mock_db = MagicMock()
    mock_db.update_job_progress = AsyncMock()
    mock_db.mark_message_deleted = AsyncMock()

    engine = AntiGlitchEngine(bot=mock_bot, db=mock_db)

    job = CleaningJob(
        job_id="job-user",
        chat_id=12345,
        chat_title="Channel",
        target_user_id=777,
        status="pending",
        filter_mode="all",
        filter_types=[],
        scope_type="10",
        speed_profile="fast",
    )

    # 5 messages: 2 from user 777, 2 from user 888, 1 with None
    messages = [
        TrackedMessage(chat_id=12345, message_id=1, date=1000, content_type="text", sender_id=777),
        TrackedMessage(chat_id=12345, message_id=2, date=1001, content_type="text", sender_id=888),
        TrackedMessage(chat_id=12345, message_id=3, date=1002, content_type="text", sender_id=777),
        TrackedMessage(chat_id=12345, message_id=4, date=1003, content_type="text", sender_id=888),
        TrackedMessage(chat_id=12345, message_id=5, date=1004, content_type="text", sender_id=None),
    ]

    final_job = await engine.execute_job(job, messages)
    assert final_job.status == "completed"
    assert final_job.deleted_count == 2
    assert final_job.skipped_count == 3
    assert mock_bot.delete_message.call_count == 2
