import logging
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def get_stage(stages, channel: str):
    """Gets the stage for a channel"""
    for _, stage in stages.items():
        if channel in stage.channels:
            return stage()
    return None


def clean_url(url: str) -> str:
    """Clean and validate URL"""
    if not url.startswith(("http://", "https://")):
        return ""

    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return ""
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
    except ValueError:
        return ""


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


def check_url_uniqueness(
    sheet, url: str, user_id: str, field: str = "deployed_url"
) -> tuple[bool, str]:
    """Check if URL has been used by another intern.

    Args:
        sheet: The sheet object
        url: The URL to check
        user_id: The ID of the current user
        field: The field to check ('deployed_url' or 'github_url')

    Returns:
        tuple[bool, str]: (is_unique, error_message)
    """
    submission = sheet.get_row(field, url)
    if submission and submission[1].get("user_id") != user_id:
        field_name = (
            "API endpoint" if field == "deployed_url" else "GitHub repository"
        )
        return (
            False,
            f"This {field_name} has already been submitted by another intern.",
        )
    return True, ""
