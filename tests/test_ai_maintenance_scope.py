"""Security regression tests for the autonomous NEURAL maintenance workflow."""

from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ai-maintenance.yml"
VALIDATOR = ROOT / "scripts" / "validate_ai_maintenance_scope.py"


def _git(repository: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "app").mkdir()
    (repository / "tests").mkdir()
    (repository / ".github" / "workflows").mkdir(parents=True)
    (repository / "app" / "service.py").write_text(
        "value = 1\n", encoding="utf-8"
    )
    (repository / "tests" / "test_service.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    (repository / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "Test")
    _git(repository, "config", "user.email", "test@example.invalid")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "initial")
    return repository


def _validate(repository: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), "--repo", str(repository)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_scope_validator_accepts_only_app_and_tests_changes(tmp_path: Path):
    repository = _repository(tmp_path)
    (repository / "app" / "service.py").write_text(
        "value = 2\n", encoding="utf-8"
    )
    (repository / "tests" / "test_new.py").write_text(
        "def test_new():\n    assert True\n", encoding="utf-8"
    )

    result = _validate(repository)

    assert result.returncode == 0, result.stderr


def test_scope_validator_rejects_untracked_workflow_files(tmp_path: Path):
    repository = _repository(tmp_path)
    unexpected = repository / ".github" / "workflows" / "unexpected.yml"
    unexpected.write_text("name: unexpected\n", encoding="utf-8")

    result = _validate(repository)

    assert result.returncode != 0
    assert ".github/workflows/unexpected.yml" in result.stderr


def test_scope_validator_rejects_rename_from_app_into_workflow_directory(
    tmp_path: Path,
):
    repository = _repository(tmp_path)
    _git(repository, "mv", "app/service.py", ".github/workflows/evil.yml")

    result = _validate(repository)

    assert result.returncode != 0
    assert ".github/workflows/evil.yml" in result.stderr


def test_scope_validator_rejects_symlinks_even_when_inside_app(tmp_path: Path):
    repository = _repository(tmp_path)
    (repository / "app" / "escape").symlink_to("../../README.md")

    result = _validate(repository)

    assert result.returncode != 0
    assert "symlink" in result.stderr.casefold()


def test_codex_runs_in_an_isolated_app_and_tests_workspace():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "Prepare isolated agent workspace" in workflow
    assert "working-directory: ${{ steps.agent_workspace.outputs.path }}" in workflow
    assert "Copy validated app and tests changes back" in workflow
    assert "find app tests -type l" in workflow


def test_workflow_validates_scope_and_uses_credential_helper():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "validate_ai_maintenance_scope.py" in workflow
    assert "gh auth setup-git" in workflow
    assert "x-access-token:$GH_TOKEN@" not in workflow
    assert "push --set-upstream origin" in workflow


@pytest.mark.parametrize(
    "step_name",
    ["Open draft pull request", "Run CI against the generated PR branch"],
)
def test_publication_steps_require_successful_validation(step_name: str):
    workflow = WORKFLOW.read_text(encoding="utf-8")
    start = workflow.index(f"- name: {step_name}")
    end = workflow.find("\n      - name:", start + 1)
    section = workflow[start:] if end < 0 else workflow[start:end]

    assert "steps.validation.outcome == 'success'" in section
