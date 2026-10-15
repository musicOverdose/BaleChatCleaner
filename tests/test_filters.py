"""
Unit tests for the filter engine.
"""

from src.cleaner.filters import matches_filter


def test_matches_filter_all():
    assert matches_filter("text", "all", []) is True
    assert matches_filter("photo", "all", []) is True
    assert matches_filter("audio", "all", []) is True


def test_matches_filter_only():
    selected = ["audio", "document"]
    assert matches_filter("audio", "only", selected) is True
    assert matches_filter("document", "only", selected) is True
    assert matches_filter("text", "only", selected) is False
    assert matches_filter("photo", "only", selected) is False


def test_matches_filter_except():
    # User wants to delete EVERYTHING EXCEPT audio and documents
    selected = ["audio", "document"]
    assert matches_filter("audio", "except", selected) is False      # KEEP audio
    assert matches_filter("document", "except", selected) is False   # KEEP document
    assert matches_filter("text", "except", selected) is True        # DELETE text
    assert matches_filter("photo", "except", selected) is True       # DELETE photo
    assert matches_filter("video", "except", selected) is True       # DELETE video
    assert matches_filter("voice", "except", selected) is True       # DELETE voice
