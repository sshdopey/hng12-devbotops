from datetime import datetime
from typing import Any
import requests
from github import Github
import time
from dataclasses import dataclass
from typing import Optional

from config import Config, logger, wat_tz
from spreadsheet import Sheet
from utils import check_url_uniqueness, handle_promotion


@dataclass
class ValidationResult:
    success: bool
    message: str
    details: Optional[str] = None


class CITester:
    def __init__(self, token: str, repo_name: str, deployed_url: str):
        self.github = Github(token)
        self.repo = self.github.get_repo(repo_name)
        self.user = self.github.get_user()
        self.deployed_url = deployed_url.rstrip("/")
        self.original_main_content = None

    def _save_main_content(self):
        try:
            contents = self.repo.get_contents("main.py", ref="main")
            self.original_main_content = contents.decoded_content.decode(
                "utf-8"
            )
            logger.info("Saved original main.py content")
        except Exception as e:
            logger.error(f"Failed to save main.py: {e}")
            raise

    def _restore_main_content(self):
        if self.original_main_content:
            try:
                contents = self.repo.get_contents("main.py", ref="main")
                self.repo.update_file(
                    path="main.py",
                    message="Restore original content",
                    content=self.original_main_content,
                    sha=contents.sha,
                    branch="main",
                )
                logger.info("Restored main.py")
            except Exception as e:
                logger.error(f"Failed to restore main.py: {e}")
                raise

    def _wait_for_job(self, commit, job_name: str, timeout: int = 300) -> str:
        """Wait for a specific job to complete and return its conclusion."""
        start = time.time()
        while time.time() - start < timeout:
            checks = commit.get_check_runs()
            for check in checks:
                if check.name == job_name:
                    if check.conclusion in ["success", "failure", "cancelled"]:
                        return check.conclusion
            time.sleep(5)
        return "timeout"

    def validate_initial_endpoint(self) -> ValidationResult:
        expected_book = {
            "id": 1,
            "title": "The Hobbit",
            "author": "J.R.R. Tolkien",
            "publication_year": 1937,
            "genre": "Science Fiction",
        }
        try:
            response = requests.get(f"{self.deployed_url}")
            server = response.headers.get("Server", "").lower()
            if "nginx" not in server:
                return ValidationResult(
                    False,
                    "Application must be served using Nginx",
                    f"Server header indicates {server} is being used instead of nginx",
                )

            books_response = requests.get(
                f"{self.deployed_url}/api/v1/books/1"
            )
            if books_response.status_code != 200:
                return ValidationResult(
                    False,
                    "The books endpoint is not responding correctly - Expected status code 200",
                    f"Got status code: {books_response.status_code}. Please check your API implementation.",
                )
            if books_response.json() != expected_book:
                return ValidationResult(
                    False,
                    "The book data doesn't match the expected format - Please check the book object structure",
                    f"Expected: {expected_book}, Got: {books_response.json()}",
                )

            stage2_response = requests.get(f"{self.deployed_url}/stage2")
            if stage2_response.status_code != 404:
                return ValidationResult(
                    False,
                    "The /stage2 endpoint should return 404 initially as it hasn't been implemented yet",
                    f"Got status code: {stage2_response.status_code}",
                )
            return ValidationResult(
                True,
                "Initial API endpoints are correctly implemented and responding",
            )
        except requests.RequestException as e:
            return ValidationResult(
                False, "Failed to connect to your API endpoints", str(e)
            )

    def check_repo_access(self) -> ValidationResult:
        try:
            invitations = self.user.get_invitations()
            for inv in invitations:
                if inv.repository.full_name == self.repo.full_name:
                    self.user.accept_invitation(inv)
                    return ValidationResult(
                        True,
                        "Successfully accepted repository collaboration invitation",
                    )

            if not self.repo.has_in_collaborators(self.user.login):
                return ValidationResult(
                    False,
                    "You need to add hng12-devbotops as a collaborator to your repository",
                    "Please go to repository settings -> Collaborators -> Add people",
                )
            return ValidationResult(
                True, "Repository access permissions verified successfully"
            )
        except Exception as e:
            return ValidationResult(
                False, "Failed to verify repository access permissions", str(e)
            )

    def test_bad_pr(self) -> ValidationResult:
        branch_name = f"test-bad-pr-{int(time.time())}"
        try:
            source = self.repo.get_branch("main")
            self.repo.create_git_ref(
                f"refs/heads/{branch_name}", source.commit.sha
            )
            self.repo.update_file(
                "main.py",
                "Bad commit",
                "invalid code",
                self.repo.get_contents("main.py", ref=branch_name).sha,
                branch_name,
            )
            pr = self.repo.create_pull(
                title="Bad PR", body="", head=branch_name, base="main"
            )
            commit = pr.get_commits().reversed[0]
            result = self._wait_for_job(commit, "test")
            return ValidationResult(
                result == "failure",
                f"CI pipeline {'correctly rejected' if result == 'failure' else 'failed to reject'} invalid code",
                "Your CI should fail when invalid code is submitted",
            )
        except Exception as e:
            return ValidationResult(
                False, "Failed to test CI pipeline with invalid code", str(e)
            )
        finally:
            try:
                self.repo.get_git_ref(f"heads/{branch_name}").delete()
            except:
                pass

    def test_good_pr(self) -> ValidationResult:
        branch_name = f"test-good-pr-{int(time.time())}"
        try:
            source = self.repo.get_branch("main")
            self.repo.create_git_ref(
                f"refs/heads/{branch_name}", source.commit.sha
            )
            content = self.repo.get_contents(
                "main.py", ref="main"
            ).decoded_content.decode()
            new_route = """
@app.get("/stage2")
async def stage2():
    return {"message": "welcome to stage 2"}
"""
            updated_content = content + new_route

            self.repo.update_file(
                "main.py",
                "Good commit",
                updated_content,
                self.repo.get_contents("main.py", ref=branch_name).sha,
                branch_name,
            )
            pr = self.repo.create_pull(
                title="Good PR", body="", head=branch_name, base="main"
            )
            commit = pr.get_commits().reversed[0]
            result = self._wait_for_job(commit, "test")
            if result == "success":
                pr.merge()
                return ValidationResult(
                    True,
                    "Valid code changes passed CI checks and were merged successfully",
                )
            return ValidationResult(
                False,
                "CI pipeline failed for valid code changes",
                f"Expected CI success but got: {result}",
            )
        except Exception as e:
            return ValidationResult(
                False, "Failed to test CI pipeline with valid code", str(e)
            )
        finally:
            try:
                self.repo.get_git_ref(f"heads/{branch_name}").delete()
            except:
                pass

    def check_deployment(self) -> ValidationResult:
        try:
            time.sleep(10)
            latest_commit = self.repo.get_commits()[0]
            result = self._wait_for_job(latest_commit, "deploy")
            return ValidationResult(
                result == "success",
                f"Automatic deployment {'completed successfully' if result == 'success' else 'failed'}",
                f"Deployment status: {result}. Your changes should be automatically deployed when merged.",
            )
        except Exception as e:
            return ValidationResult(
                False, "Failed to verify automatic deployment", str(e)
            )

    def validate_deployed_endpoint(self) -> ValidationResult:
        try:
            response = requests.get(f"{self.deployed_url}/stage2")
            if response.status_code != 200:
                return ValidationResult(
                    False,
                    "Stage2 endpoint not found - deployment did not update",
                    f"Status code: {response.status_code}",
                )

            data = response.json()
            if data.get("message") == "welcome to stage 2":
                return ValidationResult(
                    True, "Stage2 endpoint successfully deployed and working"
                )
            return ValidationResult(
                False,
                "Stage2 endpoint found but returned incorrect response",
                f"Got: {data}",
            )
        except requests.RequestException as e:
            return ValidationResult(
                False, "Failed to check Stage2 endpoint", str(e)
            )


