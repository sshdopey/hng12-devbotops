import time
from dataclasses import dataclass
from typing import Optional

import requests
from github import GithubIntegration
from github.Auth import AppAuth

from config import logger


@dataclass
class ValidationResult:
    success: bool
    message: str
    details: Optional[str] = None


class StageTwoGrader:
    def __init__(self, repo_name: str, deployed_url: str):
        with open("hng12-bot.pem", "r") as key_file:
            private_key = key_file.read()

        client_id = "Iv23li3QtBHrdNGU1816"
        self.auth = AppAuth(client_id, private_key)

        owner, repo = repo_name.split("/")
        self.git_integration = GithubIntegration(auth=self.auth)
        self.installation = self.git_integration.get_repo_installation(
            owner, repo
        )
        self.github = self.git_integration.get_github_for_installation(
            self.installation.id
        )
        self.repo = self.github.get_repo(repo_name)
        self.deployed_url = deployed_url
        self.original_main_content = None

    def _save_main_content(self):
        """Save the original main.py content before making changes"""
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
        """Restore the original main.py content"""
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
        """
        Wait for a specific GitHub Actions job (by name) to complete.
        A small initial delay is added to allow GitHub time to create the check run.
        """
        start = time.time()
        while time.time() - start < timeout:
            checks = commit.get_check_runs()
            for check in checks:
                if job_name.lower() in check.name.lower():
                    if check.status.lower() == "completed":
                        logger.info(
                            f"Job '{job_name}' completed with conclusion: {check.conclusion}"
                        )
                        return check.conclusion
            time.sleep(3)
        logger.warning(
            f"Job '{job_name}' did not complete within the timeout period."
        )
        return "timeout"

    def validate_initial_endpoint(self) -> ValidationResult:
        """
        Validate that before any Stage 2 changes, the API:
          - Is served using Nginx.
          - Returns the expected book data on /api/v1/books/1.
          - DOES NOT expose the /stage2 endpoint (should return 404).
        """
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
                    "Server Misconfiguration",
                    f"Expected Nginx, but the Server header indicates '{server}'. Please ensure Nginx is used.",
                )

            books_response = requests.get(
                f"{self.deployed_url}/api/v1/books/1"
            )
            if books_response.status_code != 200:
                return ValidationResult(
                    False,
                    "Books Endpoint Issue",
                    f"Expected status code 200 for /api/v1/books/1, but got {books_response.status_code}.",
                )
            if books_response.json() != expected_book:
                return ValidationResult(
                    False,
                    "Book Data Mismatch",
                    f"Expected: {expected_book}, but received: {books_response.json()}.",
                )

            stage2_response = requests.get(f"{self.deployed_url}/stage2")
            if stage2_response.status_code != 404:
                return ValidationResult(
                    False,
                    "Unexpected /stage2 Availability",
                    (
                        f"The /stage2 endpoint should not be available before merging Stage 2 changes by the bot. "
                        f"Expected a 404 Not Found response but got {stage2_response.status_code}."
                    ),
                )
            return ValidationResult(
                True,
                "Initial endpoints are configured correctly. Note: The /stage2 endpoint shouldn't be available until the bot merges.",
            )
        except requests.RequestException as e:
            return ValidationResult(
                False,
                "API Connection Error",
                f"An error occurred while connecting to the API: {str(e)}",
            )

    def test_bad_pr(self) -> ValidationResult:
        """
        Create a pull request with deliberately bad code to ensure that
        the CI pipeline detects and rejects invalid code.
        """
        branch_name = f"test-bad-pr-{int(time.time())}"
        try:
            source = self.repo.get_branch("main")
            self.repo.create_git_ref(
                f"refs/heads/{branch_name}", source.commit.sha
            )
            file_contents = self.repo.get_contents("main.py", ref=branch_name)
            self.repo.update_file(
                "main.py",
                "Introduce invalid code to test CI",
                "invalid code",
                file_contents.sha,
                branch_name,
            )
            pr = self.repo.create_pull(
                title="Bad PR - Testing CI failure",
                body="",
                head=branch_name,
                base="main",
            )
            time.sleep(3)
            commit = list(pr.get_commits())[-1]
            result = self._wait_for_job(commit, "test")
            if result == "failure":
                return ValidationResult(
                    True,
                    "CI Pipeline Correctly Rejected Invalid Code",
                    "The CI pipeline failed as expected when invalid code was submitted.",
                )
            return ValidationResult(
                False,
                "CI Pipeline Did Not Reject Invalid Code",
                (
                    f"Expected the CI to fail, but the check concluded with '{result}'. "
                    "Ensure that your CI pipeline is properly configured to reject invalid code."
                ),
            )
        except Exception as e:
            return ValidationResult(
                False, "Error Testing CI with Bad Code", str(e)
            )
        finally:
            try:
                self.repo.get_git_ref(f"heads/{branch_name}").delete()
            except Exception:
                pass

    def test_good_pr(self) -> ValidationResult:
        """
        Create a pull request with valid changes that add the /stage2 endpoint.
        Verify that the CI pipeline passes and that the PR can be merged.
        """
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

            file_contents = self.repo.get_contents("main.py", ref=branch_name)
            self.repo.update_file(
                "main.py",
                "Add /stage2 endpoint for Stage 2",
                updated_content,
                file_contents.sha,
                branch_name,
            )
            pr = self.repo.create_pull(
                title="Good PR - Adding Stage 2",
                body="",
                head=branch_name,
                base="main",
            )
            time.sleep(3)
            commit = list(pr.get_commits())[-1]
            result = self._wait_for_job(commit, "test")
            if result == "success":
                pr.merge()
                return ValidationResult(
                    True,
                    (
                        "CI Pipeline Passed and Valid Changes Merged. "
                        "Your code met the project standards and the /stage2 endpoint change is accepted."
                    ),
                )
            return ValidationResult(
                False,
                "CI Pipeline Failed for Valid Code Changes",
                f"Expected CI to pass but received a '{result}' conclusion. Please check your CI configuration.",
            )
        except Exception as e:
            return ValidationResult(
                False, "Error Testing CI with Valid Code", str(e)
            )
        finally:
            try:
                self.repo.get_git_ref(f"heads/{branch_name}").delete()
            except Exception:
                pass

    def check_deployment(self) -> ValidationResult:
        """
        Verify that after merging the PR, the automatic deployment job completes successfully.
        """
        try:
            latest_commit = self.repo.get_commits()[0]
            result = self._wait_for_job(latest_commit, "deploy")
            if result == "success":
                return ValidationResult(
                    True,
                    "Automatic Deployment Completed Successfully.",
                    "Your deployment job finished with a 'success' status.",
                )
            return ValidationResult(
                False,
                "Automatic Deployment Failed",
                f"Deployment job concluded with status: '{result}'. Please investigate your deployment pipeline.",
            )
        except Exception as e:
            return ValidationResult(
                False, "Error Verifying Automatic Deployment", str(e)
            )

    def validate_deployed_endpoint(self) -> ValidationResult:
        """
        After a successful deployment, verify that the /stage2 endpoint is available and returns
        the correct welcome message.
        """
        try:
            time.sleep(3)
            response = requests.get(f"{self.deployed_url}/stage2")
            if response.status_code != 200:
                return ValidationResult(
                    False,
                    "Stage 2 Endpoint Not Available After Deployment",
                    (
                        f"Expected status code 200 for /stage2 after deployment, but received {response.status_code}. "
                        "Ensure that your deployment job properly updates the deployed application."
                    ),
                )

            data = response.json()
            if data.get("message") == "welcome to stage 2":
                return ValidationResult(
                    True,
                    "Stage 2 Endpoint Successfully Deployed and Working.",
                    "Your /stage2 endpoint returned the expected welcome message.",
                )
            return ValidationResult(
                False,
                "Incorrect Response from /stage2 Endpoint",
                f"Expected message 'welcome to stage 2', but got: {data.get('message')}",
            )
        except requests.RequestException as e:
            return ValidationResult(
                False, "Error Connecting to Stage 2 Endpoint", str(e)
            )
