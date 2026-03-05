import os
import os.path

from git import Repo, GitCommandError
import requests
from urllib.parse import urlparse
from github import Github
from urllib.parse import urlparse
import logging
from mhc.config import *

logging.basicConfig(level=logging.DEBUG)



def clone_and_checkout_commit(repo_url, repository_directory, commit_hash):
    """Clone a GitHub repository and checkout a specific commit hash.
       Raises an exception if cloning or checking out fails.
    """
    try:
        if os.path.exists(repository_directory):
            # Check for a stale lock file and remove it
            lock_file = os.path.join(repository_directory, ".git", "index.lock")
            if os.path.exists(lock_file):
                print(f"Removing stale lock file at {lock_file}")
                os.remove(lock_file)
            print(f"Opening existing repo at {repository_directory}")
            repo = Repo(repository_directory)
        else:
            print(f"Cloning {repo_url}...")
            repo = Repo.clone_from(repo_url, repository_directory)

            # 1. Fetch to ensure we have the latest metadata
        print(f"Fetching updates...")
        repo.git.fetch('--all')

        # 2. Force checkout to bypass dirty state or index issues
        print(f"Checking out commit {commit_hash}...")
        repo.git.checkout(commit_hash, force=True)

        # Verify checkout success
        current_commit = repo.head.object.hexsha
        if commit_hash != current_commit:
            raise Exception(
                f"Failed to checkout the correct commit. Expected: {commit_hash}, Got: {current_commit}")

        print(f"Successfully checked out commit: {commit_hash}")
        return current_commit

    except GitCommandError as e:
        raise Exception(f"Git command failed: {repository_directory} {str(e)}")
    except Exception as e:
        raise Exception(f"Error: {str(e)}")


def get_all_commit_info(repo_path, branch="HEAD"):
    repo = Repo(repo_path)
    commits = []

    for c in repo.iter_commits(branch):
        commits.append({
            "hash": c.hexsha,
            "author": c.author.name,
            "email": c.author.email,
            "date": c.committed_datetime,
            "message": c.message.strip(),
            "parents": [p.hexsha for p in c.parents],
        })

    return commits



def parse_github_url(url):
    parts = urlparse(url).path.strip("/").split("/")
    return parts[0], parts[1]


def get_repo_metadata(github_url):
    g = Github(GITHUB_API_KEY, per_page=10_000)
    owner, project = parse_github_url(github_url)

    repo = g.get_repo(f"{owner}/{project}")

    default_branch = repo.default_branch

    # ---------- Basic stats ----------
    stars = repo.stargazers_count
    forks = repo.forks_count
    watchers = repo.subscribers_count

    # ---------- Contributors ----------
    contributors = repo.get_contributors(anon=True).totalCount

    # # ---------- Commits ----------
    commits = repo.get_commits(sha=default_branch)
    total_commits = commits.totalCount

    latest_commit = commits[0]
    first_commit = commits[total_commits - 1]

    latest_hash = latest_commit.sha
    latest_date = latest_commit.commit.committer.date

    first_hash = first_commit.sha
    first_date = first_commit.commit.committer.date

    return {
        "stars": stars,
        "forks": forks,
        "watchers": watchers,
        "contributors": contributors,
        "commits": total_commits,
        "created_at": first_date.isoformat(),
        "updated_at": latest_date.isoformat(),
        "created_hash": first_hash,
        "updated_hash": latest_hash,
        "branch": default_branch
    }