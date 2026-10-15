"""
Unit tests for the DatabaseManager and async SQLite queries.
"""

import pytest
import os
from src.database.db import DatabaseManager
from src.database.models import CleaningJob


@pytest.mark.asyncio
async def test_database_lifecycle(tmp_path):
    db_file = str(tmp_path / "test_cleaner.db")
    db = DatabaseManager(db_file)
    await db.init_db()

    # 1. Test Chat Upsert & Retrieval
    await db.upsert_chat(chat_id=-1001234567, title="Test Channel", chat_type="channel")
    chats = await db.get_chats(active_only=True)
    assert len(chats) == 1
    assert chats[0].title == "Test Channel"
    assert chats[0].chat_type == "channel"

    # 2. Test Message Tracking
    # Save 5 messages: 2 text, 2 photos, 1 audio
    await db.save_message(chat_id=-1001234567, message_id=1, date=1000, content_type="text")
    await db.save_message(chat_id=-1001234567, message_id=2, date=1001, content_type="text")
    await db.save_message(chat_id=-1001234567, message_id=3, date=1002, content_type="photo")
    await db.save_message(chat_id=-1001234567, message_id=4, date=1003, content_type="photo")
    await db.save_message(chat_id=-1001234567, message_id=5, date=1004, content_type="audio")

    stats = await db.get_tracked_count(-1001234567)
    assert stats["text"] == 2
    assert stats["photo"] == 2
    assert stats["audio"] == 1

    # 3. Test Filter Query: 'all'
    all_msgs = await db.get_tracked_messages_to_clean(
        chat_id=-1001234567,
        filter_mode="all",
        filter_types=[],
    )
    assert len(all_msgs) == 5

    # 4. Test Filter Query: 'only' (photos only)
    photos = await db.get_tracked_messages_to_clean(
        chat_id=-1001234567,
        filter_mode="only",
        filter_types=["photo"],
    )
    assert len(photos) == 2
    assert all(p.content_type == "photo" for p in photos)

    # 5. Test Filter Query: 'except' (All except audio) -> should return 4 (text & photos)
    except_audio = await db.get_tracked_messages_to_clean(
        chat_id=-1001234567,
        filter_mode="except",
        filter_types=["audio"],
    )
    assert len(except_audio) == 4
    assert all(m.content_type != "audio" for m in except_audio)

    # 6. Mark Deleted
    await db.mark_message_deleted(-1001234567, message_id=1)
    remaining = await db.get_tracked_messages_to_clean(
        chat_id=-1001234567,
        filter_mode="all",
        filter_types=[],
    )
    assert len(remaining) == 4

    # 7. Job Lifecycle
    job = CleaningJob(
        job_id="test-job-1",
        chat_id=-1001234567,
        chat_title="Test Channel",
        status="pending",
        filter_mode="only",
        filter_types=["photo"],
        scope_type="50",
        target_count=2,
    )
    await db.create_job(job)

    fetched_job = await db.get_job("test-job-1")
    assert fetched_job is not None
    assert fetched_job.status == "pending"
    assert fetched_job.filter_types == ["photo"]

    await db.update_job_progress(
        job_id="test-job-1",
        status="completed",
        deleted_count=2,
        skipped_count=0,
    )
    updated_job = await db.get_job("test-job-1")
    assert updated_job.status == "completed"
    assert updated_job.deleted_count == 2
