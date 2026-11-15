import json

from app.ai_review_policy import (
    _is_waiting_for_review_evidence,
    evaluate_codeant_review_evidence,
    evaluate_reviews,
)


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
            f"**Assessed commit:** `{head_sha}`"
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


def test_actual_codeant_status_and_risk_comment_format_is_accepted():
    run = {
        "run_id": "e22da4662759",
        "label": "Reviewed your PR",
        "commit": HEAD_SHA,
        "started": "2026-11-15T06:18:10.876763",
        "finished": "2026-11-15T06:20:33.802414",
        "done": True,
    }
    status = {
        "user": {"login": "codeant-ai[bot]"},
        "body": (
            "## CodeAnt Review Status\n\n"
            "**✅ Review completed**\n\n"
            "<!-- codeant-review-status:"
            + json.dumps([run], separators=(",", ":"))
            + " -->"
        ),
        "created_at": "2026-11-15T06:09:05Z",
        "updated_at": "2026-11-15T06:20:34Z",
    }
    risk = {
        "user": {"login": "codeant-ai[bot]"},
        "body": (
            "## CodeAnt PR Risk\n\n"
            "**🟢&nbsp; Low Risk**\n\n"
            "**Assessed commit:** " + chr(96) + HEAD_SHA + chr(96)
        ),
        "created_at": "2026-11-15T06:14:01Z",
        "updated_at": "2026-11-15T06:20:44Z",
    }

    assert evaluate_codeant_review_evidence([status, risk], HEAD_SHA) == []


def test_missing_or_stale_codeant_evidence_waits_but_findings_block():
    waiting = [
        "Missing a completed CodeAnt review status for the current head commit.",
        "Missing a CodeAnt PR risk assessment for the current head commit.",
        "The latest CodeAnt review status does not cover the current head commit.",
        "The latest CodeAnt review for the current head has not completed.",
        "The CodeAnt PR risk assessment does not match the current head commit.",
        "Missing a formal AI review from codeant-ai[bot] on the current head commit.",
    ]
    blockers = [
        "CodeAnt review status is malformed and cannot be trusted.",
        "The CodeAnt PR risk assessment is not Low Risk.",
        "Unresolved AI blocker from codeant-ai[bot].",
    ]

    assert all(_is_waiting_for_review_evidence(item) for item in waiting)
    assert not any(_is_waiting_for_review_evidence(item) for item in blockers)



def test_negative_completion_label_does_not_count_as_a_review():
    runs = [{
        "run_id": "review-negative",
        "label": "Not reviewed",
        "commit": HEAD_SHA,
        "started": "2026-11-15T06:00:00Z",
        "finished": "2026-11-15T06:02:00Z",
        "done": True,
    }]

    failures = evaluate_codeant_review_evidence(
        [status_comment(runs=runs), risk_comment()],
        HEAD_SHA,
    )

    assert any("not completed" in failure.casefold() for failure in failures)


def test_finish_timestamp_before_start_timestamp_is_rejected():
    runs = [{
        "run_id": "review-time-reversed",
        "label": "Reviewed your PR",
        "commit": HEAD_SHA,
        "started": "2026-11-15T06:02:00Z",
        "finished": "2026-11-15T06:00:00Z",
        "done": True,
    }]

    failures = evaluate_codeant_review_evidence(
        [status_comment(runs=runs), risk_comment()],
        HEAD_SHA,
    )

    assert failures


def test_risk_assessment_requires_full_head_sha():
    comments = [
        status_comment(),
        risk_comment(HEAD_SHA[:12]),
    ]

    failures = evaluate_codeant_review_evidence(comments, HEAD_SHA)

    assert any("current head" in failure.casefold() for failure in failures)


def test_high_risk_assessment_cannot_pass_due_to_incidental_low_risk_text():
    risk = risk_comment(risk="High Risk")
    risk["body"] += "\\n\\nThe previous scan was **Low Risk**."

    failures = evaluate_codeant_review_evidence(
        [status_comment(), risk],
        HEAD_SHA,
    )

    assert any("low risk" in failure.casefold() for failure in failures)
