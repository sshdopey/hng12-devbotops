from datetime import datetime
from typing import Any
import requests
import jwt
import time
from dataclasses import dataclass
from typing import Optional
from github import Github, GithubIntegration


@dataclass
class ValidationResult:
    success: bool
    message: str
    details: Optional[str] = None


class GitHubAppAuth:
    def __init__(self, app_id: int, private_key_path: str = '../hg12-bot.2025-02-13.private-key.pem'):
        self.app_id = app_id
        with open(private_key_path, 'r') as key_file:
            self.private_key = key_file.read()

    def create_jwt(self) -> str:
        now = int(time.time())
        payload = {
            'iat': now,
            'exp': now + (10 * 60),  # JWT valid for 10 minutes
            'iss': self.app_id
        }
        return jwt.encode(payload, self.private_key, algorithm='RS256')

    def get_installation_token(self, installation_id: int) -> str:
        jwt_token = self.create_jwt()
        headers = {
            'Authorization': f'Bearer {jwt_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        response = requests.post(
            f'https://api.github.com/app/installations/{installation_id}/access_tokens',
            headers=headers
        )
        response.raise_for_status()
        return response.json()['token']


class CITester:
    def __init__(self, app_auth: GitHubAppAuth, installation_id: int, repo_name: str, deployed_url: str):
        token = app_auth.get_installation_token(installation_id)
        self.github = Github(token)
        self.repo = self.github.get_repo(repo_name)
        self.deployed_url = deployed_url.rstrip("/")
        self.original_main_content = None

    def _save_main_content(self):
        try:
            contents = self.repo.get_contents("main.py", ref="main")
            self.original_main_content = contents.decoded_content.decode("utf-8")
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
            repo = self.repo.get_contents(".")
            return ValidationResult(
                True,
                "Repository access permissions verified successfully"
            )
        except Exception as e:
            return ValidationResult(
                False,
                "GitHub App needs appropriate permissions to access the repository",
                str(e)
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
            time.sleep(10)  # Wait for deployment to start
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
