"""Regression tests for Octopus deployment workflow timeout budgeting."""

from pathlib import Path
import re


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "octopus-deploy.yml"
).read_text(encoding="utf-8")


def test_octopus_job_timeout_leaves_headroom_after_await_action_timeout():
    deploy = re.search(
        r"(?ms)^  deploy:\n(.*?)(?=^  [a-z0-9_-]+:\n|\Z)",
        WORKFLOW,
    )
    assert deploy, "The Octopus deploy job must exist"

    job = deploy.group(1)
    job_timeout = re.search(r"(?m)^    timeout-minutes: (\d+)$", job)
    assert job_timeout, "The Octopus deploy job must have an explicit timeout"

    await_step = re.search(
        r"(?ms)^      - name: Wait for the Octopus deployment to finish\n"
        r"(.*?)(?=^      - name:|\Z)",
        job,
    )
    assert await_step, "The Octopus await-task step must exist"

    await_timeout = re.search(
        r"(?m)^\s+timeout_after: ['\"]?(\d+)['\"]?$",
        await_step.group(1),
    )
    assert await_timeout, "The Octopus await-task timeout must be explicit"

    job_seconds = int(job_timeout.group(1)) * 60
    await_seconds = int(await_timeout.group(1))
    required_headroom_seconds = 30 * 60

    assert job_seconds >= await_seconds + required_headroom_seconds, (
        "The GitHub job timeout must leave at least 30 minutes beyond the "
        "Octopus task wait timeout so setup and teardown cannot cut off the wait."
    )
