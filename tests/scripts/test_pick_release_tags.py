"""Tests for scripts/sandbox/pick-release-tags.sh.

The "Pick release tags" CI job feeds this script's stdout straight into a
GitHub Actions matrix. A repo/fork with no vYYYY.M.D release tags yet (or a
checkout that forgot to fetch tags) must not fail the job forever -- it
should emit an empty JSON array so downstream matrix jobs simply skip.
"""

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "sandbox" / "pick-release-tags.sh"


def _run(repo_dir, *args):
    return subprocess.run(
        ["bash", str(SCRIPT), "--repo", str(repo_dir), *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def _init_repo(path):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "a@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "a"], cwd=path, check=True)


def _commit_and_tag(path, tag=None):
    subprocess.run(["git", "commit", "--allow-empty", "-q", "-m", tag or "init"], cwd=path, check=True)
    if tag:
        subprocess.run(["git", "tag", tag], cwd=path, check=True)


@pytest.fixture()
def empty_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    _commit_and_tag(repo)
    return repo


@pytest.fixture()
def tagged_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    for tag in ("v2024.1.1", "v2024.6.3", "v2025.1.1", "v2025.6.1", "v2026.1.1", "v2026.6.1"):
        _commit_and_tag(repo, tag)
    return repo


def test_no_tags_emits_empty_matrix_instead_of_failing(empty_repo):
    # This is the regression: a repo/fork with zero release tags (a real,
    # unavoidable state for a fresh fork) must not hard-fail the job.
    result = _run(empty_repo, "--count", "5")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
    assert "no vYYYY.M.D release tags found" in result.stderr


def test_non_release_tags_only_also_emits_empty_matrix(empty_repo):
    subprocess.run(["git", "tag", "backup/2026-01-01"], cwd=empty_repo, check=True)
    result = _run(empty_repo, "--count", "5")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


def test_tags_present_still_picks_a_spread(tagged_repo):
    result = _run(tagged_repo, "--count", "5")
    assert result.returncode == 0, result.stderr
    import json

    picked = json.loads(result.stdout)
    assert picked[0] == "v2024.1.1"
    assert picked[-1] == "v2026.6.1"
    assert len(picked) == 5
