import logging
from typing import Optional
from urllib.parse import urlparse
from config import Config

logger = logging.getLogger(__name__)


def clean_url(url: str) -> Optional[str]:
    """Clean and validate URL"""
    if not url:
        return None

    if not url.startswith(("http://", "https://")):
        url = "http://" + url

    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
    except:
        return None


def handle_promotion(stage, client, user_id):
    """Handle user promotion to next stage"""
    try:
        # for channel in Config.STAGE_CHANNELS[stage]["current"]:
        #     client.conversations_kick(channel=channel, user=user_id, token=Config.SLACK_USER_TOKEN)

        for channel in Config.STAGE_CHANNELS[stage]["next"]:
            client.conversations_invite(channel=channel, users=user_id)

        # client.users_profile_set(
        #     user=user_id,
        #     profile={"status_emoji": Config.STAGE_STATUS_EMOJIS[stage + 1]},
        #     token=Config.SLACK_USER_TOKEN
        # )
    except Exception as e:
        logger.error(f"Promotion error: {str(e)}")
        raise
