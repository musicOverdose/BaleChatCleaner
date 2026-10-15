"""
Configuration management for BaleChatCleaner.
Supports environment variables and .env file loading.
"""

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator


class Settings(BaseSettings):
    # Telegram / Bale Bot Token (obtained from @botfather)
    BOT_TOKEN: str = Field(..., description="Bale Bot Token")

    # Authorized Admin IDs (comma-separated or list of ints)
    ADMIN_IDS: List[int] = Field(default_factory=list, description="List of Telegram/Bale User IDs allowed to access the panel")

    # Bale API base URL
    BALE_API_ENDPOINT: str = Field(default="https://tapi.bale.ai", description="Base URL for Bale Bot API")

    # Database file path
    DB_PATH: str = Field(default="data/cleaner.db", description="SQLite database file location")

    # Anti-Glitch defaults
    DEFAULT_CHANNEL_DELAY: float = Field(default=0.12, description="Delay between message deletes in channels (seconds)")
    DEFAULT_GROUP_DELAY: float = Field(default=0.06, description="Delay between message deletes in groups (seconds)")
    SYNC_PAUSE_INTERVAL: int = Field(default=25, description="Pause deletion every N messages to let client sockets flush")
    SYNC_PAUSE_DURATION: float = Field(default=1.5, description="Duration of sync flush pause (seconds)")
    
    # Scratch chat or channel for non-destructive probing (optional)
    PROBE_SCRATCH_CHAT_ID: int = Field(default=0, description="Chat ID for non-destructive type probing")

    # Logging
    LOG_LEVEL: str = Field(default="INFO", description="Logging level (DEBUG, INFO, WARNING, ERROR)")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, str):
            if not v.strip():
                return []
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, (int, float)):
            return [int(v)]
        if isinstance(v, list):
            return [int(x) for x in v]
        return []


# Global settings singleton
try:
    settings = Settings()
except Exception:
    # Allow fallback during build/testing when BOT_TOKEN is not yet set
    settings = None
