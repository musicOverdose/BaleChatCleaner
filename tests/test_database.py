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
    # Save 5 messages: 2 text (user 111), 1 photo (user 111), 1 photo (user 222), 1 audio (user 222)
    await db.save_message(chat_id=-1001234567, message_id=1, date=1000, content_type="text", sender_id=111)
    await db.save_message(chat_id=-1001234567, message_id=2, date=1001, content_type="text", sender_id=111)
    await db.save_message(chat_id=-1001234567, message_id=3, date=1002, content_type="photo", sender_id=111)
    await db.save_message(chat_id=-1001234567, message_id=4, date=1003, content_type="photo", sender_id=222)
    await db.save_message(chat_id=-1001234567, message_id=5, date=1004, content_type="audio", sender_id=222)

    stats = await db.get_tracked_count(-1001234567)
    assert stats["text"] == 2
    assert stats["photo"] == 2
    assert stats["audio"] == 1

    # Test Chat Senders
    senders = await db.get_chat_senders(-1001234567)
    assert len(senders) == 2
    assert senders[0]["sender_id"] == 111 and senders[0]["count"] == 3
    assert senders[1]["sender_id"] == 222 and senders[1]["count"] == 2

    # 3. Test Filter Query: 'all'
    all_msgs = await db.get_tracked_messages_to_clean(
        chat_id=-1001234567,
        filter_mode="all",
        filter_types=[],
    )
    assert len(all_msgs) == 5

    # Test Filter Query with target_user_id
    user_msgs = await db.get_tracked_messages_to_clean(
        chat_id=-1001234567,
        filter_mode="all",
        filter_types=[],
        target_user_id=111,
    )
    assert len(user_msgs) == 3
    assert all(m.sender_id == 111 for m in user_msgs)

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
        target_user_id=111,
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
    assert fetched_job.target_user_id == 111
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
    assert updated_job.target_user_id == 111

    # 8. Test Latest Message ID
    latest_id = await db.get_latest_message_id(-1001234567)
    assert latest_id == 5

