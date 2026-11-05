"""Security regression tests for the autonomous NEURAL maintenance workflow."""

from pathlib import Path
import subprocess
import sys


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


def test_publish_job_only_runs_when_a_validated_patch_artifact_exists():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    codex_section = workflow[workflow.index("  codex:"):workflow.index("  publish:")]
    publish_section = workflow[workflow.index("  publish:"):]

    assert "patch_ready:" in codex_section
    assert "steps.upload_patch.outputs.artifact-id" in codex_section
    assert "needs: codex" in publish_section
    assert "needs.codex.outputs.patch_ready == 'true'" in publish_section
    upload_start = codex_section.index("- name: Upload validated patch for publish job")
    upload_end = codex_section.find("\n      - name:", upload_start + 1)
    upload_step = codex_section[upload_start:] if upload_end < 0 else codex_section[upload_start:upload_end]
    assert "steps.stage.outputs.changed == 'true' && steps.validation.outcome == 'success'" in upload_step


def test_publish_job_holds_all_publication_until_after_0831_laos_time():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    publish_section = workflow[workflow.index("  publish:"):]
    gate = publish_section.index("- name: Enforce PR publication window (Laos)")
    branch = publish_section.index("- name: Create isolated maintenance branch and push")
    pull_request = publish_section.index("- name: Open draft pull request")

    assert gate < branch < pull_request
    branch_step = publish_section[branch:pull_request]
    assert "steps.time_window.outputs.allowed == 'true'" in branch_step
    assert "gh pr create --draft --base main" in publish_section
    assert "gh workflow run ci.yml" not in publish_section
    assert "gh pr merge" not in publish_section
    assert "--auto" not in publish_section


def test_time_window_uses_decimal_hhmm_and_blocks_before_0831():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert workflow.count('current_hhmm_decimal=$((10#$current_hhmm))') == 2
    assert workflow.count("current_hhmm_decimal < 831") == 2
    assert workflow.count('[[ ! "$current_hhmm" =~ ^[0-9]{4}$ ]]') == 2


def test_codex_engineering_cycle_is_not_gated_by_the_publication_window():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    codex_section = workflow[workflow.index("  codex:"):workflow.index("  publish:")]
    for step_name in [
        "Verify trusted dependency lock before agent execution",
        "Prepare isolated agent workspace",
        "Run Codex maintenance agent",
        "Copy validated app and tests changes back",
        "Validate generated patch with locked project checks",
    ]:
        start = codex_section.index(f"- name: {step_name}")
        end = codex_section.find("\n      - name:", start + 1)
        step = codex_section[start:] if end < 0 else codex_section[start:end]
        assert "steps.time_window.outputs.allowed" not in step


def test_workflow_uses_shallow_checkout_and_env_safe_run_id():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "fetch-depth: 1" in workflow
    assert "RUN_ID: ${{ github.run_id }}" in workflow
    assert 'BRANCH="ai/maintenance/$RUN_ID"' in workflow
    assert 'BRANCH="ai/maintenance/${{ github.run_id }}"' not in workflow


def test_copy_back_does_not_preserve_hard_links():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 'rsync -rlptD --delete "$AGENT_WORKSPACE/app/"' in workflow
    assert 'rsync -rlptD --delete "$AGENT_WORKSPACE/tests/"' in workflow
    assert 'rsync -a --delete' not in workflow


def test_generated_pr_is_draft_and_never_auto_merges():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    publish_section = workflow[workflow.index("  publish:"):]

    assert "- name: Open draft pull request" in publish_section
    assert "gh pr create --draft --base main" in publish_section
    assert "gh pr create --base main" not in publish_section
    assert "gh workflow run ci.yml" not in publish_section
    assert "gh pr merge" not in publish_section
    assert "--auto" not in publish_section


def test_scope_validator_validates_both_rename_source_and_destination(
    tmp_path: Path,
):
    """--no-renames exposes both the deleted source and the added destination
    as independent changed paths.  A rename entirely outside app/ and tests/
    must be rejected on both sides."""
    repository = _repository(tmp_path)
    # README.md (root-level, outside allowed roots) → .github/workflows/evil.yml
    # git mv stages both a deletion of README.md and an addition of evil.yml;
    # with --no-renames the validator sees both paths independently.
    _git(repository, "mv", "README.md", ".github/workflows/evil.yml")

    result = _validate(repository)

    assert result.returncode != 0
    # Destination must be rejected
    assert ".github/workflows/evil.yml" in result.stderr
    # Source (README.md at repository root) must also be rejected
    assert "README.md" in result.stderr


def test_workflow_uses_hourly_schedule_and_never_auto_merges():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert 'cron: "0 * * * *"' in workflow
    assert 'cron: "41 2 * * 1"' not in workflow
    assert "gh pr merge" not in workflow
    assert "--auto" not in workflow


def test_workflow_publication_is_after_0830_in_laos_timezone():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "TZ=Asia/Vientiane" in workflow
    assert "current_hhmm_decimal=$((10#$current_hhmm))" in workflow
    assert "current_hhmm_decimal < 831" in workflow
    assert '[[ ! "$current_hhmm" =~ ^[0-9]{4}$ ]]' in workflow
    publish_job = workflow[workflow.index("  publish:"):]
    assert "needs.codex.outputs.patch_ready == 'true'" in publish_job


def test_publish_job_receives_only_a_validated_patch_artifact():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "steps.validation.outcome == 'success'" in workflow
    assert "id: upload_patch" in workflow
    assert "artifact-id" in workflow
    assert "outputs.patch_ready" in workflow


def test_workflow_cost_control_uses_single_variable():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "AI_MAINTENANCE_AUTORUN" in workflow
    assert "authorize_pull_request" not in workflow


def test_workflow_codex_job_has_read_only_permissions():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    codex_start = workflow.index("  codex:")
    publish_start = workflow.index("  publish:")
    codex_section = workflow[codex_start:publish_start]

    assert "contents: read" in codex_section
    assert "contents: write" not in codex_section
    assert "pull-requests: write" not in codex_section
    assert "actions: write" not in codex_section


def test_workflow_publish_job_has_minimal_write_permissions():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    publish_start = workflow.index("  publish:")
    publish_section = workflow[publish_start:]

    assert "contents: write" in publish_section
    assert "pull-requests: write" in publish_section
    assert "actions: write" not in publish_section
