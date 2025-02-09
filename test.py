from github import Github
import time
import requests
from typing import Optional
import logging
from dataclasses import dataclass

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


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
        """Save original main.py content for restoration."""
        try:
            contents = self.repo.get_contents("main.py", ref="main")
            self.original_main_content = contents.decoded_content.decode(
                "utf-8"
            )
            logger.info("Successfully saved original main.py content")
        except Exception as e:
            logger.error(f"Failed to save original main.py content: {e}")
            raise

    def _restore_main_content(self):
        """Restore main.py to its original state."""
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
                logger.info("Successfully restored main.py to original state")
            except Exception as e:
                logger.error(f"Failed to restore main.py: {e}")
                raise

    def validate_initial_endpoint(self) -> ValidationResult:
        """Check if the initial /books/1 endpoint returns expected data and /stage2 returns 404."""
        expected_book = {
            "id": 1,
            "title": "The Hobbit",
            "author": "J.R.R. Tolkien",
            "publication_year": 1937,
            "genre": "Science Fiction",
        }

        try:
            # Check /books/1 endpoint
            books_response = requests.get(
                f"{self.deployed_url}/api/v1/books/1"
            )
            if books_response.status_code != 201:
                logger.warning(
                    f"Books endpoint returned unexpected status: {books_response.status_code}"
                )
                return ValidationResult(
                    False,
                    "Books endpoint not returning 200",
                    f"Status: {books_response.status_code}",
                )

            book_data = books_response.json()
            if book_data != expected_book:
                logger.warning("Books endpoint returned unexpected data")
                return ValidationResult(
                    False, "Unexpected book data", f"Got: {book_data}"
                )

            # Check /stage2 endpoint should return 404
            stage2_response = requests.get(f"{self.deployed_url}/stage2")
            if stage2_response.status_code != 404:
                logger.warning(
                    f"Stage2 endpoint returned unexpected status: {stage2_response.status_code}"
                )
                return ValidationResult(
                    False,
                    "Stage2 endpoint should return 404",
                    f"Status: {stage2_response.status_code}",
                )

            logger.info("Initial endpoint validation successful")
            return ValidationResult(
                True, "Initial endpoints validated successfully"
            )

        except requests.RequestException as e:
            logger.error(f"Error checking endpoints: {e}")
            return ValidationResult(False, "Failed to check endpoints", str(e))

    def check_repo_access(self) -> ValidationResult:
        """Check and handle repository access."""
        logger.info(f"Checking access to repository: {self.repo.full_name}")
        try:
            # Check for pending invitations
            invitations = self.user.get_invitations()
            for invitation in invitations:
                if invitation.repository.full_name == self.repo.full_name:
                    self.user.accept_invitation(invitation)
                    logger.info(
                        f"Accepted invitation to {self.repo.full_name}"
                    )
                    return ValidationResult(
                        True, "Accepted repository invitation"
                    )

            # Verify collaborator status
            is_collaborator = self.repo.has_in_collaborators(self.user.login)
            if not is_collaborator:
                logger.warning("Access denied: Not a collaborator")
                return ValidationResult(
                    False, "Not a collaborator on repository"
                )

            logger.info("Repository access confirmed")
            return ValidationResult(True, "Has repository access")

        except Exception as e:
            logger.error(f"Failed to check repository access: {e}")
            return ValidationResult(
                False, "Failed to verify repository access", str(e)
            )

    def test_bad_pr(self) -> ValidationResult:
        """Submit and test a PR that should fail CI."""
        branch_name = f"test-bad-pr-{int(time.time())}"
        logger.info(f"Creating bad PR on branch: {branch_name}")

        try:
            if not self.create_branch(branch_name):
                return ValidationResult(
                    False, "Failed to create branch for bad PR"
                )

            bad_code = "well, I am going to fail"
            if not self.update_file("main.py", bad_code, branch_name):
                self.cleanup(branch_name)
                return ValidationResult(
                    False, "Failed to update file for bad PR"
                )

            pr = self.create_pr(
                "Bad PR", "This PR should fail CI", branch_name
            )
            if not pr:
                self.cleanup(branch_name)
                return ValidationResult(False, "Failed to create bad PR")

            result = self.wait_for_ci(pr)
            self.cleanup(branch_name)

            if result == "failure":
                logger.info("Bad PR failed CI as expected")
                return ValidationResult(True, "Bad PR failed CI as expected")
            else:
                logger.warning(f"Bad PR unexpected CI result: {result}")
                return ValidationResult(
                    False,
                    "Bad PR did not fail as expected",
                    f"CI Result: {result}",
                )

        except Exception as e:
            logger.error(f"Error in bad PR test: {e}")
            self.cleanup(branch_name)
            return ValidationResult(False, "Error in bad PR test", str(e))

    def test_good_pr(self) -> ValidationResult:
        """Submit and test a PR that should pass CI."""
        branch_name = f"test-good-pr-{int(time.time())}"
        logger.info(f"Creating good PR on branch: {branch_name}")

        try:
            if not self.create_branch(branch_name):
                return ValidationResult(
                    False, "Failed to create branch for good PR"
                )

            contents = self.repo.get_contents("main.py", ref="main")
            current_code = contents.decoded_content.decode("utf-8")

            new_route = '''

@app.get("/stage2")
async def stage2():
    """Welcome endpoint for stage 2."""
    return {"message": "welcome to stage 2"}
'''
            if_pos = current_code.rfind("if __name__")
            updated_code = (
                current_code[:if_pos] + new_route + current_code[if_pos:]
            )

            if not self.update_file("main.py", updated_code, branch_name):
                self.cleanup(branch_name)
                return ValidationResult(
                    False, "Failed to update file for good PR"
                )

            pr = self.create_pr(
                "Add stage2 endpoint",
                "Added new /stage2 endpoint that returns a welcome message",
                branch_name,
            )
            if not pr:
                self.cleanup(branch_name)
                return ValidationResult(False, "Failed to create good PR")

            result = self.wait_for_ci(pr)

            if result != "success":
                logger.warning(f"Good PR unexpected CI result: {result}")
                self.cleanup(branch_name)
                return ValidationResult(
                    False, "Good PR did not pass CI", f"CI Result: {result}"
                )
            else:
                pr.merge(merge_method="squash")

            logger.info("Good PR passed CI successfully")
            return ValidationResult(True, "Good PR passed CI successfully")

        except Exception as e:
            logger.error(f"Error in good PR test: {e}")
            self.cleanup(branch_name)
            return ValidationResult(False, "Error in good PR test", str(e))

    def check_deployment(self) -> ValidationResult:
        """Check if deployment job runs and succeeds."""
        logger.info("Checking deployment job")
        try:
            time.sleep(10)

            # Get latest commit
            commits = self.repo.get_commits()
            latest_commit = commits[0]
            logger.info(f"Latest commit SHA: {latest_commit.sha}")

            start_time = time.time()
            while True:
                checks = latest_commit.get_check_runs()
                if checks.totalCount > 0:
                    for check in checks:
                        if check.name == "deploy":
                            if check.status == "completed":
                                logger.info(
                                    f"Deployment completed with conclusion: {check.conclusion}"
                                )
                                if check.conclusion == "success":
                                    return ValidationResult(
                                        True, "Deployment successful"
                                    )
                                else:
                                    return ValidationResult(
                                        False,
                                        "Deployment failed",
                                        check.conclusion,
                                    )
                            logger.debug("Deployment still running...")

                if time.time() - start_time > 120:
                    logger.warning("Deployment check timed out")
                    return ValidationResult(
                        False, "Deployment check timed out"
                    )

                time.sleep(10)

        except Exception as e:
            logger.error(f"Error checking deployment: {e}")
            return ValidationResult(False, "Error checking deployment", str(e))

    def validate_deployed_endpoint(self) -> ValidationResult:
        """Validate the newly deployed /stage2 endpoint."""
        logger.info("Checking deployed /stage2 endpoint")
        try:
            time.sleep(5)
            response = requests.get(f"{self.deployed_url}/stage2")

            if response.status_code == 200:
                data = response.json()
                if data.get("message") == "welcome to stage 2":
                    logger.info("Stage2 endpoint validation successful")
                    return ValidationResult(
                        True, "Stage2 endpoint working correctly"
                    )
                else:
                    logger.warning("Stage2 endpoint returned unexpected data")
                    return ValidationResult(
                        False,
                        "Unexpected response from stage2 endpoint",
                        str(data),
                    )
            else:
                logger.warning(
                    f"Stage2 endpoint returned status {response.status_code}"
                )
                return ValidationResult(
                    False,
                    "Stage2 endpoint not accessible",
                    f"Status: {response.status_code}",
                )

        except requests.RequestException as e:
            logger.error(f"Error checking stage2 endpoint: {e}")
            return ValidationResult(
                False, "Failed to check stage2 endpoint", str(e)
            )

    def create_branch(
        self, branch_name: str, from_branch: str = "main"
    ) -> bool:
        try:
            source = self.repo.get_branch(from_branch)
            self.repo.create_git_ref(
                f"refs/heads/{branch_name}", source.commit.sha
            )
            logger.info(f"Created branch: {branch_name}")
            return True
        except Exception as e:
            logger.error(f"Branch creation failed: {e}")
            return False

    def update_file(self, filename: str, content: str, branch: str) -> bool:
        try:
            try:
                contents = self.repo.get_contents(filename, ref=branch)
                self.repo.update_file(
                    path=filename,
                    message=f"Update {filename}",
                    content=content,
                    sha=contents.sha,
                    branch=branch,
                )
                logger.info(f"Updated file: {filename} on branch: {branch}")
            except Exception:
                self.repo.create_file(
                    path=filename,
                    message=f"Create {filename}",
                    content=content,
                    branch=branch,
                )
                logger.info(f"Created file: {filename} on branch: {branch}")
            return True
        except Exception as e:
            logger.error(f"File update failed: {e}")
            return False

    def create_pr(self, title: str, body: str, head: str) -> Optional[object]:
        try:
            pr = self.repo.create_pull(
                title=title, body=body, head=head, base="main"
            )
            logger.info(f"Created PR: {title}")
            return pr
        except Exception as e:
            logger.error(f"PR creation failed: {e}")
            return None

    def wait_for_ci(self, pr, timeout: int = 120) -> str:
        logger.info(f"Waiting for CI on PR #{pr.number}")
        start_time = time.time()
        while True:
            pr.update()
            checks = pr.get_commits().reversed[0].get_check_runs()
            if checks.totalCount > 0:
                for check in checks:
                    if check.name == "test":
                        if check.status == "completed":
                            logger.info(
                                f"CI completed with conclusion: {check.conclusion}"
                            )
                            return check.conclusion
                        logger.debug("CI still running...")
            if time.time() - start_time > timeout:
                logger.warning("CI timed out")
                return "timeout"
            time.sleep(5)

    def cleanup(self, branch_name: str):
        try:
            ref = self.repo.get_git_ref(f"heads/{branch_name}")
            ref.delete()
            logger.info(f"Cleaned up branch: {branch_name}")
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")


