import logging
import os

from dotenv import load_dotenv
import pytz

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
wat_tz = pytz.timezone("Africa/Lagos")


class Config:
    SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
    SLACK_USER_TOKEN = os.getenv("SLACK_USER_TOKEN")
    SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN")
    SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET")
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
    MAINTENANCE_MODE = bool(os.getenv("MAINTENANCE_MODE", False))
