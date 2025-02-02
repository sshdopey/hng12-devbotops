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

    emoji = ":one:"
    channels = ["C08AHHWBTK8"]
    next_channels = ["C08BAAHFAUV"]
    required_score = 6
    wat_tz = pytz.timezone("Africa/Lagos")
    deadline = wat_tz.localize(
        datetime.strptime("2025-02-07 23:59:59", "%Y-%m-%d %H:%M:%S")
    )

    test_cases = [
        {"number": "371", "expected_properties": ["armstrong", "odd"]},
        {"number": "6", "expected_properties": ["perfect", "even"]},
        {"number": "17", "expected_properties": ["prime", "odd"]},
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
            "H": "promoted",  # We'll keep this column but use it differently
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
                    "type": "input",
                    "block_id": "api_url",
                    "label": {"type": "plain_text", "text": "API URL"},
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "api_url",
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Enter your API endpoint URL (e.g., https://your-api.com/api/classify-number)",
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
                            "text": "Enter your GitHub repository URL",
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
            username = body["user"]["name"]
            values = body["view"]["state"]["values"]
            api_url = values["api_url"]["api_url"]["value"]
            github_url = values["github_url"]["github_url"]["value"]

            submission = self.sheet.get_row("user_id", user_id)
            if submission and float(submission[1].get("score", 0)) >= self.required_score:
                client.chat_postEphemeral(
                    channel=channel,
                    user=user_id,
                    text="🎉 You have already achieved a perfect score in Stage 1! No need to submit again.",
                )
                return

            for url, url_type in [
                (api_url, "api_url"),
                (github_url, "github_url"),
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
                    }
                )

            # Handle results and promotion
            message = self._get_result_message(score, result, user_id, trials)
            if achieved_required_score:
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

            # Handle error case testing
            if test_case.get("error_test"):
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

            # Handle successful case testing
            if response.status_code != 200:
                return (
                    False,
                    result,
                    "Valid input should return 200 status code",
                )

            checks = [
                (
                    lambda: "number" in result,
                    "Response must include 'number' field",
                ),
                (
                    lambda: isinstance(result.get("number"), (int, float)),
                    "Number field must be numeric",
                ),
                (
                    lambda: "is_prime" in result,
                    "Response must include 'is_prime' field",
                ),
                (
                    lambda: isinstance(result.get("is_prime"), bool),
                    "is_prime must be boolean",
                ),
                (
                    lambda: "is_perfect" in result,
                    "Response must include 'is_perfect' field",
                ),
                (
                    lambda: isinstance(result.get("is_perfect"), bool),
                    "is_perfect must be boolean",
                ),
                (
                    lambda: "properties" in result,
                    "Response must include 'properties' field",
                ),
                (
                    lambda: isinstance(result.get("properties"), list),
                    "properties must be an array",
                ),
                (
                    lambda: "class_sum" in result,
                    "Response must include 'class_sum' field",
                ),
                (
                    lambda: isinstance(result.get("class_sum"), (int, float)),
                    "class_sum must be numeric",
                ),
                (
                    lambda: "fun_fact" in result,
                    "Response must include 'fun_fact' field",
                ),
                (
                    lambda: isinstance(result.get("fun_fact"), str),
                    "fun_fact must be a string",
                ),
            ]

            for check, message in checks:
                if not check():
                    return False, result, message

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
            return False, None, f"Test failed: {str(e)}"

    def _grade_submission(self, api_url: str) -> tuple[float, list]:
        """Grade submission and return score with helpful messages."""
        total_tests = 0
        passed_tests = 0
        messages = []

        # Test basic JSON response
        success, _, message = self._test_endpoint(api_url, {"number": "123"})
        if not success:
            return 0, [
                "❌ Your API isn't returning valid JSON responses.",
                f"Details: {message}",
                "📝 Make sure your API:",
                "   • Returns valid JSON",
                "   • Sets Content-Type: application/json header",
                "   • Is publicly accessible",
            ]

        # Test structure and format
        total_tests += 6  # One test for each field
        test_case = {"number": "42"}
        success, response, message = self._test_endpoint(api_url, test_case)
        if success:
            passed_tests += 6
        else:
            messages.extend(
                [
                    "❌ Your API response is missing required fields or has incorrect formats.",
                    f"Details: {message}",
                    "📝 Check that your response includes all required fields with correct types:",
                ]
            )

        # Test error handling
        total_tests += 2
        test_case = {"number": "abc", "error_test": True}
        success, _, message = self._test_endpoint(api_url, test_case)
        if success:
            passed_tests += 2
        else:
            messages.extend(
                [
                    "❌ Your error handling needs improvement.",
                    f"Details: {message}",
                    "📝 For invalid input, return:",
                    "   • Status code 400",
                    "   • JSON with number and error fields",
                ]
            )

        score = (passed_tests / total_tests) * 6  # Scale to 6 points

        if not messages:  # All tests passed
            messages = [
                "✅ Your API is working perfectly! It:",
                "   • Returns valid JSON responses",
                "   • Includes all required fields",
                "   • Handles errors correctly",
                "   • Uses proper status codes",
            ]
            if score >= 6:
                messages.append("\n🎉 Congratulations! You've passed Stage 1!")

        return score, messages

    def _get_result_message(
        self, score: float, messages: list, user_id: str, trials: int
    ) -> str:
        """Generate a clear, encouraging feedback message."""
        status = "🎯 Almost there!" if score > 0 else "🚀 Let's get started!"
        if score >= 6:
            status = "🌟 Success!"

        return (
            f"<@{user_id}> Stage 1 Results (Attempt #{trials})\n\n"
            f"{status}\n"
            f"Score: {score:.1f}/6.0\n\n"
            f"{chr(10).join(messages)}\n\n"
            f"{'💡 Fix these issues and try again!' if score < 6 else '🎊 Proceed to the next stage!'}"
        )
