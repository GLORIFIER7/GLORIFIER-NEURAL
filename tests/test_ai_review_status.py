import pytest

import app.ai_review_status as publisher
from app.ai_review_status import derive_status, parse_commit_timestamp


def test_missing_reviews_remain_pending_before_the_review_deadline():
    failures = [
        "Missing a formal AI review from amazon-q-developer[bot] on the current head commit.",
        "Missing a formal AI review from codeant-ai[bot] on the current head commit.",
    ]

    assert derive_status(failures, 899) == (
        "pending",
        "Waiting for both current-head AI reviews (15-minute deadline).",
    )


def test_missing_reviews_fail_closed_at_the_review_deadline():
    failures = ["Missing a formal AI review from codeant-ai[bot] on the current head commit."]

    assert derive_status(failures, 900)[0] == "failure"


def test_explicit_blocker_fails_immediately_even_before_deadline():
    failures = ["amazon-q-developer[bot] reported an explicit blocker in its current-head review."]

    assert derive_status(failures, 1)[0] == "failure"


def test_both_current_head_reviews_without_blockers_succeed():
    assert derive_status([], 0) == (
        "success",
        "Both configured AI reviewers passed current-head policy checks.",
    )


def test_github_commit_timestamp_is_normalized_to_utc():
    parsed = parse_commit_timestamp("2026-11-05T10:00:00Z")

    assert parsed.isoformat() == "2026-11-05T10:00:00+00:00"


def test_timestamp_with_numeric_offset_is_preserved_and_normalized():
    parsed = parse_commit_timestamp("2026-11-05T12:00:00+02:00")

    assert parsed.isoformat() == "2026-11-05T10:00:00+00:00"


def test_timestamp_without_timezone_is_rejected():
    with pytest.raises(ValueError, match="timezone"):
        parse_commit_timestamp("2026-11-05T10:00:00")


def _two_open_pull_requests():
    return [
        {
            "number": 1,
            "base": {"ref": "main"},
            "head": {"sha": "a" * 40},
            "html_url": "https://github.com/example/repo/pull/1",
        },
        {
            "number": 2,
            "base": {"ref": "main"},
            "head": {"sha": "b" * 40},
            "html_url": "https://github.com/example/repo/pull/2",
        },
    ]


def _stub_sweep_inputs(monkeypatch):
    def request_json(url, token, payload=None):
        if url == "https://api.github.com/repos/example/repo":
            return {"default_branch": "main"}
        if "/pulls?" in url:
            return _two_open_pull_requests()
        raise AssertionError(f"Unexpected API request: {url}")

    monkeypatch.setattr(publisher, "_request_json", request_json)
    monkeypatch.setattr(publisher, "_fetch_policy_evidence", lambda *args: [])
    monkeypatch.setattr(publisher, "_commit_age_seconds", lambda *args: 1)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)


def test_preliminary_pending_status_failure_does_not_abort_remaining_pull_requests(
    monkeypatch,
):
    _stub_sweep_inputs(monkeypatch)
    calls = []

    def publish(repo, token, sha, state, description, target_url):
        calls.append((sha, state))
        if sha == "a" * 40 and state == "pending":
            raise RuntimeError("temporary status write failure")

    monkeypatch.setattr(publisher, "_publish_status", publish)

    counts = publisher.sweep_open_pull_requests("example/repo", "token")

    assert counts == {
        "success": 1,
        "pending": 0,
        "failure": 0,
        "error": 1,
        "skipped": 0,
    }
    assert ("b" * 40, "success") in calls


def test_final_status_write_failure_does_not_abort_remaining_pull_requests(monkeypatch):
    _stub_sweep_inputs(monkeypatch)
    calls = []

    def publish(repo, token, sha, state, description, target_url):
        calls.append((sha, state))
        if sha == "a" * 40 and state == "success":
            raise RuntimeError("temporary status write failure")

    monkeypatch.setattr(publisher, "_publish_status", publish)

    counts = publisher.sweep_open_pull_requests("example/repo", "token")

    assert counts["error"] == 1
    assert counts["success"] == 1
    assert ("b" * 40, "success") in calls


def test_unsupported_derived_state_fails_closed_without_aborting_sweep(monkeypatch):
    _stub_sweep_inputs(monkeypatch)
    calls = []
    monkeypatch.setattr(
        publisher, "derive_status", lambda failures, age: ("warning", "unexpected state")
    )
    monkeypatch.setattr(
        publisher,
        "_publish_status",
        lambda repo, token, sha, state, description, target_url: calls.append(
            (sha, state)
        ),
    )

    counts = publisher.sweep_open_pull_requests("example/repo", "token")

    assert counts["error"] == 2
    assert ("a" * 40, "error") in calls
    assert ("b" * 40, "error") in calls


def test_repository_and_token_validation_have_distinct_errors():
    with pytest.raises(ValueError, match="GITHUB_REPOSITORY"):
        publisher.sweep_open_pull_requests("invalid repo", "token")
    with pytest.raises(ValueError, match="GH_TOKEN"):
        publisher.sweep_open_pull_requests("example/repo", "")
