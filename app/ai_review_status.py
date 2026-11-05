"""Publish trusted AI-review policy statuses for open pull requests.

This module is intended to run only from the repository's default branch on a
schedule or a push to that branch. It never checks out or executes pull-request
code. The status is written to the exact head SHA returned by the GitHub API.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from urllib.parse import quote

GITHUB_API_ROOT = "https://api.github.com"
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
HEAD_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")
STATUS_CONTEXT = "AI Review Policy (trusted)"
DEFAULT_REVIEW_TIMEOUT_SECONDS = 900


def derive_status(
    failures: list[str],
    head_age_seconds: float,
    timeout_seconds: int = DEFAULT_REVIEW_TIMEOUT_SECONDS,
) -> tuple[str, str]:
    """Map review evidence to a GitHub commit status, failing closed."""
    from .ai_review_policy import MISSING_REVIEW_PREFIX

    blockers = [
        failure for failure in failures
        if not failure.startswith(MISSING_REVIEW_PREFIX)
    ]
    if blockers:
        return "failure", "A current-head AI review blocker or invalid review state exists."
    if failures:
        if head_age_seconds >= timeout_seconds:
            return "failure", "Timed out waiting for both current-head AI reviews."
        return "pending", "Waiting for both current-head AI reviews (15-minute deadline)."
    return "success", "Both configured AI reviewers passed current-head policy checks."


def parse_commit_timestamp(value: str) -> datetime:
    """Parse GitHub's ISO-8601 commit timestamp and require timezone awareness."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("GitHub commit timestamp is missing.")
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("GitHub commit timestamp must include a timezone.")
    return parsed.astimezone(timezone.utc)


def _request_json(url: str, token: str, payload: dict | None = None) -> object:
    from .ai_review_policy import _request_json as request_json

    return request_json(url, token, payload)


def _fetch_policy_evidence(repo: str, number: int, token: str, head_sha: str) -> list[str]:
    from .ai_review_policy import (
        _fetch_review_threads,
        _fetch_reviews,
        evaluate_reviews,
    )

    reviews = _fetch_reviews(repo, number, token)
    threads = _fetch_review_threads(repo, number, token)
    return evaluate_reviews(reviews, threads, head_sha)


def _commit_age_seconds(repo: str, token: str, head_sha: str) -> float:
    payload = _request_json(
        f"{GITHUB_API_ROOT}/repos/{repo}/commits/{head_sha}", token
    )
    if not isinstance(payload, dict):
        raise TypeError("GitHub returned an invalid commit response.")
    commit = payload.get("commit") or {}
    committer = commit.get("committer") or {}
    timestamp = committer.get("date") or (commit.get("author") or {}).get("date")
    committed_at = parse_commit_timestamp(timestamp)
    return max(0.0, (datetime.now(timezone.utc) - committed_at).total_seconds())


def _publish_status(
    repo: str,
    token: str,
    head_sha: str,
    state: str,
    description: str,
    target_url: str,
) -> None:
    if state not in {"pending", "success", "failure", "error"}:
        raise ValueError(f"Unsupported GitHub commit status: {state}")
    payload = {
        "state": state,
        "context": STATUS_CONTEXT,
        "description": description[:140],
        "target_url": target_url,
    }
    _request_json(
        f"{GITHUB_API_ROOT}/repos/{repo}/statuses/{head_sha}", token, payload
    )


def _append_summary(lines: list[str]) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as summary:
            summary.write("## Trusted AI Review Status\n\n")
            summary.write("\n".join(f"- {line}" for line in lines))
            summary.write("\n")


def sweep_open_pull_requests(repo: str, token: str) -> dict[str, int]:
    """Evaluate every open PR targeting the default branch and publish statuses."""
    if not REPO_PATTERN.fullmatch(repo or "") or not token:
        raise ValueError("A valid GITHUB_REPOSITORY and scoped token are required.")

    repository = _request_json(f"{GITHUB_API_ROOT}/repos/{repo}", token)
    if not isinstance(repository, dict) or not repository.get("default_branch"):
        raise TypeError("GitHub did not return the repository default branch.")
    default_branch = str(repository["default_branch"])

    pulls: list[dict] = []
    page = 1
    while True:
        pulls_url = (
            f"{GITHUB_API_ROOT}/repos/{repo}/pulls?state=open"
            f"&base={quote(default_branch)}&per_page=100&page={page}"
        )
        payload = _request_json(pulls_url, token)
        if not isinstance(payload, list):
            raise TypeError("GitHub returned an invalid open pull-request response.")
        pulls.extend(item for item in payload if isinstance(item, dict))
        if len(payload) < 100:
            break
        page += 1

    counts = {"success": 0, "pending": 0, "failure": 0, "error": 0, "skipped": 0}
    summary: list[str] = []
    for pull in pulls:
        number = pull.get("number")
        base = pull.get("base") or {}
        head = pull.get("head") or {}
        head_sha = str(head.get("sha") or "")
        target_url = str(
            pull.get("html_url") or f"https://github.com/{repo}/pull/{number}"
        )
        if not isinstance(number, int) or base.get("ref") != default_branch:
            counts["skipped"] += 1
            continue
        if not HEAD_SHA_PATTERN.fullmatch(head_sha):
            counts["error"] += 1
            summary.append(
                f"PR #{number}: invalid head SHA; no success status was published."
            )
            continue

        # Replace any earlier success with pending before refreshing evidence.
        _publish_status(
            repo,
            token,
            head_sha,
            "pending",
            "Trusted AI review policy is refreshing current-head evidence.",
            target_url,
        )
        try:
            failures = _fetch_policy_evidence(repo, number, token, head_sha)
            age_seconds = _commit_age_seconds(repo, token, head_sha)
            state, description = derive_status(failures, age_seconds)
        except (RuntimeError, TypeError, ValueError, KeyError) as exc:
            state = "error"
            description = (
                "Trusted AI review policy could not verify current-head evidence."
            )
            summary.append(
                f"PR #{number}: evidence lookup failed ({type(exc).__name__})."
            )
        _publish_status(repo, token, head_sha, state, description, target_url)
        counts[state] += 1
        summary.append(f"PR #{number}: {state} — {description}")

    _append_summary(summary or ["No open pull requests target the default branch."])
    for line in summary:
        print(line)
    totals = ", ".join(
        f"{key}={value}" for key, value in counts.items()
    )
    print(f"Trusted AI review status sweep: {totals}")
    return counts


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GH_TOKEN", "")
    try:
        sweep_open_pull_requests(repo, token)
    except (RuntimeError, TypeError, ValueError, KeyError) as exc:
        message = (
            f"Trusted AI review status sweep failed closed ({type(exc).__name__})."
        )
        print(f"::error::{message}")
        _append_summary([message])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
