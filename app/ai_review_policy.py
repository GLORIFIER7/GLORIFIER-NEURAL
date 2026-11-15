"""Fail-closed AI-only pull request review policy for GLORIFIER-NEURAL."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

GITHUB_API_ROOT = "https://api.github.com"
AI_REVIEWERS = (
    "amazon-q-developer[bot]",
    "codeant-ai[bot]",
)
AI_REVIEWER_ALIASES = {
    "amazon-q-developer": "amazon-q-developer[bot]",
    "codeant-ai": "codeant-ai[bot]",
}
ALLOWED_REVIEW_STATES = {"APPROVED", "COMMENTED"}
# Only the explicit bot-emitted blocker annotation is treated as a blocker.
# General words such as "critical" or "high severity" are too ambiguous.
BLOCKER_PATTERN = re.compile(r"(?im)^\s*:stop_sign:\s+")
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MISSING_REVIEW_PREFIX = "Missing a formal AI review from "
WAITING_REVIEW_PREFIXES = (
    MISSING_REVIEW_PREFIX,
    "Missing a completed CodeAnt review status",
    "Missing a CodeAnt PR risk assessment",
    "The latest CodeAnt review status does not cover the current head commit.",
    "The latest CodeAnt review for the current head has not completed.",
    "The CodeAnt PR risk assessment does not match the current head commit.",
)


def _is_waiting_for_review_evidence(failure: str) -> bool:
    """Distinguish absent/stale reviewer evidence from an actual policy blocker."""
    return failure.startswith(WAITING_REVIEW_PREFIXES)

REVIEW_THREADS_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: 100, after: $cursor) {
        nodes {
          isResolved
          isOutdated
          comments(first: 100) {
            nodes {
              body
              commit { oid }
              author { login }
            }
            pageInfo { hasNextPage }
          }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""


def _normalize_login(value: object) -> str:
    login = str(value or "").casefold()
    return AI_REVIEWER_ALIASES.get(login, login)


def _login(item: dict) -> str:
    user = item.get("user")
    return _normalize_login(user.get("login")) if isinstance(user, dict) else ""


def _has_blocker(text: object) -> bool:
    return bool(BLOCKER_PATTERN.search(str(text or "")))


def _parse_review_timestamp(value: object) -> datetime:
    """Parse a GitHub review timestamp as an absolute timezone-aware instant."""
    if not isinstance(value, str) or not value.strip():
        raise TypeError("GitHub returned a review without a valid submission timestamp.")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise TypeError("GitHub returned a malformed review submission timestamp.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TypeError("GitHub review submission timestamp must include a timezone.")
    return parsed.astimezone(UTC)


def _validate_review_record(item: object) -> None:
    """Reject incomplete REST review records instead of silently ignoring them."""
    if not isinstance(item, dict):
        raise TypeError("GitHub returned a malformed pull request review.")
    user = item.get("user")
    if not isinstance(user, dict) or not isinstance(user.get("login"), str) or not user["login"]:
        raise TypeError("GitHub returned a review without a valid author login.")
    state = item.get("state")
    if not isinstance(state, str) or not state:
        raise TypeError("GitHub returned a review without a valid state.")
    commit_id = item.get("commit_id")
    if commit_id is not None and (
        not isinstance(commit_id, str)
        or not re.fullmatch(r"[0-9a-fA-F]{40,64}", commit_id)
    ):
        raise TypeError("GitHub returned a review with an invalid commit SHA.")
    submitted_at = item.get("submitted_at")
    if submitted_at is not None:
        _parse_review_timestamp(submitted_at)
    if state.upper() != "PENDING" and (
        commit_id is None or submitted_at is None
    ):
        raise TypeError("GitHub returned an incomplete submitted review.")
    body = item.get("body")
    if body is not None and not isinstance(body, str):
        raise TypeError("GitHub returned a review with a malformed body.")


def _validate_review_thread(thread: object) -> None:
    """Require complete GraphQL thread/comment fields before blocker evaluation."""
    if not isinstance(thread, dict):
        raise TypeError("GitHub GraphQL returned a malformed review thread.")
    if not isinstance(thread.get("isResolved"), bool):
        raise TypeError("GitHub GraphQL omitted the review-thread resolution state.")
    if not isinstance(thread.get("isOutdated"), bool):
        raise TypeError("GitHub GraphQL omitted the review-thread outdated state.")
    comments = thread.get("comments")
    if not isinstance(comments, dict):
        raise TypeError("GitHub GraphQL returned malformed thread comments.")
    nodes = comments.get("nodes")
    page_info = comments.get("pageInfo")
    if not isinstance(nodes, list) or not isinstance(page_info, dict):
        raise TypeError("GitHub GraphQL returned malformed thread-comment pagination.")
    if not isinstance(page_info.get("hasNextPage"), bool):
        raise TypeError("GitHub GraphQL omitted thread-comment pagination state.")
    if page_info["hasNextPage"]:
        raise RuntimeError(
            "A review thread has more than 100 comments; policy cannot verify it safely."
        )
    for comment in nodes:
        if not isinstance(comment, dict):
            raise TypeError("GitHub GraphQL returned a malformed review comment.")
        author = comment.get("author")
        if not isinstance(author, dict) or not isinstance(author.get("login"), str) or not author["login"]:
            raise TypeError("GitHub GraphQL returned a review comment without an author.")
        body = comment.get("body")
        if not isinstance(body, str):
            raise TypeError("GitHub GraphQL returned a review comment without a valid body.")
        commit = comment.get("commit")
        if not isinstance(commit, dict) or not isinstance(commit.get("oid"), str):
            raise TypeError("GitHub GraphQL returned a review comment without a commit SHA.")
        if not re.fullmatch(r"[0-9a-fA-F]{40,64}", commit["oid"]):
            raise TypeError("GitHub GraphQL returned a review comment with an invalid commit SHA.")




def _validate_issue_comment(item: object) -> None:
    """Reject incomplete GitHub issue comments before trusting bot evidence."""
    if not isinstance(item, dict):
        raise TypeError("GitHub returned a malformed issue comment.")
    user = item.get("user")
    if not isinstance(user, dict) or not isinstance(user.get("login"), str) or not user["login"]:
        raise TypeError("GitHub returned an issue comment without a valid author login.")
    body = item.get("body")
    if not isinstance(body, str):
        raise TypeError("GitHub returned an issue comment without a valid body.")
    _parse_review_timestamp(item.get("created_at"))
    _parse_review_timestamp(item.get("updated_at"))


def _parse_codeant_timestamp(value: object) -> datetime:
    """Parse CodeAnt run timestamps; its machine payload labels these values UTC."""
    if not isinstance(value, str) or not value.strip():
        raise TypeError("CodeAnt returned a review run without a valid timestamp.")
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise TypeError("CodeAnt returned a malformed review run timestamp.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def evaluate_codeant_review_evidence(
    issue_comments: list[dict],
    head_sha: str,
    resolved_risk_sha: str | None = None,
) -> list[str]:
    """Require a completed CodeAnt review and Low Risk assessment on the exact PR head."""
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", head_sha or ""):
        return ["The pull request head SHA is missing or invalid."]
    if not isinstance(issue_comments, list):
        raise TypeError("GitHub issue-comment evidence must be provided as a list.")

    for item in issue_comments:
        _validate_issue_comment(item)

    codeant_comments = [
        item for item in issue_comments
        if _normalize_login(item["user"]["login"]) == "codeant-ai[bot]"
    ]
    status_comments = [
        item for item in codeant_comments
        if "codeant-review-status:" in item["body"]
    ]
    risk_comments = [
        item for item in codeant_comments
        if "CodeAnt PR Risk" in item["body"]
    ]
    failures: list[str] = []

    if not status_comments:
        failures.append(
            "Missing a completed CodeAnt review status for the current head commit."
        )
    else:
        latest_status = max(
            status_comments,
            key=lambda item: _parse_review_timestamp(item["updated_at"]),
        )
        marker = re.search(
            r"<!--\s*codeant-review-status:(.*?)\s*-->",
            latest_status["body"],
            flags=re.DOTALL,
        )
        if marker is None:
            failures.append("CodeAnt review status has a malformed machine-readable payload.")
        else:
            try:
                runs = json.loads(marker.group(1))
                if not isinstance(runs, list) or not runs:
                    raise TypeError("CodeAnt review status must contain a non-empty run list.")
                normalized_runs = []
                for run in runs:
                    if not isinstance(run, dict):
                        raise TypeError("CodeAnt review status contains a malformed run.")
                    run_id = run.get("run_id")
                    label = run.get("label")
                    commit = run.get("commit")
                    done = run.get("done")
                    started = run.get("started")
                    finished = run.get("finished")
                    if not isinstance(run_id, str) or not run_id.strip():
                        raise TypeError("CodeAnt review status contains a run without an ID.")
                    if not isinstance(label, str) or not label.strip():
                        raise TypeError("CodeAnt review status contains a run without a label.")
                    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-fA-F]{40,64}", commit):
                        raise TypeError("CodeAnt review status contains an invalid commit SHA.")
                    if not isinstance(done, bool):
                        raise TypeError("CodeAnt review status contains an invalid completion flag.")
                    started_at = _parse_codeant_timestamp(started)
                    finished_at = (
                        _parse_codeant_timestamp(finished)
                        if finished is not None else None
                    )
                    if finished_at is not None and finished_at < started_at:
                        raise TypeError(
                            "CodeAnt review status contains a finish timestamp before its start timestamp."
                        )
                    normalized_runs.append(
                        (started_at, commit, label, done, finished_at)
                    )
                latest_run = max(normalized_runs, key=lambda run: run[0])
                _, reviewed_sha, label, done, finished_at = latest_run
                if reviewed_sha.casefold() != head_sha.casefold():
                    failures.append(
                        "The latest CodeAnt review status does not cover the current head commit."
                    )
                elif (
                    not done
                    or finished_at is None
                    or label.strip().casefold() not in {
                        "reviewed your pr",
                        "review completed",
                        "incremental review completed",
                    }
                ):
                    failures.append(
                        "The latest CodeAnt review for the current head has not completed."
                    )
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                failures.append(
                    f"CodeAnt review status is malformed and cannot be trusted: {exc}"
                )

    if not risk_comments:
        failures.append(
            "Missing a CodeAnt PR risk assessment for the current head commit."
        )
    else:
        latest_risk = max(
            risk_comments,
            key=lambda item: _parse_review_timestamp(item["updated_at"]),
        )
        assessed = re.search(
            r"(?im)^\s*\*\*Assessed commit:\*\*\s*[\x60]([0-9a-fA-F]{12,64})[\x60]",
            latest_risk["body"],
        )
        assessed_sha = assessed.group(1) if assessed is not None else ""
        verified_risk_sha = (
            assessed_sha if len(assessed_sha) >= 40 else resolved_risk_sha
        )
        if (
            assessed is None
            or not re.fullmatch(r"[0-9a-fA-F]{40,64}", verified_risk_sha or "")
            or not verified_risk_sha.casefold().startswith(assessed_sha.casefold())
            or verified_risk_sha.casefold() != head_sha.casefold()
        ):
            failures.append(
                "The CodeAnt PR risk assessment does not match the exact current head commit."
            )
        else:
            risk_labels = re.findall(
                r"(?im)^\s*\*\*(?:[^*\r\n]*&nbsp;\s*)?"
                r"(Low Risk|Moderate Risk|Medium Risk|High Risk|Critical Risk)"
                r"\s*\*\*\s*$",
                latest_risk["body"],
            )
            if len(risk_labels) != 1 or risk_labels[0].casefold() != "low risk":
                failures.append(
                    "The CodeAnt PR risk assessment is not an unambiguous Low Risk result."
                )

    return failures

def evaluate_reviews(
    reviews: list[dict],
    threads: list[dict],
    head_sha: str,
    issue_comments: list[dict] | None = None,
    resolved_risk_sha: str | None = None,
) -> list[str]:
    """Return policy failures; only current-head AI review evidence counts."""
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", head_sha or ""):
        return ["The pull request head SHA is missing or invalid."]
    if not isinstance(reviews, list) or not isinstance(threads, list):
        raise TypeError("GitHub review evidence must be provided as lists.")
    for item in reviews:
        _validate_review_record(item)
    for thread in threads:
        _validate_review_thread(thread)

    failures: list[str] = []
    required_formal_reviewers = (
        AI_REVIEWERS if issue_comments is None else (AI_REVIEWERS[0],)
    )
    for reviewer in required_formal_reviewers:
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

        latest_timestamp = max(
            _parse_review_timestamp(item["submitted_at"])
            for item in current_reviews
        )
        latest_reviews = [
            item
            for item in current_reviews
            if _parse_review_timestamp(item["submitted_at"]) == latest_timestamp
        ]
        latest_states = {
            str(item.get("state", "")).upper() for item in latest_reviews
        }
        if len(latest_states) != 1:
            failures.append(
                f"{reviewer} has conflicting review states at the latest "
                "current-head timestamp."
            )
            continue

        state = next(iter(latest_states))
        if state == "CHANGES_REQUESTED":
            failures.append(
                f"{reviewer} submitted CHANGES_REQUESTED on the current head."
            )
        elif state not in ALLOWED_REVIEW_STATES:
            failures.append(
                f"{reviewer}'s latest current-head review is not active "
                f"(state: {state or 'unknown'})."
            )
        elif any(_has_blocker(item.get("body")) for item in latest_reviews):
            failures.append(
                f"{reviewer} reported an explicit blocker in its current-head review."
            )

    if issue_comments is not None:
        failures.extend(
            evaluate_codeant_review_evidence(
                issue_comments,
                head_sha,
                resolved_risk_sha=resolved_risk_sha,
            )
        )

    for thread in threads:
        if thread.get("isResolved") is not False:
            continue
        if thread.get("isOutdated") is True:
            continue

        comments = thread.get("comments", {}).get("nodes", [])
        for comment in comments:
            author = comment.get("author") or {}
            commit = comment.get("commit") or {}
            login = _normalize_login(author.get("login"))
            if login not in AI_REVIEWERS:
                continue
            if commit.get("oid") != head_sha:
                continue
            if _has_blocker(comment.get("body")):
                failures.append(
                    f"{login} has an unresolved blocking finding on the current head."
                )

    return failures


def _request_json(url: str, token: str, payload: dict | None = None) -> object:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        url,
        data=body,
        method="POST" if body is not None else "GET",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            **({"Content-Type": "application/json"} if body is not None else {}),
        },
    )
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        code = getattr(exc, "code", None)
        detail = f"HTTP {code}" if code else type(exc).__name__
        raise RuntimeError(f"GitHub API request failed ({detail}).") from None


def _resolve_codeant_risk_sha(
    repo: str,
    issue_comments: list[dict],
    token: str,
) -> str | None:
    """Resolve CodeAnt's abbreviated assessed SHA through GitHub's commit API.

    GitHub returns a full commit object only when the supplied abbreviation
    resolves unambiguously. Any API error or mismatched response fails closed.
    """
    if not REPO_PATTERN.fullmatch(repo):
        raise ValueError("A valid repository name is required to resolve CodeAnt evidence.")
    if not isinstance(issue_comments, list):
        raise TypeError("GitHub issue-comment evidence must be provided as a list.")

    for item in issue_comments:
        _validate_issue_comment(item)

    risk_comments = [
        item for item in issue_comments
        if _normalize_login(item["user"]["login"]) == "codeant-ai[bot]"
        and "CodeAnt PR Risk" in item["body"]
    ]
    if not risk_comments:
        return None

    latest_risk = max(
        risk_comments,
        key=lambda item: _parse_review_timestamp(item["updated_at"]),
    )
    assessed = re.search(
        r"(?im)^\s*\*\*Assessed commit:\*\*\s*[\x60]([0-9a-fA-F]{12,64})[\x60]",
        latest_risk["body"],
    )
    if assessed is None:
        return None

    prefix = assessed.group(1)
    if len(prefix) >= 40:
        return prefix

    payload = _request_json(
        f"{GITHUB_API_ROOT}/repos/{repo}/commits/{prefix}",
        token,
    )
    if not isinstance(payload, dict):
        raise TypeError("GitHub commit lookup returned an invalid response.")
    resolved_sha = payload.get("sha")
    if (
        not isinstance(resolved_sha, str)
        or not re.fullmatch(r"[0-9a-fA-F]{40,64}", resolved_sha)
        or not resolved_sha.casefold().startswith(prefix.casefold())
    ):
        raise TypeError(
            "GitHub commit lookup does not match the supplied prefix."
        )
    return resolved_sha


def _fetch_reviews(repo: str, pull_number: int, token: str) -> list[dict]:
    result: list[dict] = []
    page = 1
    while True:
        url = (
            f"{GITHUB_API_ROOT}/repos/{repo}/pulls/{pull_number}/reviews"
            f"?per_page=100&page={page}"
        )
        payload = _request_json(url, token)
        if not isinstance(payload, list):
            raise TypeError("GitHub API returned an invalid pull request reviews response.")
        for item in payload:
            _validate_review_record(item)
        result.extend(payload)
        if len(payload) < 100:
            return result
        page += 1



def _fetch_issue_comments(repo: str, pull_number: int, token: str) -> list[dict]:
    """Fetch all PR issue comments used for authenticated CodeAnt status evidence."""
    result: list[dict] = []
    page = 1
    while True:
        url = (
            f"{GITHUB_API_ROOT}/repos/{repo}/issues/{pull_number}/comments"
            f"?per_page=100&page={page}"
        )
        payload = _request_json(url, token)
        if not isinstance(payload, list):
            raise TypeError("GitHub API returned an invalid pull request issue-comments response.")
        for item in payload:
            _validate_issue_comment(item)
        result.extend(payload)
        if len(payload) < 100:
            return result
        page += 1



def _fetch_review_threads(repo: str, pull_number: int, token: str) -> list[dict]:
    owner, name = repo.split("/", maxsplit=1)
    result: list[dict] = []
    cursor = None
    while True:
        payload = _request_json(
            f"{GITHUB_API_ROOT}/graphql",
            token,
            {
                "query": REVIEW_THREADS_QUERY,
                "variables": {
                    "owner": owner,
                    "name": name,
                    "number": pull_number,
                    "cursor": cursor,
                },
            },
        )
        if not isinstance(payload, dict):
            raise TypeError("GitHub GraphQL returned an invalid review-thread response.")
        if payload.get("errors"):
            raise RuntimeError("GitHub GraphQL could not read review threads.")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise TypeError("GitHub GraphQL omitted review-thread data.")
        repository = data.get("repository")
        if not isinstance(repository, dict):
            raise TypeError("GitHub GraphQL omitted the repository.")
        pull_request = repository.get("pullRequest")
        if not isinstance(pull_request, dict):
            raise TypeError("GitHub GraphQL omitted the pull request.")
        connection = pull_request.get("reviewThreads")
        if not isinstance(connection, dict):
            raise TypeError("GitHub GraphQL omitted the review-thread connection.")
        nodes = connection.get("nodes")
        page_info = connection.get("pageInfo")
        if not isinstance(nodes, list) or not isinstance(page_info, dict):
            raise TypeError("GitHub GraphQL returned malformed review-thread data.")
        if not isinstance(page_info.get("hasNextPage"), bool):
            raise TypeError("GitHub GraphQL omitted review-thread pagination state.")

        for thread in nodes:
            _validate_review_thread(thread)
            result.append(thread)

        if page_info["hasNextPage"] is not True:
            return result
        cursor = page_info.get("endCursor")
        if not isinstance(cursor, str) or not cursor:
            raise RuntimeError("GitHub GraphQL omitted the next review-thread cursor.")


def _write_summary(lines: list[str]) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write("## AI Review Policy\n\n")
            summary.write("\n".join(f"- {line}" for line in lines))
            summary.write("\n")


def _read_int(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int(os.environ.get(name, str(default))))
    except ValueError:
        return default


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GH_TOKEN", "")
    pull_number = _read_int("PR_NUMBER", 0, 1)
    wait_seconds = _read_int("AI_REVIEW_WAIT_SECONDS", 900)
    poll_interval = _read_int("AI_REVIEW_POLL_INTERVAL_SECONDS", 30, 5)
    head_sha = os.environ.get("PR_HEAD_SHA", "")

    if not REPO_PATTERN.fullmatch(repo) or pull_number < 1 or not token:
        message = "Required repository, pull request number, or read-only GitHub token is missing."
        print(f"::error::{message}")
        _write_summary([message])
        return 1
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", head_sha):
        message = "The pull request head SHA is missing or invalid."
        print(f"::error::{message}")
        _write_summary([message])
        return 1

    deadline = time.monotonic() + wait_seconds
    while True:
        try:
            reviews = _fetch_reviews(repo, pull_number, token)
            threads = _fetch_review_threads(repo, pull_number, token)
            issue_comments = _fetch_issue_comments(repo, pull_number, token)
            resolved_risk_sha = _resolve_codeant_risk_sha(
                repo, issue_comments, token
            )
        except (RuntimeError, TypeError, ValueError) as exc:
            message = str(exc)
            print(f"::error::{message}")
            _write_summary([message])
            return 1

        failures = evaluate_reviews(
            reviews,
            threads,
            head_sha,
            issue_comments=issue_comments,
            resolved_risk_sha=resolved_risk_sha,
        )
        blockers = [
            failure
            for failure in failures
            if not _is_waiting_for_review_evidence(failure)
        ]
        if blockers:
            for failure in blockers:
                print(f"::error::{failure}")
            _write_summary(blockers)
            return 1

        if not failures:
            message = (
                "Policy passed: Amazon Q submitted a formal current-head review; CodeAnt "
                "completed a current-head review with Low Risk; no unresolved AI blocker remains."
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

        print(f"Waiting for current-head AI reviews: {'; '.join(failures)}")
        time.sleep(min(poll_interval, remaining))


if __name__ == "__main__":
    raise SystemExit(main())
