"""
Filter engine for message classification and matching in BaleChatCleaner.
Supports positive matching and inverted/negation rules ("all except X").
"""

from typing import List, Set

SUPPORTED_CONTENT_TYPES = {
    "text": "📝 Text",
    "photo": "🖼 Photo",
    "video": "🎬 Video",
    "audio": "🎵 Audio / Music",
    "document": "📄 Document / File",
    "voice": "🎤 Voice Note",
    "sticker": "🎭 Sticker",
    "animation": "🎞 GIF / Animation",
    "contact": "👤 Contact Card",
    "location": "📍 Location Pin",
    "other": "⚙️ Service / System Event",
}


def get_message_content_type(message) -> str:
    """
    Extracts the primary content type string from an aiogram Message object.
    """
    if getattr(message, "photo", None):
        return "photo"
    if getattr(message, "video", None):
        return "video"
    if getattr(message, "audio", None):
        return "audio"
    if getattr(message, "document", None):
        return "document"
    if getattr(message, "voice", None):
        return "voice"
    if getattr(message, "sticker", None):
        return "sticker"
    if getattr(message, "animation", None):
        return "animation"
    if getattr(message, "contact", None):
        return "contact"
    if getattr(message, "location", None):
        return "location"
    if getattr(message, "text", None):
        return "text"
    return "other"


def matches_filter(content_type: str, filter_mode: str, selected_types: List[str]) -> bool:
    """
    Evaluates whether a message's content_type should be deleted based on filter mode:
    - 'all': delete every message
    - 'only': delete only if content_type is in selected_types
    - 'except': delete all messages EXCEPT if content_type is in selected_types
    """
    if filter_mode == "all":
        return True

    selected_set: Set[str] = set(selected_types)

    if filter_mode == "only":
        return content_type in selected_set

    if filter_mode == "except":
        return content_type not in selected_set

    return True
