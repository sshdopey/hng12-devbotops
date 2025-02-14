import argparse
import os
from github import GithubIntegration
from github.Auth import AppAuth

def check_bot_installation(repo_name: str, private_key_path: str, client_id: str):
    """
    Checks if the GitHub App is installed on the given repository.
    :param repo_name: Repository name in the format "owner/repo"
    :param private_key_path: Path to the private key file
    :param client_id: GitHub App client ID
    """
    try:
        # Load private key
        with open(private_key_path, "r") as key_file:
            private_key = key_file.read()
        
        # Authenticate with GitHub App
        auth = AppAuth(client_id, private_key)
        git_integration = GithubIntegration(auth=auth)
        
        # Extract owner and repo
        owner, repo = repo_name.split("/")
        
        # Check if the bot is installed
        try:
            installation = git_integration.get_repo_installation(owner, repo)
            print(f"✅ Bot is installed on {repo_name} (Installation ID: {installation.id})")
        except Exception:
            print(f"❌ Bot is NOT installed on {repo_name}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check if a GitHub App is installed on a repository.")
    parser.add_argument("repo", help="GitHub repository in the format 'owner/repo'")
    parser.add_argument("--key", required=True, help="Path to the private key file")
    parser.add_argument("--client", required=True, help="GitHub App client ID")
    
    args = parser.parse_args()
    check_bot_installation(args.repo, args.key, args.client)

