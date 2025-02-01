from datetime import datetime
from typing import Any
import requests
from requests.exceptions import RequestException
import json

from config import Config, logger
from spreadsheet import Sheet
from utils import handle_promotion


class StageOne:
    """Handles Stage 1 submissions and promotions for the DevOps program."""

    emoji = ":one:"
    channels = ["C08AHHWBTK8"]
    next_channels = ["C08AHHWBTK8", "C08B3UKM0QN"]
    required_score = 6

    test_cases = [
        {"number": "371", "expected_properties": ["armstrong", "odd"]},
        {"number": "6", "expected_properties": ["perfect", "even"]},
        {"number": "17", "expected_properties": ["prime", "odd"]},
        {"number": "abc", "error": True},
        {"number": "-5", "expected_properties": ["odd"]},
        {"number": "0", "expected_properties": ["even"]},
    ]

    sheet = Sheet(
        "1u5-JU71GkCOlYf7nAWdJWxoJpzNcDiKlqfB4aZDmDiAg",
        {
            "A": "timestamp",
            "B": "username",
            "C": "user_id",
            "D": "trials",
            "E": "api_url",
            "F": "github_url",
            "G": "score",
            "H": "promoted",
        },
    )

    def submission_view(self, channel: str) -> dict:
        """Returns the Slack modal view for Stage 1 submission."""
        return {
            "type": "modal",
            "title": {"type": "plain_text", "text": "DevOps Stage 1"},
            "blocks": [
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

            # Check if user has already been promoted
            submission = self.sheet.get_row("user_id", user_id)
            if submission and submission[1].get("promoted") == "1":
                client.chat_postEphemeral(
                    channel=channel,
                    user=user_id,
                    text="🎉 You have already passed Stage 1! No need to submit again.",
                )
                return

            # Validate URL uniqueness
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

            # Grade submission
            score, result = self._grade_submission(api_url)
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
                        "api_url": api_url,
                        "github_url": github_url,
                        "score": str(score),
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
                        "api_url": api_url,
                        "github_url": github_url,
                        "score": str(score),
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

    def _test_endpoint(
        self, url: str, test_case: dict
    ) -> tuple[bool, dict, str]:
        """Test a single endpoint with a test case."""
        try:
            test_url = f"{url.rstrip('/')}?number={test_case['number']}"
            response = requests.get(test_url, timeout=10)

            if not response.headers.get("Content-Type", "").startswith(
                "application/json"
            ):
                return False, None, "Response is not in JSON format"

            result = response.json()

            if "error" in test_case:
                if response.status_code != 400 or not result.get("error"):
                    return (
                        False,
                        result,
                        "Expected error response for invalid input",
                    )
            else:
                if response.status_code != 200:
                    return (
                        False,
                        result,
                        f"Expected 200 status code, got {response.status_code}",
                    )

                if not isinstance(result.get("properties"), list):
                    return False, result, "Properties should be an array"

                # Check if all expected properties are present
                missing_props = [
                    prop
                    for prop in test_case["expected_properties"]
                    if prop not in result["properties"]
                ]
                if missing_props:
                    return (
                        False,
                        result,
                        f"Missing properties: {', '.join(missing_props)}",
                    )

            return True, result, "Success"

        except requests.exceptions.RequestException as e:
            return False, None, f"Request failed: {str(e)}"
        except json.JSONDecodeError:
            return False, None, "Invalid JSON response"
        except Exception as e:
            return False, None, f"Test failed: {str(e)}"

    def _grade_submission(self, api_url: str) -> tuple[int, dict]:
        """Grade submission based on test cases and requirements."""
        score = 0
        result = {
            "query_params": {"score": 0, "max": 2, "details": []},
            "basic_props": {"score": 0, "max": 3, "details": []},
            "special_props": {"score": 0, "max": 3, "details": []},
            "edge_cases": {"score": 0, "max": 2, "details": []},
            "test_results": [],
        }

        for test_case in self.test_cases:
            success, response, message = self._test_endpoint(
                api_url, test_case
            )
            result["test_results"].append(
                {
                    "test_case": test_case,
                    "success": success,
                    "response": response,
                    "message": message,
                }
            )

            if success:
                # Query Parameter Handling (2 points)
                if test_case.get("number") == "abc":
                    result["query_params"]["score"] += 2
                    result["query_params"]["details"].append(
                        "✅ Properly handles invalid input"
                    )

                # Basic Properties (3 points)
                if "expected_properties" in test_case:
                    if "prime" in test_case["expected_properties"] and (
                        "prime" in response["properties"]
                    ):
                        result["basic_props"]["score"] += 1
                        result["basic_props"]["details"].append(
                            "✅ Correct prime check"
                        )
                    if "perfect" in test_case["expected_properties"] and (
                        "perfect" in response["properties"]
                    ):
                        result["basic_props"]["score"] += 1
                        result["basic_props"]["details"].append(
                            "✅ Correct perfect number check"
                        )
                    if any(
                        prop in ["odd", "even"]
                        for prop in test_case["expected_properties"]
                    ):
                        result["basic_props"]["score"] += 1
                        result["basic_props"]["details"].append(
                            "✅ Correct odd/even classification"
                        )

                # Special Properties (3 points)
                if (
                    "armstrong" in test_case.get("expected_properties", [])
                    and "armstrong" in response["properties"]
                ):
                    result["special_props"]["score"] += 1
                    result["special_props"]["details"].append(
                        "✅ Correct Armstrong number check"
                    )
                if "class_sum" in response:
                    result["special_props"]["score"] += 1
                    result["special_props"]["details"].append(
                        "✅ Implements digit sum calculation"
                    )
                if isinstance(response.get("properties"), list):
                    result["special_props"]["score"] += 1
                    result["special_props"]["details"].append(
                        "✅ Properties returned as array"
                    )

                # Edge Cases (2 points)
                if (
                    test_case["number"].startswith("-")
                    or test_case["number"] == "0"
                ):
                    result["edge_cases"]["score"] += 1
                    result["edge_cases"]["details"].append(
                        "✅ Handles edge cases correctly"
                    )

        # Calculate total score
        score = sum(
            category["score"]
            for category in result.values()
            if isinstance(category, dict) and "score" in category
        )

        return score, result

    def _get_result_message(
        self, result: dict, score: int, user_id: str, trials: int
    ) -> str:
        """Generate detailed submission result message."""
        message = [
            f"<@{user_id}> Stage 1 Results (Attempt #{trials}):\n",
            "📋 Grading Summary:",
            f"Query Parameter Handling: {result['query_params']['score']}/{result['query_params']['max']} points",
            f"Basic Properties: {result['basic_props']['score']}/{result['basic_props']['max']} points",
            f"Special Properties: {result['special_props']['score']}/{result['special_props']['max']} points",
            f"Edge Cases: {result['edge_cases']['score']}/{result['edge_cases']['max']} points",
            f"\nTotal Score: {score}/10 points (Required: {self.required_score})\n",
        ]

        # Add details for each category
        for category in [
            "query_params",
            "basic_props",
            "special_props",
            "edge_cases",
        ]:
            if result[category]["details"]:
                message.extend(result[category]["details"])

        # Add test case results
        message.append("\n🧪 Test Cases:")
        for test_result in result["test_results"]:
            status = "✅" if test_result["success"] else "❌"
            message.append(
                f"{status} Test case {test_result['test_case']['number']}: {test_result['message']}"
            )

        if score < self.required_score:
            message.append("\n📝 Areas for Improvement:")
            if result["query_params"]["score"] < result["query_params"]["max"]:
                message.append("• Improve input validation and error handling")
            if result["basic_props"]["score"] < result["basic_props"]["max"]:
                message.append(
                    "• Review implementation of basic number properties"
                )
            if (
                result["special_props"]["score"]
                < result["special_props"]["max"]
            ):
                message.append("• Enhance special number properties detection")
            if result["edge_cases"]["score"] < result["edge_cases"]["max"]:
                message.append("• Add better handling of edge cases")
            message.append(
                "\n💡 Review the requirements and resubmit when ready!"
            )
        else:
            message.append(
                f"\n🎉 Congratulations! You've completed Stage 1 in {trials} {'attempt' if trials == 1 else 'attempts'}!"
            )

        return "\n".join(message)
