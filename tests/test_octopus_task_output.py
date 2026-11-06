"""Regression tests for safe Octopus task IDs written to GITHUB_OUTPUT."""

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


WORKFLOW = (
    Path(__file__).resolve().parents[1]
    / ".github"
    / "workflows"
    / "octopus-deploy.yml"
).read_text(encoding="utf-8")


def _task_output_script() -> str:
    step = re.search(
        r"(?ms)^      - name: Validate the deployment task response\n"
        r"(.*?)(?=^      - name:|\Z)",
        WORKFLOW,
    )
    assert step, "The Octopus deployment task validation step must exist"

    run = re.search(
        r"(?ms)^        run: \|\n((?:^          .*\n|^\n)*)",
        step.group(1),
    )
    assert run, "The task validation step must contain an inline Bash script"

    return "\n".join(
        line.removeprefix("          ")
        for line in run.group(1).splitlines()
    ).rstrip()


def _run_task_output(server_task_id: str) -> tuple[subprocess.CompletedProcess[str], str]:
    with tempfile.TemporaryDirectory(prefix="octopus-task-output-") as directory:
        output_path = Path(directory) / "github-output"
        output_path.write_text("", encoding="utf-8")
        environment = os.environ.copy()
        environment["GITHUB_OUTPUT"] = str(output_path)
        environment["OCTOPUS_SERVER_TASKS"] = json.dumps(
            [{"serverTaskId": server_task_id}]
        )
        result = subprocess.run(
            ["bash", "-euo", "pipefail", "-c", _task_output_script()],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
        return result, output_path.read_text(encoding="utf-8")


def test_octopus_task_output_accepts_one_valid_server_task_id():
    result, output = _run_task_output("ServerTasks-1234")

    assert result.returncode == 0, result.stderr
    assert output == "server_task_id=ServerTasks-1234\n"


def test_octopus_task_output_rejects_carriage_returns_and_newlines():
    for server_task_id in (
        "ServerTasks-1234\nINJECTED=value",
        "ServerTasks-1234\rINJECTED=value",
    ):
        result, output = _run_task_output(server_task_id)

        assert result.returncode != 0, "control characters must fail closed"
        assert output == "", "invalid task IDs must not write to GITHUB_OUTPUT"
        assert "unexpected newline" in result.stdout.lower()
