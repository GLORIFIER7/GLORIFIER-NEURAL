from app.ai_review_policy import evaluate_reviews


HEAD_SHA = "a" * 40


def review(user, state="COMMENTED", commit_id=HEAD_SHA, submitted_at="2026-11-05T10:00:00Z", body=""):
    return {
        "user": {"login": user},
        "state": state,
        "commit_id": commit_id,
        "submitted_at": submitted_at,
        "body": body,
    }


def comment(user, commit_id=HEAD_SHA, body="Reviewed."):
    return {
        "user": {"login": user},
        "commit_id": commit_id,
        "body": body,
    }


def test_two_configured_ai_reviewers_on_current_head_satisfy_policy():
    reviews = [
        review("amazon-q-developer[bot]"),
        review("codeant-ai[bot]", submitted_at="2026-11-05T10:01:00Z"),
    ]

    assert evaluate_reviews(reviews, [], HEAD_SHA) == []


def test_human_review_does_not_substitute_for_missing_ai_reviewer():
    reviews = [
        review("amazon-q-developer[bot]"),
        review("human-reviewer", state="APPROVED"),
    ]

    failures = evaluate_reviews(reviews, [], HEAD_SHA)

    assert any("codeant-ai[bot]" in failure for failure in failures)


def test_stale_ai_review_does_not_satisfy_current_head():
    reviews = [
        review("amazon-q-developer[bot]", commit_id="b" * 40),
        review("codeant-ai[bot]"),
    ]

    failures = evaluate_reviews(reviews, [], HEAD_SHA)

    assert any("amazon-q-developer[bot]" in failure for failure in failures)


def test_changes_requested_by_ai_reviewer_blocks_merge():
    reviews = [
        review("amazon-q-developer[bot]", state="CHANGES_REQUESTED"),
        review("codeant-ai[bot]"),
    ]

    failures = evaluate_reviews(reviews, [], HEAD_SHA)

    assert any("CHANGES_REQUESTED" in failure for failure in failures)


def test_explicit_ai_blocker_finding_blocks_merge():
    reviews = [
        review("amazon-q-developer[bot]"),
        review("codeant-ai[bot]"),
    ]
    comments = [
        comment("amazon-q-developer[bot]", body=":stop_sign: Security/Cost Risk"),
    ]

    failures = evaluate_reviews(reviews, comments, HEAD_SHA)

    assert any("blocking finding" in failure.lower() for failure in failures)


def test_old_ai_inline_comment_does_not_block_new_head():
    reviews = [
        review("amazon-q-developer[bot]"),
        review("codeant-ai[bot]"),
    ]
    comments = [
        comment("amazon-q-developer[bot]", commit_id="b" * 40, body=":stop_sign: old finding"),
    ]

    assert evaluate_reviews(reviews, comments, HEAD_SHA) == []


def test_human_comment_does_not_count_as_ai_blocker_or_ai_review():
    reviews = [
        review("amazon-q-developer[bot]"),
        review("codeant-ai[bot]"),
    ]
    comments = [
        comment("human-reviewer", body=":stop_sign: advisory only"),
    ]

    assert evaluate_reviews(reviews, comments, HEAD_SHA) == []
