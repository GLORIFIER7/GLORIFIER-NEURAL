"""Fail-closed AI-only pull request review policy for GLORIFIER-NEURAL."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

AI_REVIEWERS = (
    "amazon-q-developer[bot]",
    "codeant-ai[bot]",
)
ALLOWED_REVIEW_STATES = {"APPROVED", "COMMENTED"}
BLOCKER_MARKERS = (
    ":stop_sign:",
    "security/cost risk",
    "[blocker]",
    "blocker:",
    "critical:",
    "severity: critical",
    "high severity",
    "do not merge",
    "must not merge",
    "::error::",
)
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MISSING_REVIEW_PREFIX = "Missing a formal AI review from "


def _login(item: dict) -> str:
    user = item.get("user")
    return str(user.get("login", "")).casefold() if isinstance(user, dict) else ""


def _has_blocker(text: object) -> bool:
    body = str(text or "").casefold()
    return any(marker in body for marker in BLOCKER_MARKERS)


def evaluate_reviews(reviews: list[dict], comments: list[dict], head_sha: str) -> list[str]:
    """Return policy failures; only the configured bot identities count."""
    failures: list[str] = []

    if not head_sha or not re.fullmatch(r"[0-9a-fA-F]{40,64}", head_sha):
        return ["The pull request head SHA is missing or invalid."]

    for reviewer in AI_REVIEWERS:
        current_reviews = [
            item
            for item in reviews
            if _login(item) == reviewer
            and item.get("commit_id") == head_sha
            and item.get("submitted_at")
        ]
        if not current_reviews:
            failures.append(
                f"{MISSING_REVIEW_PREFIX}{reviewer} on the current head commit."
            )
            continue

        if any(str(item.get("state", "")).upper() == "CHANGES_REQUESTED" for item in current_reviews):
            failures.append(f"{reviewer} submitted CHANGES_REQUESTED on the current head.")
            continue

        latest = max(current_reviews, key=lambda item: str(item.get("submitted_at", "")))
        state = str(latest.get("state", "")).upper()
        if state not in ALLOWED_REVIEW_STATES:
            failures.append(
                f"{reviewer}'s latest current-head review is not active "
                f"(state: {state or 'unknown'})."
            )
            continue
        if _has_blocker(latest.get("body")):
            failures.append(
                f"{reviewer} reported an explicit blocking finding in its current-head review."
            )

    for item in comments:
        if _login(item) not in AI_REVIEWERS or item.get("commit_id") != head_sha:
            continue
        if _has_blocker(item.get("body")):
            failures.append(
                f"{_login(item)} reported an explicit blocking finding on the current head."
            )

    return failures


def _fetch_collection(api_url: str, repo: str, pull_number: int, collection: str, token: str) -> list[dict]:
    result: list[dict] = []
    page = 1
    while True:
        url = (
            f"{api_url.rstrip('/')}/repos/{repo}/pulls/{pull_number}/"
            f"{collection}?per_page=100&page={page}"
        )
        request = Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            code = getattr(exc, "code", None)
            detail = f"HTTP {code}" if code else type(exc).__name__
            raise RuntimeError(
                f"GitHub API could not return pull request {collection} ({detail})."
            ) from None

        if not isinstance(payload, list):
            raise RuntimeError(f"GitHub API returned an invalid {collection} response.")
        result.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            return result
        page += 1


def _write_summary(lines: list[str]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write("## AI Review Policy\n\n")
            summary.write("\n".join(f"- {line}" for line in lines))
            summary.write("\n")


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GH_TOKEN", "")
    api_url = os.environ.get("GH_API_URL", "https://api.github.com")
    try:
        pull_number = int(os.environ.get("PR_NUMBER", ""))
        wait_seconds = max(0, int(os.environ.get("AI_REVIEW_WAIT_SECONDS", "0")))
        poll_interval = max(5, int(os.environ.get("AI_REVIEW_POLL_INTERVAL_SECONDS", "30")))
    except ValueError:
        pull_number = 0
        wait_seconds = 0
        poll_interval = 30
    head_sha = os.environ.get("PR_HEAD_SHA", "")

    if not REPO_PATTERN.fullmatch(repo) or pull_number < 1 or not token:
        message = "Required repository, pull request number, or read-only GitHub token is missing."
        print(f"::error::{message}")
        _write_summary([message])
        return 1

    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            reviews = _fetch_collection(api_url, repo, pull_number, "reviews", token)
            comments = _fetch_collection(api_url, repo, pull_number, "comments", token)
        except RuntimeError as exc:
            message = str(exc)
            print(f"::error::{message}")
            _write_summary([message])
            return 1

        failures = evaluate_reviews(reviews, comments, head_sha)
        blockers = [
            failure for failure in failures
            if not failure.startswith(MISSING_REVIEW_PREFIX)
        ]
        if blockers:
            for failure in blockers:
                print(f"::error::{failure}")
            _write_summary(blockers)
            return 1

        if not failures:
            message = (
                "Policy passed: Amazon Q Developer and CodeAnt AI each submitted a formal "
                "review for the current head commit, and no explicit AI blocker was found."
            )
            print(message)
            _write_summary([message])
            return 0

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            for failure in failures:
                print(f"::error::{failure}")
            _write_summary(failures)
            return 1

        missing = "; ".join(failures)
        print(f"Waiting for current-head AI reviews: {missing}")
        time.sleep(min(poll_interval, remaining))


if __name__ == "__main__":
    raise SystemExit(main())
