from datetime import datetime
from typing import Any

from config import Config, logger, wat_tz
from spreadsheet import Sheet
from stages.stage_2_grader import StageTwoGrader
from utils import check_url_uniqueness, handle_promotion


class StageTwoDevOps:
    next_emoji = ":three:"
    channels = ["C08AYKQ9AQ7"]
    next_channels = ["C08CM5W329Z", "C08DA2RDPRN"]
    required_score = 9
    max_trials = 20
    deadline = wat_tz.localize(
        datetime.strptime("2025-02-14 23:59:59", "%Y-%m-%d %H:%M:%S")
    )
    sheet = Sheet(
        "1ZA1b5xSTcZKjclGIXG4Ph5MT6BnsXrnu-2sMXaPHoY8",
        {
            "A": "timestamp",
            "B": "display_name",
            "C": "user_id",
            "D": "trials",
            "E": "deployed_url",
            "F": "github_url",
            "G": "score",
        },
    )

    def submission_view(self, channel: str) -> dict:
        """Returns the Slack modal view for Stage 2 submission."""
        now = datetime.now(wat_tz)
        if now > self.deadline:
            return {
                "type": "modal",
                "title": {
                    "type": "plain_text",
                    "text": "Backend x DevOps Stage 2",
                },
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "❌ The deadline for Stage 2 submissions has passed.",
                        },
                    }
                ],
                "close": {"type": "plain_text", "text": "Close"},
            }

        time_left = self.deadline - now
        days = time_left.days
        hours = time_left.seconds // 3600
        minutes = (time_left.seconds % 3600) // 60
        return {
            "type": "modal",
            "title": {
                "type": "plain_text",
                "text": "Backend x DevOps Stage 2",
            },
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"⏰ Time remaining: {days} days, {hours} hours, {minutes} minutes",
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "⚠️ *IMPORTANT:* Before submitting, please ensure you have installed the *HNG12 Bot* GitHub App on your repository: https://github.com/apps/hng12-bot",
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "ℹ️ Please submit the *domain/subdomain* of the deployed application (e.g., `https://your-domain.com`).",
                    },
                },
                {
                    "type": "input",
                    "block_id": "deployed_url",
                    "label": {
                        "type": "plain_text",
                        "text": "Deployed URL",
                    },
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "deployed_url",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "https://your-domain.com",
                        },
                    },
                },
                {
                    "type": "input",
                    "block_id": "github_url",
                    "label": {
                        "type": "plain_text",
                        "text": "GitHub Repository URL",
                    },
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "github_url",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "https://github.com/username/repository",
                        },
                    },
                },
            ],
            "close": {"type": "plain_text", "text": "Cancel"},
            "submit": {"type": "plain_text", "text": "Submit"},
            "callback_id": "submission",
            "private_metadata": channel,
        }

    def _grade_submission(self, grader: StageTwoGrader) -> tuple[float, list]:
        score = 1.0
        result = []
        checks = [
            (grader.validate_initial_endpoint, 2),
            (grader.test_bad_pr, 1),
            (grader.test_good_pr, 2),
            (grader.check_deployment, 2),
            (grader.validate_deployed_endpoint, 1),
        ]

        for check_func, points in checks:
            validation = check_func()
            if not validation.success:
                result.append(f"❌ {validation.message}")
                if validation.details:
                    result.append(f"Details: {validation.details}")
                return score, result
            score += points
            result.append(f"✅ {validation.message}")

        return score, result

    def submit(self, channel: str, body: dict, client: Any) -> None:
        user_id = body["user"]["id"]
        data = {}
        grader = None

        try:
            submission = self.sheet.get_row("user_id", user_id)
            if submission:
                trials = int(submission[1].get("trials", "0"))
                score = submission[1].get("score", "0")
                if trials >= self.max_trials:
                    client.chat_postEphemeral(
                        channel=channel,
                        user=user_id,
                        text="❌ You have used all your attempts (20/20).",
                    )
                    return
                if score == "grading":
                    client.chat_postEphemeral(
                        channel=channel,
                        user=user_id,
                        text="❌ Your previous submission is still being graded. Please wait.",
                    )
                    return
            else:
                trials = 0

            values = body["view"]["state"]["values"]
            deployed_url = values["deployed_url"]["deployed_url"][
                "value"
            ].strip()
            github_url = values["github_url"]["github_url"]["value"].strip()

            for url, field in [
                (deployed_url, "deployed_url"),
                (github_url, "github_url"),
            ]:
                is_unique, msg = check_url_uniqueness(
                    self.sheet, url, user_id, field
                )
                if not is_unique:
                    client.chat_postEphemeral(
                        channel=channel, user=user_id, text=f"❌ {msg}"
                    )
                    return

            timestamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
            data = {
                "timestamp": timestamp,
                "deployed_url": deployed_url,
                "github_url": github_url,
                "score": "grading",
                "trials": str(trials + 1),
            }
            if submission:
                self.sheet.update(submission[0], data)
            else:
                profile = client.users_profile_get(user=user_id)
                if profile["ok"]:
                    username = profile["profile"]["display_name"]
                    if not username:
                        username = profile["profile"]["real_name"]
                else:
                    username = body["user"]["name"]
                data["display_name"] = username
                data["user_id"] = user_id
                self.sheet.append(data)
                submission = self.sheet.get_row("user_id", user_id)

            repo_name = "/".join(github_url.split("/")[-2:]).replace(
                ".git", ""
            )
            grader = StageTwoGrader(repo_name, deployed_url)
            grader._save_main_content()

            client.chat_postEphemeral(
                channel=channel,
                user=user_id,
                text=f"🔄 Your submission has been received! Grading process is starting...\n"
                f"• Monitor your repository: {github_url}\n"
                "• Watch for bot activities to help debug any issues\n"
                "• Please be patient while I evaluate your submission",
            )

            score, result = self._grade_submission(grader)
            achieved = score >= self.required_score

            data["score"] = str(score)
            self.sheet.update(submission[0], data)

            message = "\n".join(result)
            attempts_msg = f"\nAttempts used: {trials + 1}/{self.max_trials}"
            if achieved:
                handle_promotion(
                    client,
                    user_id,
                    self.channels,
                    self.next_channels,
                    self.next_emoji,
                    Config.SLACK_USER_TOKEN,
                )
                client.chat_postMessage(
                    channel=user_id,
                    text=f"{message}\n\n🚀 Access granted to next stage!{attempts_msg}",
                )
            else:
                client.chat_postEphemeral(
                    channel=channel,
                    user=user_id,
                    text=f"{message}{attempts_msg}",
                )

        except Exception as e:
            logger.error(f"Submission error: {e}")

            data["score"] = "0"
            self.sheet.update(submission[0], data)

            error_msg = (
                "❌ Invalid GitHub repository. Please ensure:\n"
                "• HNG12 Bot GitHub App is installed on your repository: https://github.com/apps/hng12-bot"
                f"\nAttempts used: {trials + 1}/{self.max_trials}"
            )
            client.chat_postEphemeral(
                channel=channel, user=user_id, text=error_msg
            )
        finally:
            try:
                if (
                    grader is not None
                    and grader.original_main_content is not None
                ):
                    grader._restore_main_content()
            except Exception as restore_error:
                logger.error(
                    f"Failed to restore main content: {restore_error}"
                )


class StageTwoBackend(StageTwoDevOps):
    channels = ["C08B6GUP4PQ"]
    next_channels = ["C08DA2RDPRN", "C08CR90L1NE"]
    sheet = Sheet(
        "1Ah-HVmKHL4sEJCCKGnSGu-AXEZxPJ0ltDn7MCVIUH7Q",
        {
            "A": "timestamp",
            "B": "display_name",
            "C": "user_id",
            "D": "trials",
            "E": "deployed_url",
            "F": "github_url",
            "G": "score",
        },
    )
