import json
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

    def validate_initial_endpoint(self) -> ValidationResult:
        expected_book = {
            "id": 1,
            "title": "The Hobbit",
            "author": "J.R.R. Tolkien",
            "publication_year": 1937,
            "genre": "Science Fiction",
        }
        try:
            # Check /books/1
            books_response = requests.get(
                f"{self.deployed_url}/api/v1/books/1"
            )
            if books_response.status_code not in [200, 201]:
                return ValidationResult(
                    False,
                    "Books endpoint returned unexpected status",
                    f"Status: {books_response.status_code}",
                )
            if books_response.json() != expected_book:
                return ValidationResult(False, "Unexpected book data")

            # Check /stage2 returns 404
            stage2_response = requests.get(f"{self.deployed_url}/stage2")
            if stage2_response.status_code != 404:
                return ValidationResult(
                    False,
                    "Stage2 endpoint should return 404",
                    f"Status: {stage2_response.status_code}",
                )
            return ValidationResult(True, "Initial endpoints validated")
        except requests.RequestException as e:
            return ValidationResult(False, "Request failed", str(e))

    def check_repo_access(self) -> ValidationResult:
        try:
            # Check invitations
            invitations = self.user.get_invitations()
            for inv in invitations:
                if inv.repository.full_name == self.repo.full_name:
                    self.user.accept_invitation(inv)
                    return ValidationResult(True, "Accepted invitation")

            if not self.repo.has_in_collaborators(self.user.login):
                return ValidationResult(False, "Not a collaborator")
            return ValidationResult(True, "Access confirmed")
        except Exception as e:
            return ValidationResult(False, "Access check failed", str(e))

    def test_bad_pr(self) -> ValidationResult:
        branch_name = f"test-bad-pr-{int(time.time())}"
        try:
            # Create branch and bad PR
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

            # Wait for CI
            start = time.time()
            while time.time() - start < 120:
                pr.update()
                checks = list(pr.get_commits().reversed[0].get_check_runs())
                if len(checks) > 0 and checks[0].conclusion == "failure":
                    return ValidationResult(True, "Bad PR failed CI")
                time.sleep(5)
            return ValidationResult(False, "Bad PR CI timeout")
        except Exception as e:
            return ValidationResult(False, "Bad PR test failed", str(e))
        finally:
            try:
                self.repo.get_git_ref(f"heads/{branch_name}").delete()
            except:
                pass

    def test_good_pr(self) -> ValidationResult:
        branch_name = f"test-good-pr-{int(time.time())}"
        try:
            # Create branch and good PR
            source = self.repo.get_branch("main")
            self.repo.create_git_ref(
                f"refs/heads/{branch_name}", source.commit.sha
            )
            content = self.repo.get_contents(
                "main.py", ref="main"
            ).decoded_content.decode()
            new_route = '\n@app.get("/stage2")\nasync def stage2(): return {"message": "welcome to stage 2"}'
            updated_content = content.replace(
                "if __name__", new_route + "\nif __name__"
            )
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

            # Wait for CI
            start = time.time()
            while time.time() - start < 120:
                pr.update()
                checks = pr.get_commits().reversed[0].get_check_runs()
                if len(checks) > 0 and checks[0].conclusion == "success":
                    pr.merge()
                    return ValidationResult(True, "Good PR passed CI")
                time.sleep(5)
            return ValidationResult(False, "Good PR CI timeout")
        except Exception as e:
            return ValidationResult(False, "Good PR test failed", str(e))
        finally:
            try:
                self.repo.get_git_ref(f"heads/{branch_name}").delete()
            except:
                pass

    def check_deployment(self) -> ValidationResult:
        try:
            time.sleep(10)
            latest_commit = self.repo.get_commits()[0]
            start = time.time()
            while time.time() - start < 120:
                checks = latest_commit.get_check_runs()
                for check in checks:
                    if (
                        check.name == "deploy"
                        and check.conclusion == "success"
                    ):
                        return ValidationResult(True, "Deployment succeeded")
                time.sleep(10)
            return ValidationResult(False, "Deployment timeout")
        except Exception as e:
            return ValidationResult(False, "Deployment check failed", str(e))

    def validate_deployed_endpoint(self) -> ValidationResult:
        try:
            response = requests.get(f"{self.deployed_url}/stage2")
            if response.json().get("message") == "welcome to stage 2":
                return ValidationResult(True, "Stage2 endpoint working")
            return ValidationResult(False, "Invalid stage2 response")
        except requests.RequestException as e:
            return ValidationResult(False, "Stage2 check failed", str(e))


class StageTwo:
    next_emoji = ":three:"
    channels = ["C08AYKQ9AQ7"]
    next_channels = ["C08AYKQ9AQ7"]
    required_score = 8
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
                "title": {"type": "plain_text", "text": "DevOps Stage 2"},
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
            "title": {"type": "plain_text", "text": "DevOps Stage 2"},
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
        try:
            user_id = body["user"]["id"]
            values = body["view"]["state"]["values"]
            deployed_url = values["deployed_url"]["deployed_url"][
                "value"
            ].strip()
            github_url = values["github_url"]["github_url"]["value"].strip()

            # URL uniqueness checks
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

            # Initialize CI tester
            repo_name = "/".join(github_url.split("/")[-2:])
            tester = CITester(Config.GITHUB_TOKEN, repo_name, deployed_url)
            tester._save_main_content()

            # Grade submission
            score, result = self._grade_submission(tester)
            achieved = score >= self.required_score

            # Update spreadsheet
            timestamp = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
            submission = self.sheet.get_row("user_id", user_id)
            trials = int(submission[1]["trials"]) + 1 if submission else 1
            data = {
                "timestamp": timestamp,
                "deployed_url": deployed_url,
                "github_url": github_url,
                "score": str(score),
                "trials": str(trials),
            }
            if submission:
                self.sheet.update(submission[0], data)
            else:
                data["display_name"] = client.users_profile_get(user=user_id)[
                    "profile"
                ]["display_name"]
                data["user_id"] = user_id
                self.sheet.append(data)

            # Send results
            message = "\n".join(result)
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
                    text=f"{message}\n\n🚀 Access granted to next stage!",
                )
            else:
                client.chat_postEphemeral(
                    channel=channel, user=user_id, text=message
                )

        except Exception as e:
            logger.error(f"Submission error: {e}")
            client.chat_postEphemeral(
                channel=channel,
                user=user_id,
                text="❌ Critical error during grading",
            )
        finally:
            try:
                tester._restore_main_content()
            except:
                pass

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
