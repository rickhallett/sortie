"""Integration smoke test: full pipeline with echo-based CLI stubs."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest
import yaml


# Absolute path to the real sortie.py script
SCRIPT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts", "sortie.py"))

# Canned YAML output that the printf stubs emit
STUB_OUTPUT = """\
findings:
  - id: f-001
    severity: major
    file: src/auth.ts
    line: 42
    category: security
    summary: Token cached without expiry validation
    detail: The OAuth token is stored but expiry is not checked.

verdict: pass_with_findings
"""


def _printf_command(text: str) -> str:
    """Return a printf shell command that emits *text* (newlines escaped)."""
    # Replace newlines with \\n for printf, escape single quotes
    escaped = text.replace("\\", "\\\\").replace("'", "'\\''").replace("\n", "\\n")
    return f"printf '{escaped}\\n'"


def _make_stub_config(tmp_path) -> tuple[str, str, str]:
    """Write sortie.yaml, a minimal prompt file, and return (config_path, prompt_path, ledger_path)."""
    os.makedirs(str(tmp_path), exist_ok=True)
    prompt_path = os.path.join(str(tmp_path), "sortie-code.md")
    with open(prompt_path, "w") as f:
        f.write("Review the diff for branch {branch}.\n")

    debrief_prompt_path = os.path.join(str(tmp_path), "debrief.md")
    with open(debrief_prompt_path, "w") as f:
        f.write("Debrief the findings.\n")

    ledger_path = os.path.join(str(tmp_path), "ledger.yaml")
    deposition_dir = os.path.join(str(tmp_path), ".sortie")

    stub_cmd = _printf_command(STUB_OUTPUT)

    cfg = {
        "roster": [
            {
                "name": "stub-a",
                "invoke": "cli",
                "command": stub_cmd,
                "timeout": 30,
            },
            {
                "name": "stub-b",
                "invoke": "cli",
                "command": stub_cmd,
                "timeout": 30,
            },
        ],
        "debrief": {
            "name": "debrief-stub",
            "invoke": "cli",
            "command": stub_cmd,
            "prompt": debrief_prompt_path,
            "timeout": 30,
        },
        "triage": {
            "block_on": ["critical"],
            "max_remediation_cycles": 2,
            "convergence_threshold": 2,
        },
        "modes": {
            "code": {
                "prompt": prompt_path,
                "trigger": "merge",
                "roster": ["stub-a", "stub-b"],
                "triage": {
                    "block_on": ["critical"],
                },
            },
        },
        "ledger": {
            "path": ledger_path,
        },
        "deposition": {
            "dir": deposition_dir + "/{tree_sha}-{cycle}/",
            "keep_individual": True,
        },
    }

    config_path = os.path.join(str(tmp_path), "sortie.yaml")
    with open(config_path, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False)

    return config_path, ledger_path, deposition_dir


def _init_git_repo(tmp_path: str) -> None:
    """Initialise a git repo with an initial commit on main and a worker branch."""

    def git(*args):
        subprocess.run(
            ["git", *args],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")

    # Initial commit on main
    src_file = os.path.join(tmp_path, "src", "auth.ts")
    os.makedirs(os.path.dirname(src_file), exist_ok=True)
    with open(src_file, "w") as f:
        f.write("// auth module\nexport const token = '';\n")

    git("add", ".")
    git("commit", "-m", "init: initial commit")

    # Worker branch with a change
    git("checkout", "-b", "worktree/worker-b")
    with open(src_file, "a") as f:
        f.write("\n// TODO: validate token expiry\n")
    git("add", ".")
    git("commit", "-m", "feat: add token caching")

    # Return to main
    git("checkout", "main")


class TestIntegrationPipeline:
    def test_pipeline_smoke(self, tmp_path):
        """Full pipeline with printf stubs completes and produces expected artifacts."""
        repo_dir = str(tmp_path / "repo")
        os.makedirs(repo_dir)

        _init_git_repo(repo_dir)

        config_path, ledger_path, deposition_dir = _make_stub_config(tmp_path / "config")

        result = subprocess.run(
            [
                sys.executable,
                SCRIPT,
                "--config", config_path,
                "pipeline", "worktree/worker-b",
                "--mode", "code",
            ],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )

        # --- Exit code ---
        assert result.returncode in (0, 1, 2), (
            f"Unexpected exit code {result.returncode}.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

        # --- At least one run directory ---
        sortie_base = os.path.join(str(tmp_path / "config"), ".sortie")
        assert os.path.isdir(sortie_base), (
            f".sortie dir not found at {sortie_base}.\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        run_dirs = [
            d for d in os.listdir(sortie_base)
            if os.path.isdir(os.path.join(sortie_base, d))
        ]
        assert len(run_dirs) >= 1, "Expected at least one run directory in .sortie/"

        run_dir = os.path.join(sortie_base, run_dirs[0])

        # --- verdict.yaml exists ---
        verdict_path = os.path.join(run_dir, "verdict.yaml")
        assert os.path.isfile(verdict_path), f"verdict.yaml not found in {run_dir}"

        with open(verdict_path) as f:
            verdict_data = yaml.safe_load(f)
        assert isinstance(verdict_data, dict), "verdict.yaml should be a YAML mapping"
        assert "verdict" in verdict_data, "verdict.yaml must contain 'verdict' key"

        # --- ledger.yaml exists with at least one entry ---
        assert os.path.isfile(ledger_path), f"ledger.yaml not found at {ledger_path}"

        with open(ledger_path) as f:
            ledger_data = yaml.safe_load(f)
        assert isinstance(ledger_data, dict), "ledger.yaml should be a YAML mapping"
        runs = ledger_data.get("runs", [])
        assert len(runs) >= 1, "ledger.yaml must contain at least one run entry"

        # --- individual sortie-{model}.yaml files ---
        sortie_files = [
            f for f in os.listdir(run_dir)
            if f.startswith("sortie-") and f.endswith(".yaml")
        ]
        assert len(sortie_files) >= 1, (
            f"Expected at least one sortie-{{model}}.yaml in {run_dir}; found: {os.listdir(run_dir)}"
        )

        # Spot-check one of them
        with open(os.path.join(run_dir, sortie_files[0])) as f:
            sortie_doc = yaml.safe_load(f)
        assert isinstance(sortie_doc, dict), "sortie-{model}.yaml should be a YAML mapping"
        assert "verdict" in sortie_doc, "sortie-{model}.yaml must have 'verdict' key"
