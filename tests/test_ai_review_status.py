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


def test_timestamp_without_timezone_is_rejected():
    try:
        parse_commit_timestamp("2026-11-05T10:00:00")
    except ValueError as exc:
        assert "timezone" in str(exc)
    else:
        raise AssertionError("A timezone-free commit timestamp must be rejected")
