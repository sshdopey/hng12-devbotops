from typing import Any, Dict

import requests

from config import logger, Config
from utils import clean_url, handle_promotion


class StageZeroHandler:
    @classmethod
    def create_modal_view(cls, channel_id: str) -> dict:
        return {
            "type": "modal",
            "title": {
                "type": "plain_text",
                "text": "DevOps Stage 0",
            },
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Please enter the URL where you deployed your site.\n\nMake sure:\n• The URL is accessible\n• It contains 'Welcome to DevOps Stage 0'\n• It's served by NGINX",
                    },
                },
                {
                    "type": "input",
                    "block_id": "deployed_url",
                    "label": {"type": "plain_text", "text": "Deployed URL"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "deployed_url",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Enter the full URL (including http:// or https://)",
                        },
                    },
                },
            ],
            "close": {"type": "plain_text", "text": "Cancel"},
            "submit": {"type": "plain_text", "text": "Submit"},
            "callback_id": "submission",
            "private_metadata": f"{channel_id}:0",
        }

    @classmethod
    def handle_submission(cls, user_id, channel_id, body, client):
        """Handle Stage 0 submission"""
        try:
            url = body["view"]["state"]["values"]["deployed_url"][
                "deployed_url"
            ]["value"]

            result = cls.grade(url, user_id)

            message = cls.format_response(result, user_id)
            if result.get("score", 0) == 3:
                try:
                    current = Config.STAGE_CHANNELS[0]["current"]
                    next_channels = Config.STAGE_CHANNELS[0]["next"]
                    handle_promotion(
                        client,
                        user_id,
                        current,
                        next_channels,
                        Config.STAGE_STATUS_EMOJIS[1],
                        Config.SLACK_USER_TOKEN,
                    )
                    new_channels = [
                        ch for ch in next_channels if ch not in current
                    ]
                    channels_text = ", ".join(
                        [f"<#{ch}>" for ch in new_channels]
                    )
                    client.chat_postMessage(
                        channel=user_id,
                        text=f"{message}\n\nYou should now be able to see the new channels: {channels_text} 🎉",
                    )
                except Exception as e:
                    logger.error(f"Promotion error: {str(e)}")
                    message += "\n\n⚠️ Promotion error. Please contact a mentor - <@U08A036CLGG>."
                    client.chat_postEphemeral(
                        channel=channel_id, user=user_id, text=message
                    )
            else:
                logger.debug(result)
                client.chat_postEphemeral(
                    channel=channel_id, user=user_id, text=message
                )

        except Exception as e:
            logger.error(f"Submission error: {str(e)}")
            client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text=":wrench: Something went wrong. Please try again.",
            )

    @classmethod
    def grade(cls, url: str, user_id: str) -> Dict[str, Any]:
        """Grade the Stage 0 submission"""
        clean_submission_url = clean_url(url)
        result = {
            "valid_url": False,
            "message_found": False,
            "is_nginx": False,
            "server_info": "Unknown",
            "score": 0,
        }

        if not clean_submission_url:
            return result

        try:
            resp = requests.get(clean_submission_url, timeout=10)
            resp.raise_for_status()

            result["valid_url"] = True
            result["score"] += 1

            result["message_found"] = "Welcome to DevOps Stage 0" in resp.text
            if result["message_found"]:
                result["score"] += 1

            server_info = resp.headers.get("Server", "Unknown")
            result["server_info"] = server_info
            result["is_nginx"] = "nginx" in server_info.lower()
            if result["is_nginx"]:
                result["score"] += 1

        except requests.exceptions.RequestException:
            pass

        return result

    @classmethod
    def format_response(cls, result: Dict[str, Any], user_id: str) -> str:
        """Format the grading results"""
        msg = [
            f"Hey <@{user_id}>! Here's your Stage 0 result:",
            "",
            "*Requirements:*",
            f"• *Valid URL:* {':white_check_mark: Passed' if result['valid_url'] else ':x: Failed'}",
            f"• *Welcome Message:* {':white_check_mark: Passed' if result['message_found'] else ':x: Failed'}",
            f"• *NGINX Server:* {':white_check_mark: Passed' if result['is_nginx'] else ':x: Failed'}",
            "",
            f"*Server Detected:* {result['server_info']}",
            f"*Score: {result['score']}/3*",
        ]

        if result["score"] < 3:
            msg.extend(["", "*To improve your score:*"])
            if not result["valid_url"]:
                msg.append("• Ensure your URL is properly formatted")
            if not result["message_found"]:
                msg.append("• Add 'Welcome to DevOps Stage 0' to your page")
            if not result["is_nginx"]:
                msg.append("• Configure your server to use NGINX")
            msg.extend(
                ["", "Make these changes and use *`/submit`* to try again!"]
            )

        return "\n".join(msg)
