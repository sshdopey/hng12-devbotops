from datetime import datetime
from typing import Any

import requests
from requests.exceptions import RequestException

from config import Config, logger
from spreadsheet import Sheet
from utils import handle_promotion


class StageZero:
    """Handles Stage 0 submissions and promotions for the DevOps program."""

    emoji = ":zero:"
    channels = ["C089GSHEMFT"]
    next_channels = ["C089GSHEMFT", "C08AHHWBTK8", "C08B3UKM0QN"]
    required_score = 5
    expected_text = "Welcome to DevOps Stage 0"

    backlinks = [
        "https://hng.tech/hire/devops-engineers",
        "https://hng.tech/hire/cloud-engineers",
        "https://hng.tech/hire/site-reliability-engineers",
        "https://hng.tech/hire/platform-engineers",
        "https://hng.tech/hire/infrastructure-engineers",
        "https://hng.tech/hire/kubernetes-specialists",
        "https://hng.tech/hire/aws-solutions-architects",
        "https://hng.tech/hire/azure-devops-engineers",
        "https://hng.tech/hire/google-cloud-engineers",
        "https://hng.tech/hire/ci-cd-pipeline-engineers",
        "https://hng.tech/hire/monitoring-observability-engineers",
        "https://hng.tech/hire/automation-engineers",
        "https://hng.tech/hire/docker-specialists",
        "https://hng.tech/hire/linux-developers",
        "https://hng.tech/hire/postgresql-developers",
    ]

    sheet = Sheet(
        "1t-JU71GkCOlYf7nAWdJWxoJpzNcDiKlqfB4aZDmDiAg",
        {
            "A": "timestamp",
            "B": "username",
            "C": "user_id",
            "D": "trials",
            "E": "deployed_url",
            "F": "blog_url",
            "G": "promoted",
        },
    )

    def submission_view(self, channel: str) -> dict:
        """Returns the Slack modal view for Stage 0 submission."""
        return {
            "type": "modal",
            "title": {"type": "plain_text", "text": "DevOps Stage 0"},
            "blocks": [
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
                {
                    "type": "input",
                    "block_id": "blog_url",
                    "label": {"type": "plain_text", "text": "Blog Post URL"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "blog_url",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Enter your blog post URL",
                        },
                    },
                },
            ],
            "close": {"type": "plain_text", "text": "Cancel"},
            "submit": {"type": "plain_text", "text": "Submit"},
            "callback_id": "submission",
            "private_metadata": channel,
        }

    def submit(self, channel: str, body: dict, client: Any) -> None:
        """Process Stage 0 submission and handle promotion if successful."""
        try:
            user_id = body["user"]["id"]
            username = body["user"]["name"]
            values = body["view"]["state"]["values"]
            deployed_url = values["deployed_url"]["deployed_url"]["value"]
            blog_url = values["blog_url"]["blog_url"]["value"]

            # Check if user has already been promoted
            submission = self.sheet.get_row("user_id", user_id)
            if submission and submission[1].get("promoted") == "1":
                client.chat_postEphemeral(
                    channel=channel,
                    user=user_id,
                    text="🎉 You have already passed Stage 0! No need to submit again.",
                )
                return

            # Validate URL uniqueness
            for url, url_type in [
                (deployed_url, "deployed_url"),
                (blog_url, "blog_url"),
            ]:
                is_unique, message = self._check_url_uniqueness(
                    url, url_type, user_id
                )
                if not is_unique:
                    client.chat_postEphemeral(
                        channel=channel,
                        user=user_id,
                        text=f"❌ {message}",
                    )
                    return

            # Grade submission
            score, result = self._grade_submission(deployed_url, blog_url)
            promoted = score >= self.required_score

            # Update or create submission record
            timestamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
            if submission:
                current_trials = int(submission[1].get("trials", 0))
                trials = current_trials + 1
                self.sheet.update(
                    submission[0],
                    {
                        "timestamp": timestamp,
                        "deployed_url": deployed_url,
                        "blog_url": blog_url,
                        "promoted": "1" if promoted else "0",
                        "trials": str(trials),
                    },
                )
            else:
                trials = 1
                self.sheet.append(
                    {
                        "timestamp": timestamp,
                        "username": username,
                        "user_id": user_id,
                        "deployed_url": deployed_url,
                        "blog_url": blog_url,
                        "promoted": "1" if promoted else "0",
                        "trials": "1",
                    }
                )

            # Handle results and promotion
            message = self._get_result_message(result, score, user_id, trials)
            if promoted:
                handle_promotion(
                    client,
                    user_id,
                    self.channels,
                    self.next_channels,
                    self.emoji,
                    Config.SLACK_USER_TOKEN,
                )

                new_channels = [
                    f"<#{ch}>"
                    for ch in self.next_channels
                    if ch not in self.channels
                ]
                client.chat_postMessage(
                    channel=user_id,
                    text=f"{message}\n\n🚀 Access granted to: {', '.join(new_channels)}",
                )
            else:
                client.chat_postEphemeral(
                    channel=channel,
                    user=user_id,
                    text=message,
                )

        except Exception as e:
            logger.error(f"Submission error: {str(e)}")
            client.chat_postEphemeral(
                channel=channel,
                user=user_id,
                text="🚨 An error occurred while processing your submission. Please try again or contact support.",
            )

    def _check_url_uniqueness(
        self, url: str, url_type: str, user_id: str
    ) -> tuple[bool, str]:
        """Check if URL has been used by another intern."""
        submission = self.sheet.get_row(url_type, url)
        if submission and submission[1].get("user_id") != user_id:
            return (
                False,
                f"This {url_type.replace('_', ' ')} has already been submitted by another intern.",
            )
        return True, ""

    def _fetch_url_content(
        self, url: str, timeout: int = 15
    ) -> tuple[bool, str, requests.Response]:
        """Fetch URL content safely."""
        try:
            response = requests.get(url, timeout=timeout, allow_redirects=True)
            response.raise_for_status()
            return True, "", response
        except RequestException as e:
            return False, f"Error accessing URL: {str(e)}", None

    def _check_backlinks(self, content: str) -> bool:
        """Check if content contains at least one backlink."""
        return any(backlink in content for backlink in self.backlinks)

    def _grade_submission(
        self, deployed_url: str, blog_url: str
    ) -> tuple[int, dict]:
        """Grade submission based on technical requirements."""
        score = 0
        result = {
            "deployed_valid": False,
            "message_present": False,
            "nginx_present": False,
            "blog_valid": False,
            "backlink_present": False,
            "server": "Unknown",
            "errors": [],
        }

        # Check deployed URL
        success, error, response = self._fetch_url_content(deployed_url)
        if success:
            result["deployed_valid"] = True
            score += 1

            if self.expected_text in response.text:
                result["message_present"] = True
                score += 1

            server = response.headers.get("Server", "Unknown")
            result["server"] = server
            if "nginx" in server.lower():
                result["nginx_present"] = True
                score += 1
        else:
            result["errors"].append(f"Deployed URL: {error}")

        # Check blog URL
        success, error, response = self._fetch_url_content(blog_url)
        if success:
            result["blog_valid"] = True
            score += 1

            if self._check_backlinks(response.text):
                result["backlink_present"] = True
                score += 1
        else:
            result["errors"].append(f"Blog URL: {error}")

        return score, result

    def _get_result_message(
        self, result: dict, score: int, user_id: str, trials: int
    ) -> str:
        """Generate detailed submission result message."""
        message = [
            f"<@{user_id}> Stage 0 Results (Attempt #{trials}):\n",
            "📋 Requirements Check:",
            f"{'✅' if result['deployed_valid'] else '❌'} Deployed URL is accessible",
            f"{'✅' if result['message_present'] else '❌'} Welcome message present",
            f"{'✅' if result['nginx_present'] else '❌'} NGINX server detected",
            f"{'✅' if result['blog_valid'] else '❌'} Blog post is accessible",
            f"{'✅' if result['backlink_present'] else '❌'} Backlink's present",
            f"Server: {result['server']}",
            f"Score: {score}/{self.required_score}\n",
        ]

        if result["errors"]:
            message.append("⚠️ Errors encountered:")
            message.extend(f"• {error}" for error in result["errors"])
            message.append("")

        if score < self.required_score:
            message.append("📝 Required improvements:")
            if not result["deployed_valid"]:
                message.append("• Ensure your deployed URL is accessible")
            if not result["message_present"]:
                message.append(f"• Add '{self.expected_text}' to your page")
            if not result["nginx_present"]:
                message.append("• Configure NGINX as your web server")
            if not result["blog_valid"]:
                message.append("• Ensure your blog post URL is accessible")
            if not result["backlink_present"]:
                message.append(
                    "• Include at least one of the provided backlinks in your blog post"
                )
            message.append(
                "\n💡 Resubmit when you've made these improvements!"
            )
        else:
            message.append(
                f"🎉 Congratulations! You've completed Stage 0 in {trials} {'attempt' if trials == 1 else 'attempts'}!"
            )

        return "\n".join(message)
