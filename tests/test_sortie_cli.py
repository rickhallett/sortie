"""Tests for the sortie CLI entry point (scripts/sortie.py)."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

import pytest
import yaml


SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "sortie.py")


def run_cli(*args, cwd=None, input=None):
    """Run the sortie CLI with the given arguments and return CompletedProcess."""
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        capture_output=True,
        text=True,
        cwd=cwd or os.path.dirname(SCRIPT),
        input=input,
    )


class TestHelpAndUsage:
    def test_help_prints_usage(self):
        result = run_cli("--help")
        assert result.returncode == 0
        output = result.stdout + result.stderr
        assert "pipeline" in output
        assert "status" in output
        assert "dispose" in output

    def test_unknown_subcommand_fails(self):
        result = run_cli("unknowncmd")
        assert result.returncode != 0

    def test_no_args_fails_or_prints_help(self):
        result = run_cli()
        # Either shows help (0) or errors out (non-zero) -- both are acceptable
        # but output should mention subcommands
        output = result.stdout + result.stderr
        assert "pipeline" in output or "usage" in output.lower() or result.returncode != 0


class TestStatusSubcommand:
    def test_status_no_runs(self, tmp_path):
        """With an empty ledger, status should return 0 and say no runs."""
        # Build a minimal config pointing to an empty ledger
        ledger_path = tmp_path / "ledger.yaml"
        ledger_data = {"runs": []}
        ledger_path.write_text(yaml.dump(ledger_data))

        config = {
            "roster": [],
            "debrief": {"model": "claude", "invoke": "hook-agent", "prompt": "prompts/debrief.md"},
            "triage": {"block_on": ["critical"]},
            "modes": {"code": {"prompt": "prompts/sortie-code.md"}},
            "ledger": {"path": str(ledger_path)},
            "deposition": {"dir": str(tmp_path / "{tree_sha}-{cycle}")},
        }
        config_path = tmp_path / "sortie.yaml"
        config_path.write_text(yaml.dump(config))

        result = run_cli("--config", str(config_path), "status")
        assert result.returncode == 0
        output = result.stdout + result.stderr
        # Should indicate no runs
        assert "no runs" in output.lower() or "0 runs" in output.lower() or "0" in output

    def test_status_shows_recent_runs(self, tmp_path):
        """With some runs in ledger, status should display them."""
        ledger_path = tmp_path / "ledger.yaml"
        runs = [
            {
                "tree_sha": "abc12345",
                "cycle": 1,
                "mode": "code",
                "verdict": "pass",
                "worker_branch": "feature/test",
                "findings": [],
            },
            {
                "tree_sha": "def67890",
                "cycle": 1,
                "mode": "code",
                "verdict": "fail",
                "worker_branch": "feature/other",
                "findings": [{"id": "F1", "summary": "issue"}],
            },
        ]
        ledger_path.write_text(yaml.dump({"runs": runs}))

        config = {
            "roster": [],
            "debrief": {"model": "claude", "invoke": "hook-agent", "prompt": "prompts/debrief.md"},
            "triage": {"block_on": ["critical"]},
            "modes": {"code": {"prompt": "prompts/sortie-code.md"}},
            "ledger": {"path": str(ledger_path)},
            "deposition": {"dir": str(tmp_path / "{tree_sha}-{cycle}")},
        }
        config_path = tmp_path / "sortie.yaml"
        config_path.write_text(yaml.dump(config))

        result = run_cli("--config", str(config_path), "status")
        assert result.returncode == 0
        output = result.stdout + result.stderr
        assert "abc12345" in output or "abc" in output
        assert "pass" in output


class TestDisposeSubcommand:
    def _setup_run(self, tmp_path):
        """Create run dir with verdict.yaml and ledger.yaml. Return (config_path, run_id)."""
        tree_sha = "abcdef1234567890"
        cycle = 1
        run_id = f"{tree_sha}-{cycle}"
        run_path = tmp_path / run_id
        run_path.mkdir(parents=True)

        findings = [
            {
                "id": "F001",
                "summary": "SQL injection risk",
                "severity": "critical",
                "convergent": True,
                "disposition": "open",
            }
        ]
        verdict_data = {
            "verdict": "fail",
            "findings": findings,
            "convergence": "convergent",
            "tree_sha": tree_sha,
            "cycle": cycle,
        }
        verdict_path = run_path / "verdict.yaml"
        verdict_path.write_text(yaml.dump(verdict_data))

        ledger_path = tmp_path / "ledger.yaml"
        ledger_runs = [
            {
                "tree_sha": tree_sha,
                "cycle": cycle,
                "mode": "code",
                "verdict": "fail",
                "worker_branch": "feature/test",
                "findings": findings,
            }
        ]
        ledger_path.write_text(yaml.dump({"runs": ledger_runs}))

        config = {
            "roster": [],
            "debrief": {"model": "claude", "invoke": "hook-agent", "prompt": "prompts/debrief.md"},
            "triage": {"block_on": ["critical"]},
            "modes": {"code": {"prompt": "prompts/sortie-code.md"}},
            "ledger": {"path": str(ledger_path)},
            "deposition": {"dir": str(tmp_path / "{tree_sha}-{cycle}")},
        }
        config_path = tmp_path / "sortie.yaml"
        config_path.write_text(yaml.dump(config))

        return config_path, run_id, tree_sha, cycle, run_path, ledger_path

    def test_dispose_updates_verdict_and_ledger(self, tmp_path):
        """dispose should update disposition in both verdict.yaml and ledger.yaml."""
        config_path, run_id, tree_sha, cycle, run_path, ledger_path = self._setup_run(tmp_path)

        result = run_cli(
            "--config", str(config_path),
            "dispose", run_id, "F001", "fixed",
        )
        assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"

        # Check verdict.yaml updated
        verdict = yaml.safe_load((run_path / "verdict.yaml").read_text())
        f001 = next(f for f in verdict["findings"] if f["id"] == "F001")
        assert f001["disposition"] == "fixed"

        # Check ledger updated
        ledger_data = yaml.safe_load(ledger_path.read_text())
        run_entry = next(
            r for r in ledger_data["runs"]
            if r["tree_sha"] == tree_sha and r["cycle"] == cycle
        )
        l_f001 = next(f for f in run_entry["findings"] if f["id"] == "F001")
        assert l_f001["disposition"] == "fixed"

    def test_dispose_invalid_disposition_fails(self, tmp_path):
        """Unsupported disposition values should cause non-zero exit."""
        config_path, run_id, *_ = self._setup_run(tmp_path)
        result = run_cli(
            "--config", str(config_path),
            "dispose", run_id, "F001", "invalid-value",
        )
        assert result.returncode != 0

    def test_dispose_valid_dispositions(self, tmp_path):
        """Each valid disposition value should succeed."""
        valid = ["fixed", "false-positive", "deferred", "disagree"]
        for disposition in valid:
            inner_tmp = tmp_path / disposition
            inner_tmp.mkdir()
            config_path, run_id, tree_sha, cycle, run_path, ledger_path = self._setup_run(inner_tmp)
            result = run_cli(
                "--config", str(config_path),
                "dispose", run_id, "F001", disposition,
            )
            assert result.returncode == 0, (
                f"disposition {disposition!r} failed: {result.stderr}"
            )


class TestSortieDisposeBulk:
    def _setup_run(self, tmp_path):
        """Create run dir with verdict.yaml and ledger.yaml. Return (config_path, run_id, ...)."""
        tree_sha = "abcdef1234567890"
        cycle = 1
        run_id = f"{tree_sha}-{cycle}"
        run_path = tmp_path / run_id
        run_path.mkdir(parents=True)

        findings = [
            {
                "id": "F001",
                "summary": "SQL injection risk",
                "severity": "critical",
                "convergent": True,
                "disposition": "open",
            },
            {
                "id": "F002",
                "summary": "XSS vulnerability",
                "severity": "high",
                "convergent": True,
                "disposition": "open",
            },
            {
                "id": "F003",
                "summary": "Insecure dependency",
                "severity": "medium",
                "convergent": False,
                "disposition": "open",
            },
        ]
        verdict_data = {
            "verdict": "fail",
            "findings": findings,
            "convergence": "convergent",
            "tree_sha": tree_sha,
            "cycle": cycle,
        }
        verdict_path = run_path / "verdict.yaml"
        verdict_path.write_text(yaml.dump(verdict_data))

        ledger_path = tmp_path / "ledger.yaml"
        ledger_runs = [
            {
                "tree_sha": tree_sha,
                "cycle": cycle,
                "mode": "code",
                "verdict": "fail",
                "worker_branch": "feature/test",
                "findings": findings,
            }
        ]
        ledger_path.write_text(yaml.dump({"runs": ledger_runs}))

        config = {
            "roster": [],
            "debrief": {"model": "claude", "invoke": "hook-agent", "prompt": "prompts/debrief.md"},
            "triage": {"block_on": ["critical"]},
            "modes": {"code": {"prompt": "prompts/sortie-code.md"}},
            "ledger": {"path": str(ledger_path)},
            "deposition": {"dir": str(tmp_path / "{tree_sha}-{cycle}")},
        }
        config_path = tmp_path / "sortie.yaml"
        config_path.write_text(yaml.dump(config))

        return config_path, run_id, tree_sha, cycle, run_path, ledger_path

    def test_dispose_bulk_marks_all(self, tmp_path):
        """dispose-bulk should update all findings in both verdict.yaml and ledger.yaml."""
        config_path, run_id, tree_sha, cycle, run_path, ledger_path = self._setup_run(tmp_path)

        result = run_cli(
            "--config", str(config_path),
            "dispose-bulk", run_id, "fixed",
        )
        assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"

        # Check verdict.yaml: all findings updated
        verdict = yaml.safe_load((run_path / "verdict.yaml").read_text())
        for finding in verdict["findings"]:
            assert finding["disposition"] == "fixed", (
                f"Finding {finding['id']} not updated in verdict.yaml"
            )

        # Check ledger: all findings updated
        ledger_data = yaml.safe_load(ledger_path.read_text())
        run_entry = next(
            r for r in ledger_data["runs"]
            if r["tree_sha"] == tree_sha and r["cycle"] == cycle
        )
        for finding in run_entry["findings"]:
            assert finding["disposition"] == "fixed", (
                f"Finding {finding['id']} not updated in ledger"
            )

        # Check stdout contains finding count
        output = result.stdout + result.stderr
        assert "3" in output
