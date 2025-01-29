from typing import Any, Dict

import requests

from config import logger
from utils import clean_url, handle_promotion


class StageZeroHandler:
    @classmethod
    def create_modal_view(cls, trigger_id: str, channel_id: str) -> dict:
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
                        "text": "Submit your deployed application URL for Stage 0 evaluation.",
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
                    logger.debug("promotion")
                    handle_promotion(0, client, user_id)
                except Exception as e:
                    logger.error(f"Promotion error: {str(e)}")
                    message += (
                        "\n\n⚠️ Promotion error. Please contact an admin."
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
                text="🔧 Something went wrong. Please try again.",
            )

    @classmethod
    def grade(cls, url: str, user_id: str) -> Dict[str, Any]:
        """Grade the Stage 0 submission"""
        clean_submission_url = clean_url(url)
        result = {
            "success": False,
            "valid_url": False,
            "message_found": False,
            "is_nginx": False,
            "server_info": "Unknown",
            "score": 0,
            "error": None,
        }

        if not clean_submission_url:
            result["error"] = "Invalid URL format."
            return result

        result["valid_url"] = True
        result["score"] += 1

        try:
            resp = requests.get(clean_submission_url, timeout=10)
            resp.raise_for_status()

            result["success"] = True
            result["message_found"] = "Welcome to DevOps Stage 0" in resp.text
            if result["message_found"]:
                result["score"] += 1

            server_info = resp.headers.get("Server", "Unknown")
            result["server_info"] = server_info
            result["is_nginx"] = "nginx" in server_info.lower()
            if result["is_nginx"]:
                result["score"] += 1

        except requests.exceptions.RequestException as e:
            result["error"] = "Failed to fetch the URL."

        return result

    @classmethod
    def format_response(cls, result: Dict[str, Any], user_id: str) -> str:
        """Format the grading results"""
        msg = [
            f"Hey <@{user_id}>! 🚀 Stage 0 Evaluation Results:",
            "",
            "📝 *Requirements Check:*",
            f"• Valid URL: {'✅' if result['valid_url'] else '❌'}",
            f"• Welcome Message: {'✅' if result['message_found'] else '❌'}",
            f"• NGINX Server: {'✅' if result['is_nginx'] else '❌'}",
            "",
            f"🖥️ *Server Detected:* {result['server_info']}",
            f"🎯 *Score: {result['score']}/3*",
        ]

        if result["error"]:
            msg.extend(["", f"⚠️ *Note:* {result['error']}"])

        if result["score"] == 3:
            msg.extend(
                [
                    "",
                    "🎉 *Congratulations!* You've achieved a perfect score in Stage 0!",
                    "You're ready to move on to the next stage.",
                ]
            )
        else:
            msg.extend(["", "📋 *To improve your score:*"])
            if not result["valid_url"]:
                msg.append("• Ensure your URL is properly formatted")
            if not result["message_found"]:
                msg.append("• Add 'Welcome to DevOps Stage 0' to your page")
            if not result["is_nginx"]:
                msg.append("• Configure your server to use NGINX")

        return "\n".join(msg)
