import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import logging
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_USER_TOKEN = os.getenv("SLACK_USER_TOKEN")

CURRENT_CHANNELS = ["C08AHHWBTK8"]
NEXT_CHANNELS = ["C08BAAHFAUV", "C08AYKQ9AQ7"]
NEW_STATUS_EMOJI = ":two:"

client = WebClient(token=SLACK_BOT_TOKEN)


def promote_intern(slack_id: str) -> None:
    try:
        for channel in CURRENT_CHANNELS:
            try:
                client.conversations_kick(
                    channel=channel,
                    user=slack_id,
                    token=SLACK_USER_TOKEN,
                )
            except SlackApiError as e:
                logger.error(
                    f"Failed to kick user from {channel}: {e.response['error']}"
                )

        for channel in NEXT_CHANNELS:
            try:
                client.conversations_invite(channel=channel, users=slack_id)
            except SlackApiError as e:
                logger.error(
                    f"Failed to invite user to {channel}: {e.response['error']}"
                )

        try:
            client.users_profile_set(
                user=slack_id,
                profile={"status_emoji": NEW_STATUS_EMOJI},
                token=SLACK_USER_TOKEN,
            )
        except SlackApiError as e:
            logger.error(f"Failed to set status emoji: {e.response['error']}")
        logger.info(f"Successfully promoted intern {slack_id}")
    except Exception as e:
        logger.error(f"Unexpected error promoting intern {slack_id}: {str(e)}")


def promote_interns(intern_ids: list) -> None:
    for intern_id in intern_ids:
        logger.info(f"Starting promotion process for intern {intern_id}")
        promote_intern(intern_id)
        logger.info(f"Completed promotion process for intern {intern_id}")


if __name__ == "__main__":
    interns_to_promote = ["U08AS0T4TAP"]

    promote_interns(interns_to_promote)
