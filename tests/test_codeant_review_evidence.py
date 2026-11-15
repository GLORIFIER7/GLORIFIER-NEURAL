import json

from app.ai_review_policy import evaluate_codeant_review_evidence, evaluate_reviews


HEAD_SHA = "a" * 40
OTHER_SHA = "b" * 40


def status_comment(head_sha=HEAD_SHA, *, runs=None, login="codeant-ai[bot]"):
    if runs is None:
        runs = [
            {
                "run_id": "review-001",
                "label": "Reviewed your PR",
                "commit": head_sha,
                "started": "2026-11-15T06:00:00Z",
                "finished": "2026-11-15T06:02:00Z",
                "done": True,
            }
        ]
    body = (
        "CodeAnt Review Status\n"
        "<!-- codeant-review-status:"
        + json.dumps(runs, separators=(",", ":"))
        + " -->"
    )
    return {
        "user": {"login": login},
        "body": body,
        "created_at": "2026-11-15T06:00:00Z",
        "updated_at": "2026-11-15T06:02:00Z",
    }


def risk_comment(head_sha=HEAD_SHA, *, risk="Low Risk", login="codeant-ai[bot]"):
    return {
        "user": {"login": login},
        "body": (
            "CodeAnt PR Risk\n\n"
            f"**{risk}**\n\n"
            "- The PR appears safe to merge; no actionable issues were identified in the review.\n\n"
            f"**Assessed commit:** `{head_sha[:12]}`"
        ),
        "created_at": "2026-11-15T06:03:00Z",
        "updated_at": "2026-11-15T06:03:00Z",
    }


def test_codeant_completed_review_and_low_risk_on_exact_head_satisfy_evidence():
    comments = [status_comment(), risk_comment()]

    assert evaluate_codeant_review_evidence(comments, HEAD_SHA) == []


def test_codeant_stale_review_status_does_not_satisfy_current_head():
    comments = [status_comment(OTHER_SHA), risk_comment()]

    failures = evaluate_codeant_review_evidence(comments, HEAD_SHA)

    assert any("current head" in failure.casefold() for failure in failures)


def test_codeant_stale_risk_assessment_does_not_satisfy_current_head():
    comments = [status_comment(), risk_comment(OTHER_SHA)]

    failures = evaluate_codeant_review_evidence(comments, HEAD_SHA)

    assert any("risk" in failure.casefold() for failure in failures)


def test_latest_incomplete_codeant_run_overrides_older_completed_run():
    runs = [
        {
            "run_id": "review-new",
            "label": "Reviewing your PR…",
            "commit": HEAD_SHA,
            "started": "2026-11-15T06:03:00Z",
            "finished": None,
            "done": False,
        },
        {
            "run_id": "review-old",
            "label": "Reviewed your PR",
            "commit": HEAD_SHA,
            "started": "2026-11-15T06:00:00Z",
            "finished": "2026-11-15T06:02:00Z",
            "done": True,
        },
    ]
    comments = [status_comment(runs=runs), risk_comment()]

    failures = evaluate_codeant_review_evidence(comments, HEAD_SHA)

    assert any("not completed" in failure.casefold() for failure in failures)


def test_codeant_non_low_risk_result_blocks_policy():
    comments = [status_comment(), risk_comment(risk="High Risk")]

    failures = evaluate_codeant_review_evidence(comments, HEAD_SHA)

    assert any("low risk" in failure.casefold() for failure in failures)


def test_comment_from_non_codeant_author_cannot_satisfy_policy():
    comments = [
        status_comment(login="GLORIFIER7"),
        risk_comment(login="GLORIFIER7"),
    ]

    failures = evaluate_codeant_review_evidence(comments, HEAD_SHA)

    assert failures


def test_malformed_codeant_machine_status_fails_closed():
    malformed = {
        "user": {"login": "codeant-ai[bot]"},
        "body": "<!-- codeant-review-status:{not-json} -->",
        "created_at": "2026-11-15T06:00:00Z",
        "updated_at": "2026-11-15T06:02:00Z",
    }
    comments = [malformed, risk_comment()]

    failures = evaluate_codeant_review_evidence(comments, HEAD_SHA)

    assert failures


def test_review_policy_accepts_codeant_comment_evidence_without_formal_review_object():
    comments = [status_comment(), risk_comment()]
    amazon_q_review = [
        {
            "user": {"login": "amazon-q-developer[bot]"},
            "state": "COMMENTED",
            "commit_id": HEAD_SHA,
            "submitted_at": "2026-11-15T06:00:00Z",
            "body": "Review completed without blockers.",
        }
    ]

    assert evaluate_reviews(
        amazon_q_review,
        [],
        HEAD_SHA,
        issue_comments=comments,
    ) == []
