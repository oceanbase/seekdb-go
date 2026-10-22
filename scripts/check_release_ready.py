#!/usr/bin/env python3
"""Require a successful public-install workflow for the exact main commit."""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


def repository(remote: str) -> str:
    if remote.startswith("git@github.com:"):
        path = remote.removeprefix("git@github.com:")
    else:
        url = urllib.parse.urlparse(remote)
        if url.scheme not in ("https", "ssh") or url.hostname != "github.com":
            raise ValueError("release remote must be a github.com repository")
        path = url.path.lstrip("/")
    path = path.rstrip("/").removesuffix(".git")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", path):
        raise ValueError("invalid GitHub repository path")
    return path


def check(remote: str, commit: str) -> str:
    repo = repository(remote)
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("release commit must be a full SHA")
    return "\n".join(check_workflow(repo, commit, workflow) for workflow in
                     ("test.yml", "release-validation.yml"))


def check_workflow(repo: str, commit: str, workflow: str) -> str:
    query = urllib.parse.urlencode({"event": "push", "branch": "main",
                                    "head_sha": commit, "per_page": 20})
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow}/runs?{query}"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "seekdb-go-release",
               "X-GitHub-Api-Version": "2022-11-28"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        runs = json.load(response)["workflow_runs"]
    matching = [run for run in runs if run["head_sha"] == commit
                and run["head_branch"] == "main" and run["event"] == "push"]
    latest = max(matching, key=lambda run: run["id"], default=None)
    if not latest or latest["status"] != "completed" or latest["conclusion"] != "success":
        raise ValueError(f"{workflow} on main must pass for {commit} before tagging. "
                         f"See https://github.com/{repo}/actions/workflows/{workflow}")
    return latest["html_url"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("remote", help="GitHub HTTPS or SSH remote URL")
    parser.add_argument("commit", help="exact main commit to release")
    args = parser.parse_args()
    try:
        url = check(args.remote, args.commit)
    except (ValueError, OSError, KeyError, urllib.error.URLError) as error:
        print(f"Release blocked: {error}", file=sys.stderr)
        return 1
    print(f"Public install validation passed: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
