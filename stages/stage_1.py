import json
from datetime import datetime
from typing import Any

import pytz
import requests

from config import Config, logger
from spreadsheet import Sheet
from utils import handle_promotion


class StageOne:
    """Handles Stage 1 submissions and promotions for the DevOps program."""

    next_emoji = ":two:"
    channels = ["C08AHHWBTK8"]
    next_channels = ["C08BAAHFAUV", "C08AYKQ9AQ7"]
    required_score = 6
    wat_tz = pytz.timezone("Africa/Lagos")
    deadline = wat_tz.localize(
        datetime.strptime("2025-02-09 23:59:59", "%Y-%m-%d %H:%M:%S")
    )

    test_cases = [
        {"number": "371", "expected_properties": ["armstrong", "odd"]},
        {"number": "6", "expected_properties": ["even"]},
        {"number": "17", "expected_properties": ["odd"]},
        {"number": "abc", "error": True},
        {"number": "-5", "expected_properties": ["odd"]},
        {"number": "0", "expected_properties": ["even"]},
    ]

    sheet = Sheet(
        "1mq_WtbIoRPwHhHajcI2seAtgN4oI7ya2rAnmx1rjffg",
        {
            "A": "timestamp",
            "B": "username",
            "C": "user_id",
            "D": "trials",
            "E": "api_url",
            "F": "github_url",
            "G": "score",
        },
    )

    def submission_view(self, channel: str) -> dict:
        """Returns the Slack modal view for Stage 1 submission."""
        now = datetime.now(self.wat_tz)
        if now > self.deadline:
            return {
                "type": "modal",
                "title": {"type": "plain_text", "text": "DevOps Stage 1"},
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "❌ The deadline for Stage 1 submissions has passed.",
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
            "title": {"type": "plain_text", "text": "DevOps Stage 1"},
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
                        "text": "ℹ️ Please submit the *complete endpoint URL* for your number classification API, including the path (e.g., `https://your-domain.com/api/classify-number`).",
                    },
                },
                {
                    "type": "input",
                    "block_id": "api_url",
                    "label": {
                        "type": "plain_text",
                        "text": "API Endpoint URL",
                    },
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "api_url",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "https://your-domain.com/api/classify-number",
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

    def submit(self, channel: str, body: dict, client: Any) -> None:
        """Process Stage 1 submission and handle promotion if successful."""
        try:
            user_id = body["user"]["id"]
            values = body["view"]["state"]["values"]
            api_url = values["api_url"]["api_url"]["value"]
            github_url = values["github_url"]["github_url"]["value"]
            profile = client.users_profile_get(user=user_id)
            if profile["ok"]:
                username = profile["profile"]["display_name"]
                if not username:
                    username = profile["profile"]["real_name"]
            else:
                username = body["user"]["name"]

            submission = self.sheet.get_row("user_id", user_id)
            if (
                submission
                and float(submission[1].get("score", 0)) >= self.required_score
            ):
                client.chat_postEphemeral(
                    channel=channel,
                    user=user_id,
                    text="🎉 Congratulations! You've already achieved a perfect score in Stage 1! You can proceed to the next stage.",
                )
                return

            is_unique, message = self._check_url_uniqueness(
                api_url, user_id, "api_url"
            )
            if not is_unique:
                client.chat_postEphemeral(
                    channel=channel,
                    user=user_id,
                    text=f"❌ {message}",
                )
                return

            is_unique, message = self._check_url_uniqueness(
                github_url, user_id, "github_url"
            )
            if not is_unique:
                client.chat_postEphemeral(
                    channel=channel,
                    user=user_id,
                    text=f"❌ {message}",
                )
                return

            github_valid, github_message = self._validate_github_url(
                github_url
            )
            if not github_valid:
                client.chat_postEphemeral(
                    channel=channel,
                    user=user_id,
                    text=f"❌ {github_message}",
                )
                return

            score, result = self._grade_submission(api_url)
            achieved_required_score = score >= self.required_score

            timestamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
            if submission:
                current_trials = int(submission[1].get("trials", 0))
                trials = current_trials + 1
                current_best_score = float(submission[1].get("score", 0))
                best_score = max(current_best_score, score)

                self.sheet.update(
                    submission[0],
                    {
                        "timestamp": timestamp,
                        "api_url": api_url,
                        "github_url": github_url,
                        "score": str(best_score),
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
                        "api_url": api_url,
                        "github_url": github_url,
                        "score": str(score),
                        "trials": "1",
                    },
                )

            message = self._get_result_message(score, result, user_id, trials)
            if achieved_required_score:
                handle_promotion(
                    client,
                    user_id,
                    self.channels,
                    self.next_channels,
                    self.next_emoji,
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
        self, url: str, user_id: str, field: str = "api_url"
    ) -> tuple[bool, str]:
        """Check if URL has been used by another intern.

        Args:
            url: The URL to check
            user_id: The ID of the current user
            field: The field to check ('api_url' or 'github_url')

        Returns:
            tuple[bool, str]: (is_unique, error_message)
        """
        submission = self.sheet.get_row(field, url)
        if submission and submission[1].get("user_id") != user_id:
            field_name = (
                "API endpoint" if field == "api_url" else "GitHub repository"
            )
            return (
                False,
                f"This {field_name} has already been submitted by another intern.",
            )
        return True, ""

    def _validate_github_url(self, url: str) -> tuple[bool, str]:
        """Validate GitHub URL and check for README."""
        if not url.startswith("https://github.com/"):
            return False, "Please provide a valid GitHub repository URL"

        repo_path = "/".join(
            url.replace("https://github.com/", "").split("/")[:2]
        )
        readme_url = (
            f"https://raw.githubusercontent.com/{repo_path}/main/README.md"
        )

        try:
            response = requests.get(readme_url, timeout=10)
            if response.status_code != 200:
                return (
                    False,
                    "Repository must have a README.md file in the main branch",
                )

            if len(response.text.strip()) < 100:
                return (
                    False,
                    "README.md seems too short. Please provide a more detailed description of your project",
                )

            return True, "Success"
        except requests.RequestException:
            return (
                False,
                "Could not access the repository. Make sure it's public and the URL is correct",
            )

    def _test_endpoint(
        self, url: str, test_case: dict
    ) -> tuple[bool, dict, str]:
        """Test a single endpoint with a test case."""
        try:
            test_url = f"{url.rstrip('/')}?number={test_case['number']}"
            response = requests.get(test_url, timeout=10)

            try:
                result = response.json()
            except json.JSONDecodeError:
                return False, None, "Your API must return valid JSON"

            if not response.headers.get("Content-Type", "").startswith(
                "application/json"
            ):
                return (
                    False,
                    None,
                    "Response must have Content-Type: application/json header",
                )

            if "error" in test_case:
                if response.status_code != 400:
                    return (
                        False,
                        result,
                        "Invalid input should return 400 status code",
                    )
                if not isinstance(result.get("number"), str):
                    return (
                        False,
                        result,
                        "For invalid input, number field should contain the invalid input",
                    )
                if not result.get("error"):
                    return (
                        False,
                        result,
                        "Invalid input should have error field set to true",
                    )
                return True, result, "Success"

            if response.status_code != 200:
                input_type = (
                    "negative"
                    if test_case["number"].startswith("-")
                    else (
                        "floating-point"
                        if "." in test_case["number"]
                        else "valid integer"
                    )
                )
                return (
                    False,
                    result,
                    f"Your API returned {response.status_code} for a {input_type} number. All valid numbers should return 200 status code, even if they're negative or floating-point values.",
                )

            validation_results = []
            for check, message in self._get_validation_checks(
                result, test_case
            ):
                if not check():
                    validation_results.append(message)

            if validation_results:
                return False, result, "\n".join(validation_results)

            if test_case["number"] == "0" and result.get("is_perfect") is True:
                return (
                    False,
                    result,
                    "0 should not be classified as a perfect number (is_perfect should be false)",
                )

            if "expected_properties" in test_case and set(
                test_case["expected_properties"]
            ).difference(set(result.get("properties", []))):
                property_type = (
                    "negative numbers"
                    if test_case["number"].startswith("-")
                    else "this type of number"
                )
                return (
                    False,
                    result,
                    f"Properties list is incorrect for {property_type}. Expected only armstrong/odd/even in properties list.",
                )

            return True, result, "Success"

        except requests.exceptions.RequestException as e:
            if "Connection refused" in str(e):
                return (
                    False,
                    None,
                    "Could not connect to your API. Make sure it's running and publicly accessible.",
                )
            if "timeout" in str(e):
                return (
                    False,
                    None,
                    "Your API took too long to respond (>10 seconds)",
                )
            return False, None, f"Request failed: {str(e)}"
        except Exception as e:
            input_type = (
                "negative"
                if test_case["number"].startswith("-")
                else (
                    "floating-point"
                    if "." in test_case["number"]
                    else "valid integer"
                )
            )
            return (
                False,
                None,
                f"Your API threw an unexpected error when processing a {input_type} number. Make sure you handle all valid number types, including negative and floating-point values: {str(e)}",
            )

    def _get_validation_checks(self, result: dict, test_case: dict) -> list:
        """Return list of validation checks for API response."""
        input_type = (
            "negative"
            if test_case["number"].startswith("-")
            else "floating-point" if "." in test_case["number"] else "integer"
        )

        return [
            (
                lambda: "number" in result,
                f"Response must include 'number' field (failed on {input_type} input)",
            ),
            (
                lambda: isinstance(result.get("number"), (int, float)),
                f"Number field must be numeric (failed on {input_type} input)",
            ),
            (
                lambda: "is_prime" in result,
                f"Response must include 'is_prime' field (failed on {input_type} input)",
            ),
            (
                lambda: isinstance(result.get("is_prime"), bool),
                f"is_prime must be boolean (failed on {input_type} input)",
            ),
            (
                lambda: "is_perfect" in result,
                f"Response must include 'is_perfect' field (failed on {input_type} input)",
            ),
            (
                lambda: isinstance(result.get("is_perfect"), bool),
                f"is_perfect must be boolean (failed on {input_type} input)",
            ),
            (
                lambda: "properties" in result,
                f"Response must include 'properties' field (failed on {input_type} input)",
            ),
            (
                lambda: isinstance(result.get("properties"), list),
                f"properties must be an array (failed on {input_type} input)",
            ),
            (
                lambda: "digit_sum" in result,
                f"Response must include 'digit_sum' field (failed on {input_type} input)",
            ),
            (
                lambda: isinstance(result.get("digit_sum"), (int, float)),
                f"digit_sum must be numeric (failed on {input_type} input)",
            ),
            (
                lambda: "fun_fact" in result,
                f"Response must include 'fun_fact' field (failed on {input_type} input)",
            ),
            (
                lambda: isinstance(result.get("fun_fact"), str),
                f"fun_fact must be a string (failed on {input_type} input)",
            ),
        ]

    def _grade_submission(self, api_url: str) -> tuple[float, list]:
        """Grade submission and return score with detailed feedback."""
        total_score = 0
        messages = []
        test_results = []

        for test_case in self.test_cases:
            success, _, message = self._test_endpoint(api_url, test_case)
            test_results.append((success, message))
            if success:
                total_score += 1

        final_score = (total_score / len(self.test_cases)) * 6

        if final_score == 0:
            messages = [
                "Your API needs some work. Here's what to fix:",
                *[f"• {msg}" for _, msg in test_results if msg != "Success"],
                "\n💡 Make sure your API:",
                "• Returns valid JSON responses",
                "• Sets Content-Type: application/json header",
                "• Includes all required fields with correct types",
                "• Handles errors properly",
            ]
        elif final_score < 6:
            messages = [
                "Your API is working, but there are some issues to fix:",
                *[f"• {msg}" for _, msg in test_results if msg != "Success"],
                "\n💪 You're making progress! Keep going and try again to achieve a perfect score.",
            ]
        else:
            messages = [
                "🌟 Perfect implementation! Your API:",
                "• Returns valid JSON responses",
                "• Includes all required fields",
                "• Handles errors correctly",
                "• Uses proper status codes",
            ]

        return final_score, messages

    def _get_result_message(
        self, score: float, messages: list, user_id: str, trials: int
    ) -> str:
        """Generate a clear, encouraging feedback message."""
        status = "🎯 Getting closer!" if score > 0 else "🚀 Let's begin!"
        if score >= 6:
            status = "🌟 Perfect score!"

        retry_message = (
            "💪 Don't give up! You can keep trying until you get a perfect score."
            if score < 6
            else "🎊 Congratulations! You can now proceed to the next stage!"
        )

        return (
            f"<@{user_id}> Stage 1 Results (Attempt #{trials})\n\n"
            f"{status}\n"
            f"Score: {score:.1f}/6.0\n\n"
            f"{chr(10).join(messages)}\n\n"
            f"{retry_message}"
        )
