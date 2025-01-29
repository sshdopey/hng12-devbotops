import logging
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def clean_url(url: str) -> Optional[str]:
    """Clean and validate URL"""
    if not url.startswith(("http://", "https://")):
        return None

    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
    except:
        return None


def handle_promotion(client, user_id, current, next, status_emoji, token):
    """Handle user promotion to next stage"""
    for channel in current:
        try:
            client.conversations_kick(
                channel=channel, user=user_id, token=token
            )
        except Exception as e:
            logger.error(
                f"Error kicking user from channel {channel}: {str(e)}"
            )

    for channel in next:
        try:
            client.conversations_invite(channel=channel, users=user_id)
        except Exception as e:
            logger.error(f"Error inviting user to channel {channel}: {str(e)}")

    try:
        client.users_profile_set(
            user=user_id, profile={"status_emoji": status_emoji}, token=token
        )
    except Exception as e:
        logger.error(f"Error setting user profile: {str(e)}")
