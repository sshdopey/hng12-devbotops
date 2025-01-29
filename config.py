import logging
import os

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Config:
    SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
    SLACK_USER_TOKEN = os.getenv("SLACK_USER_TOKEN")
    SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
    SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///submissions.db")

    STAGE_CHANNELS = {
        0: {
            "current": ["C089GSHEMFT"],
            "next": ["C08AHHWBTK8"],
        },
        1: {
            "current": ["C08AHHWBTK8"],
            "next": ["C08AHHWBTK8"],
        },
    }

    STAGE_STATUS_EMOJIS = {0: ":zero:", 1: ":one:", 2: ":two:"}

    @classmethod
    def get_stage_for_channel(cls, channel_id: str) -> int:
        """Determine stage number based on channel ID"""
        for stage, channels in cls.STAGE_CHANNELS.items():
            if channel_id in channels["current"]:
                return stage
        return None
