"""Tests for the sortie pre-merge hook module."""

import os

import pytest
import yaml
from scripts.sortie_hook import check_pre_merge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_verdict_dir(tmp_path, tree_sha_short: str, cycle: int, verdict: str, findings: list | None = None, tree_sha: str | None = None, with_attestations: bool = True):
    """Create .sortie/{tree_sha_short}-{cycle}/verdict.yaml under tmp_path.

    By default also creates a minimal attestations/ subdirectory so that the
    attestation-existence check in check_pre_merge passes.  Pass
    ``with_attestations=False`` to omit it (for tests that explicitly probe the
    missing-attestations path).
    """
    cycle_dir = tmp_path / f"{tree_sha_short}-{cycle}"
    cycle_dir.mkdir(parents=True, exist_ok=True)
    data: dict = {"verdict": verdict}
    if findings is not None:
        data["findings"] = findings
    if tree_sha is not None:
        data["tree_sha"] = tree_sha
    (cycle_dir / "verdict.yaml").write_text(yaml.dump(data))
    if with_attestations:
        attestations_dir = cycle_dir / "attestations"
        attestations_dir.mkdir(exist_ok=True)
        (attestations_dir / "agent.yaml").write_text("attested: true\n")
    return cycle_dir


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sortie_env(tmp_path):
    """Set up a minimal sortie environment with a passing verdict."""
    tree_sha = "abcdef1234567890"
    tree_sha_short = tree_sha[:8]
    sortie_dir = tmp_path / ".sortie"
    sortie_dir.mkdir()
    cycle_dir = make_verdict_dir(sortie_dir, tree_sha_short, 1, "pass", tree_sha=tree_sha)
    # make_verdict_dir already creates attestations/agent.yaml by default
    attestations_dir = cycle_dir / "attestations"
    return {
        "sortie_dir": str(sortie_dir),
        "tree_sha": tree_sha,
        "tree_sha_short": tree_sha_short,
        "run_path": str(cycle_dir),
        "attestations_dir": str(attestations_dir),
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCheckPreMerge:
    def test_no_verdict_blocks(self, tmp_path):
        """Empty sortie dir (no matching dirs) -> ok=False."""
        sortie_dir = tmp_path / ".sortie"
        sortie_dir.mkdir()
        result = check_pre_merge(str(sortie_dir), "abcdef1234567890")
        assert result["ok"] is False
        assert "reason" in result

    def test_passing_verdict_allows(self, tmp_path):
        """verdict='pass' -> ok=True."""
        sortie_dir = tmp_path / ".sortie"
        sortie_dir.mkdir()
        make_verdict_dir(sortie_dir, "abcdef12", 1, "pass")
        result = check_pre_merge(str(sortie_dir), "abcdef1234567890")
        assert result["ok"] is True
        assert "reason" in result

    def test_pass_with_findings_allows(self, tmp_path):
        """verdict='pass_with_findings' -> ok=True."""
        sortie_dir = tmp_path / ".sortie"
        sortie_dir.mkdir()
        findings = [{"id": "F-001", "summary": "minor issue"}]
        make_verdict_dir(sortie_dir, "abcdef12", 1, "pass_with_findings", findings)
        result = check_pre_merge(str(sortie_dir), "abcdef1234567890")
        assert result["ok"] is True
        assert "reason" in result

    def test_failing_verdict_blocks(self, tmp_path):
        """verdict='fail' -> ok=False, reason mentions fail."""
        sortie_dir = tmp_path / ".sortie"
        sortie_dir.mkdir()
        findings = [
            {"id": "F-001", "summary": "critical bug"},
            {"id": "F-002", "summary": "security issue"},
        ]
        make_verdict_dir(sortie_dir, "abcdef12", 1, "fail", findings)
        result = check_pre_merge(str(sortie_dir), "abcdef1234567890")
        assert result["ok"] is False
        assert "fail" in result["reason"].lower()

    def test_uses_latest_cycle(self, tmp_path):
        """Cycle 1 fails, cycle 2 passes -> uses latest (cycle 2) -> ok=True."""
        sortie_dir = tmp_path / ".sortie"
        sortie_dir.mkdir()
        make_verdict_dir(sortie_dir, "abcdef12", 1, "fail")
        make_verdict_dir(sortie_dir, "abcdef12", 2, "pass")
        result = check_pre_merge(str(sortie_dir), "abcdef1234567890")
        assert result["ok"] is True

    def test_missing_sortie_dir_blocks(self, tmp_path):
        """sortie_dir does not exist -> ok=False."""
        missing_dir = str(tmp_path / ".sortie")
        result = check_pre_merge(missing_dir, "abcdef1234567890")
        assert result["ok"] is False
        assert "reason" in result

    def test_no_verdict_yaml_blocks(self, tmp_path):
        """Matching dir exists but no verdict.yaml -> ok=False."""
        sortie_dir = tmp_path / ".sortie"
        sortie_dir.mkdir()
        # Create the cycle dir without a verdict.yaml
        cycle_dir = sortie_dir / "abcdef12-1"
        cycle_dir.mkdir()
        result = check_pre_merge(str(sortie_dir), "abcdef1234567890")
        assert result["ok"] is False

    def test_uses_latest_cycle_numerically(self, tmp_path):
        """Cycle 10 must take precedence over cycle 9 (not lexicographic)."""
        sortie_dir = tmp_path / ".sortie"
        sortie_dir.mkdir()
        # Cycle 9 passes — lexicographic sort would wrongly pick this as "latest"
        make_verdict_dir(sortie_dir, "abcdef12", 9, "pass")
        # Cycle 10 fails — numerically newer, must win
        make_verdict_dir(sortie_dir, "abcdef12", 10, "fail", [{"id": "v-001", "severity": "major"}])
        result = check_pre_merge(str(sortie_dir), "abcdef1234567890")
        assert result["ok"] is False  # cycle 10 (fail) must win over cycle 9 (pass)

    def test_findings_included_in_fail_reason(self, tmp_path):
        """Up to 5 findings should appear in the reason when verdict is fail."""
        sortie_dir = tmp_path / ".sortie"
        sortie_dir.mkdir()
        findings = [{"id": f"F-00{i}", "summary": f"finding {i}"} for i in range(1, 8)]
        make_verdict_dir(sortie_dir, "abcdef12", 1, "fail", findings)
        result = check_pre_merge(str(sortie_dir), "abcdef1234567890")
        assert result["ok"] is False
        # Should mention at most 5 findings (ids F-001 through F-005)
        reason = result["reason"]
        assert "F-001" in reason
        assert "F-005" in reason
        # F-006 and F-007 should NOT be in the reason (truncated at 5)
        assert "F-006" not in reason
        assert "F-007" not in reason

    def test_rejects_mismatched_tree_sha(self, sortie_env):
        """Verdict with wrong tree_sha should be rejected."""
        verdict = {"verdict": "pass", "findings": [], "tree_sha": "wrong_sha_value"}
        verdict_path = os.path.join(sortie_env["run_path"], "verdict.yaml")
        with open(verdict_path, "w") as f:
            yaml.dump(verdict, f)
        result = check_pre_merge(
            sortie_dir=sortie_env["sortie_dir"],
            tree_sha=sortie_env["tree_sha"],
        )
        assert result["ok"] is False

    def test_accepts_matching_full_tree_sha(self, sortie_env):
        """Verdict with correct full tree_sha should be accepted."""
        verdict = {"verdict": "pass", "findings": [], "tree_sha": sortie_env["tree_sha"]}
        verdict_path = os.path.join(sortie_env["run_path"], "verdict.yaml")
        with open(verdict_path, "w") as f:
            yaml.dump(verdict, f)
        result = check_pre_merge(
            sortie_dir=sortie_env["sortie_dir"],
            tree_sha=sortie_env["tree_sha"],
        )
        assert result["ok"] is True

    def test_missing_attestations_blocks(self, sortie_env):
        """Verdict without an attestations directory should be rejected."""
        import shutil
        shutil.rmtree(sortie_env["attestations_dir"])
        result = check_pre_merge(
            sortie_dir=sortie_env["sortie_dir"],
            tree_sha=sortie_env["tree_sha"],
        )
        assert result["ok"] is False

    def test_empty_attestations_blocks(self, sortie_env):
        """Verdict with an empty attestations directory should be rejected."""
        # Remove all files in the attestations dir
        for f in os.listdir(sortie_env["attestations_dir"]):
            os.remove(os.path.join(sortie_env["attestations_dir"], f))
        result = check_pre_merge(
            sortie_dir=sortie_env["sortie_dir"],
            tree_sha=sortie_env["tree_sha"],
        )
        assert result["ok"] is False

    def test_legacy_verdict_without_tree_sha_allowed(self, tmp_path):
        """Legacy verdict without tree_sha field should still be allowed (backward compat)."""
        sortie_dir = tmp_path / ".sortie"
        sortie_dir.mkdir()
        # No tree_sha in verdict data — legacy format; make_verdict_dir adds attestations by default
        cycle_dir = make_verdict_dir(sortie_dir, "abcdef12", 1, "pass")
        result = check_pre_merge(str(sortie_dir), "abcdef1234567890")
        assert result["ok"] is True