class StageTwoBackend:
    next_emoji = ":three:"
    channels = ["C08B6GUP4PQ"]
    next_channels = ["C08DA2RDPRN", "C08CR90L1NE"]
    required_score = 9
    max_trials = 3
    deadline = wat_tz.localize(
        datetime.strptime("2025-02-14 23:59:59", "%Y-%m-%d %H:%M:%S")
    )
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

    def submission_view(self, channel: str) -> dict:
        """Returns the Slack modal view for Stage 2 submission."""
        return {
            "type": "modal",
            "title": {"type": "plain_text", "text": "Backend Stage 2"},
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "🛠 The bot is currently under maintenance. Please try again later.",
                    },
                }
            ],
            "close": {"type": "plain_text", "text": "Close"},
        }
        now = datetime.now(wat_tz)
        if now > self.deadline:
            return {
                "type": "modal",
                "title": {"type": "plain_text", "text": "Backend Stage 2"},
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
            "title": {"type": "plain_text", "text": "Backend Stage 2"},
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

    def submit(self, channel: str, body: dict, client: Any) -> None:
        user_id = body["user"]["id"]
        data = {}
        try:
            submission = self.sheet.get_row("user_id", user_id)
            if submission:
                trials = int(submission[1].get("trials", "0"))
                score = submission[1].get("score", "0")
                if trials >= self.max_trials:
                    client.chat_postEphemeral(
                        channel=channel,
                        user=user_id,
                        text="❌ You have used all your attempts (3/3).",
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

            repo_name = "/".join(github_url.split("/")[-2:])
            tester = CITester(Config.GITHUB_TOKEN, repo_name, deployed_url)
            tester._save_main_content()

            score, result = self._grade_submission(tester)
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
            client.chat_postEphemeral(
                channel=channel,
                user=user_id,
                text="❌ Critical error during grading",
            )
        finally:
            try:
                tester._restore_main_content()
            except Exception as restore_error:
                logger.error(
                    f"Failed to restore main content: {restore_error}"
                )

    def _grade_submission(self, tester: CITester) -> tuple[float, list]:
        score = 0.0
        result = []
        checks = [
            (tester.validate_initial_endpoint, 2),
            (tester.check_repo_access, 1),
            (tester.test_bad_pr, 1),
            (tester.test_good_pr, 2),
            (tester.check_deployment, 2),
            (tester.validate_deployed_endpoint, 1),
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
