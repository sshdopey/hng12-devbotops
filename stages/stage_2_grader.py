import requests
import jwt
import time
from dataclasses import dataclass
from typing import Optional
from github import Github
import logging


@dataclass
class ValidationResult:
    success: bool
    message: str
    details: Optional[str] = None


class StageTwoGrader:
    def __init__(self, repo_name: str, deployed_url: str):
        with open("../hng12-bot.pem", "r") as key_file:
            self.private_key = key_file.read()

        jwt_token = jwt.encode(
            {
                "iat": int(time.time()),
                "exp": int(time.time()) + (10 * 60),
                "iss": 1144219,
            },
            self.private_key,
            algorithm="RS256",
        )

        self.github = Github(jwt_token)
        self.repo = self.github.get_repo(repo_name)
        self.deployed_url = deployed_url.rstrip("/")
        self.original_main_content = None

    def _save_main_content(self):
        """Save the original main.py content before making changes"""
        try:
            contents = self.repo.get_contents("main.py", ref="main")
            self.original_main_content = contents.decoded_content.decode(
                "utf-8"
            )
            logging.info("Saved original main.py content")
        except Exception as e:
            logging.error(f"Failed to save main.py: {e}")
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
                logging.info("Restored main.py")
            except Exception as e:
                logging.error(f"Failed to restore main.py: {e}")
                raise

    def _wait_for_job(self, commit, job_name: str, timeout: int = 300) -> str:
        """Wait for a specific GitHub Actions job to complete"""
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
        """Validate the initial API endpoint setup"""
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
                    "The books endpoint is not responding correctly",
                    f"Got status code: {books_response.status_code}",
                )
            if books_response.json() != expected_book:
                return ValidationResult(
                    False,
                    "The book data doesn't match the expected format",
                    f"Expected: {expected_book}, Got: {books_response.json()}",
                )

            stage2_response = requests.get(f"{self.deployed_url}/stage2")
            if stage2_response.status_code != 404:
                return ValidationResult(
                    False,
                    "The /stage2 endpoint should return 404 initially",
                    f"Got status code: {stage2_response.status_code}",
                )
            return ValidationResult(
                True, "Initial API endpoints are correctly implemented"
            )
        except requests.RequestException as e:
            return ValidationResult(
                False, "Failed to connect to API endpoints", str(e)
            )

    def check_repo_access(self) -> ValidationResult:
        """Verify GitHub App has necessary repository access"""
        try:
            installation = self.repo.get_installation()
            if not installation:
                return ValidationResult(
                    False,
                    "GitHub App is not installed on this repository",
                    "Please install the GitHub App on your repository",
                )

            self.repo.get_contents(".")
            return ValidationResult(
                True, "GitHub App access verified successfully"
            )
        except Exception as e:
            return ValidationResult(
                False, "Failed to verify repository access", str(e)
            )

    def test_bad_pr(self) -> ValidationResult:
        """Test CI pipeline with invalid code"""
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
        """Test CI pipeline with valid code changes"""
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
        """Verify automatic deployment after merge"""
        try:
            time.sleep(10)
            latest_commit = self.repo.get_commits()[0]
            result = self._wait_for_job(latest_commit, "deploy")
            return ValidationResult(
                result == "success",
                f"Automatic deployment {'completed successfully' if result == 'success' else 'failed'}",
                f"Deployment status: {result}",
            )
        except Exception as e:
            return ValidationResult(
                False, "Failed to verify automatic deployment", str(e)
            )

    def validate_deployed_endpoint(self) -> ValidationResult:
        """Validate the newly deployed stage2 endpoint"""
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