def main():
    GITHUB_TOKEN = "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"
    REPO_URL = "https://github.com/ThePrimeJnr/fastapi-book-project"
    DEPLOYED_URL = "https://hng12.theprimejnr.com"
    REPO_NAME = "/".join(REPO_URL.split("/")[-2:])

    logger.info("Starting CI test suite")
    tester = CITester(GITHUB_TOKEN, REPO_NAME, DEPLOYED_URL)

    try:
        # Save original state
        tester._save_main_content()

        # Initial endpoint check
        result = tester.validate_initial_endpoint()
        if not result.success:
            logger.error(f"Initial endpoint check failed: {result.message}")
            return

        # Repository access check
        result = tester.check_repo_access()
        if not result.success:
            logger.error(f"Repository access check failed: {result.message}")
            return

        # Bad PR test
        result = tester.test_bad_pr()
        if not result.success:
            logger.error(f"Bad PR test failed: {result.message}")
            return

        # Good PR test
        result = tester.test_good_pr()
        if not result.success:
            logger.error(f"Good PR test failed: {result.message}")
            return

        # Deployment check
        result = tester.check_deployment()
        if not result.success:
            logger.error(f"Deployment check failed: {result.message}")
            return

        # Final endpoint validation
        result = tester.validate_deployed_endpoint()
        if not result.success:
            logger.error(
                f"Deployed endpoint validation failed: {result.message}"
            )
            return

        logger.info("All tests completed successfully!")

    except Exception as e:
        logger.error(f"Test suite failed: {e}")
    finally:
        # Always restore original state
        try:
            tester._restore_main_content()
            logger.info("Successfully restored repository to original state")
        except Exception as e:
            logger.error(f"Failed to restore repository state: {e}")


if __name__ == "__main__":
    main()
