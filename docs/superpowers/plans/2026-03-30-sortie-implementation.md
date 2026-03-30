# Sortie Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an async adversarial multi-model code review system for Claude Code Teams swarm workflows.

**Architecture:** Python CLI orchestrator (`scripts/sortie.py`) fans out review prompts to a configurable roster of LLMs in parallel, collects structured YAML findings, synthesizes via a 4th model debrief invocation, triages by severity, and gates worktree merges. All data captured in an append-only ledger for operational evaluation.

**Tech Stack:** Python 3.10+ (stdlib + PyYAML), justfile, Claude Code hooks, Gemini CLI, Codex CLI.

**Spec:** `docs/superpowers/specs/2026-03-30-sortie-design.md`

---

## File Map

| File | Responsibility | Created in |
|---|---|---|
| `scripts/ledger.py` | YAML ledger read/write/append, disposition updates | Task 1 |
| `scripts/config.py` | Load and validate `sortie.yaml`, mode resolution with default inheritance | Task 2 |
| `scripts/identity.py` | Tree hash computation, run ID generation, cycle counting | Task 3 |
| `scripts/attestation.py` | Write/read/verify attestation YAML files | Task 4 |
| `scripts/invoker.py` | Fan out to roster models (cli subprocess, hook-agent stub), collect output | Task 5 |
| `scripts/debrief.py` | Feed sortie outputs to debrief model, write verdict | Task 6 |
| `scripts/triage.py` | Severity-gated triage logic, verdict-to-exit-code | Task 7 |
| `scripts/sortie.py` | CLI entry point, subcommands: pipeline, run, debrief, status, dispose | Task 8 |
| `scripts/sortie_hook.py` | Claude Code pre-merge hook glue | Task 9 |
| `prompts/sortie-code.md` | Adversarial code review prompt | Task 10 |
| `prompts/sortie-tests.md` | Test quality review prompt | Task 10 |
| `prompts/sortie-docs.md` | Documentation accuracy review prompt | Task 10 |
| `prompts/debrief.md` | Synthesis/triangulation prompt | Task 10 |
| `sortie.yaml` | Default configuration | Task 11 |
| `justfile` | Orchestration targets | Task 11 |
| `hooks/settings.json` | Reference Claude Code hook config | Task 11 |
| `.gitignore` | Ignore .sortie/ runtime except ledger | Task 11 |
| `CLAUDE.md` | Agent instructions for this repo | Task 11 |
| `tests/test_ledger.py` | Ledger tests | Task 1 |
| `tests/test_config.py` | Config tests | Task 2 |
| `tests/test_identity.py` | Identity tests | Task 3 |
| `tests/test_attestation.py` | Attestation tests | Task 4 |
| `tests/test_invoker.py` | Invoker tests | Task 5 |
| `tests/test_debrief.py` | Debrief tests | Task 6 |
| `tests/test_triage.py` | Triage tests | Task 7 |
| `tests/test_sortie_cli.py` | CLI integration tests | Task 8 |
| `tests/test_hook.py` | Hook tests | Task 9 |

**Note on `sortie.py` decomposition:** The spec describes `sortie.py` as ~300-400 lines. This plan splits it into focused modules (`config.py`, `identity.py`, `attestation.py`, `invoker.py`, `debrief.py`, `triage.py`, `ledger.py`) with `sortie.py` as a thin CLI entry point that composes them. Each module is independently testable. The spec's intent is preserved -- the justfile still calls `python3 scripts/sortie.py pipeline`.

---

### Task 1: Ledger Module

**Files:**
- Create: `scripts/ledger.py`
- Create: `tests/test_ledger.py`

The ledger is the foundation -- every other module writes to it. Build first so all subsequent tasks can use it.

- [ ] **Step 1: Write failing tests for ledger**

```python
# tests/test_ledger.py
import os
import tempfile
import pytest
import yaml

from scripts.ledger import Ledger


@pytest.fixture
def tmp_ledger(tmp_path):
    path = tmp_path / "ledger.yaml"
    return Ledger(str(path))


class TestLedgerInit:
    def test_creates_file_if_missing(self, tmp_ledger):
        tmp_ledger.load()
        assert os.path.exists(tmp_ledger.path)

    def test_loads_empty_ledger(self, tmp_ledger):
        data = tmp_ledger.load()
        assert data == {"runs": []}


class TestLedgerAppend:
    def test_append_single_run(self, tmp_ledger):
        entry = {
            "tree_sha": "abc123ef",
            "cycle": 1,
            "timestamp": "2026-03-30T14:22:03Z",
            "mode": "code",
            "worker_branch": "worktree/worker-b",
            "verdict": "fail",
            "roster": ["claude", "codex", "gemini"],
            "debrief_model": "claude",
            "findings_total": 5,
            "findings_convergent": 2,
            "findings_divergent": 3,
            "by_severity": {"critical": 0, "major": 1, "minor": 4},
            "tokens": {
                "total": 12840,
                "by_model": {"claude": 4310, "codex": 3920, "gemini": 4610},
            },
            "wall_time_ms": 18400,
            "diff_stats": {"files": 4, "insertions": 127, "deletions": 23},
            "remediation_cycle": 1,
            "dispositions": {},
        }
        tmp_ledger.append(entry)
        data = tmp_ledger.load()
        assert len(data["runs"]) == 1
        assert data["runs"][0]["tree_sha"] == "abc123ef"

    def test_append_preserves_existing(self, tmp_ledger):
        entry1 = {"tree_sha": "aaa", "cycle": 1, "verdict": "pass"}
        entry2 = {"tree_sha": "bbb", "cycle": 1, "verdict": "fail"}
        tmp_ledger.append(entry1)
        tmp_ledger.append(entry2)
        data = tmp_ledger.load()
        assert len(data["runs"]) == 2
        assert data["runs"][0]["tree_sha"] == "aaa"
        assert data["runs"][1]["tree_sha"] == "bbb"


class TestLedgerDisposition:
    def test_update_disposition(self, tmp_ledger):
        entry = {
            "tree_sha": "abc123ef",
            "cycle": 1,
            "verdict": "fail",
            "dispositions": {},
        }
        tmp_ledger.append(entry)
        tmp_ledger.update_disposition("abc123ef", 1, "v-001", "fixed")
        data = tmp_ledger.load()
        assert data["runs"][0]["dispositions"]["v-001"] == "fixed"

    def test_update_disposition_nonexistent_run(self, tmp_ledger):
        with pytest.raises(ValueError, match="not found"):
            tmp_ledger.update_disposition("nonexistent", 1, "v-001", "fixed")


class TestLedgerQuery:
    def test_find_run(self, tmp_ledger):
        entry = {"tree_sha": "abc123ef", "cycle": 1, "verdict": "pass"}
        tmp_ledger.append(entry)
        run = tmp_ledger.find_run("abc123ef", 1)
        assert run["verdict"] == "pass"

    def test_find_run_missing(self, tmp_ledger):
        assert tmp_ledger.find_run("missing", 1) is None

    def test_runs_for_branch(self, tmp_ledger):
        tmp_ledger.append({"tree_sha": "a", "cycle": 1, "worker_branch": "wb"})
        tmp_ledger.append({"tree_sha": "b", "cycle": 1, "worker_branch": "wb"})
        tmp_ledger.append({"tree_sha": "c", "cycle": 1, "worker_branch": "other"})
        runs = tmp_ledger.runs_for_branch("wb")
        assert len(runs) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mrkai/code/sortie && python3 -m pytest tests/test_ledger.py -v`
Expected: FAIL -- `ModuleNotFoundError: No module named 'scripts.ledger'`

- [ ] **Step 3: Write the ledger module**

```python
# scripts/ledger.py
"""Append-only YAML ledger for sortie run data."""

import os
from typing import Any

import yaml


class Ledger:
    def __init__(self, path: str):
        self.path = path

    def load(self) -> dict:
        """Load ledger from disk. Creates empty ledger if missing."""
        if not os.path.exists(self.path):
            self._write({"runs": []})
        with open(self.path, "r") as f:
            data = yaml.safe_load(f)
        if data is None:
            return {"runs": []}
        return data

    def append(self, entry: dict[str, Any]) -> None:
        """Append a run entry to the ledger."""
        data = self.load()
        data["runs"].append(entry)
        self._write(data)

    def find_run(self, tree_sha: str, cycle: int) -> dict | None:
        """Find a specific run by tree SHA and cycle."""
        data = self.load()
        for run in data["runs"]:
            if run.get("tree_sha") == tree_sha and run.get("cycle") == cycle:
                return run
        return None

    def runs_for_branch(self, worker_branch: str) -> list[dict]:
        """Find all runs for a given worker branch."""
        data = self.load()
        return [
            r for r in data["runs"] if r.get("worker_branch") == worker_branch
        ]

    def update_disposition(
        self, tree_sha: str, cycle: int, finding_id: str, disposition: str
    ) -> None:
        """Update the disposition of a finding in a specific run."""
        data = self.load()
        for run in data["runs"]:
            if run.get("tree_sha") == tree_sha and run.get("cycle") == cycle:
                if "dispositions" not in run:
                    run["dispositions"] = {}
                run["dispositions"][finding_id] = disposition
                self._write(data)
                return
        raise ValueError(
            f"Run {tree_sha}-{cycle} not found in ledger"
        )

    def _write(self, data: dict) -> None:
        """Write ledger data to disk."""
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mrkai/code/sortie && python3 -m pytest tests/test_ledger.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/mrkai/code/sortie
git add scripts/ledger.py tests/test_ledger.py
git commit -m "feat: ledger module -- append-only YAML run data store"
```

---

### Task 2: Config Module

**Files:**
- Create: `scripts/config.py`
- Create: `tests/test_config.py`

Loads `sortie.yaml`, resolves mode-level overrides against top-level defaults.

- [ ] **Step 1: Write failing tests for config**

```python
# tests/test_config.py
import os
import pytest
import yaml

from scripts.config import load_config, resolve_mode


MINIMAL_CONFIG = {
    "roster": [
        {"name": "claude", "invoke": "hook-agent", "prompt": "prompts/sortie-code.md", "timeout": 180},
    ],
    "debrief": {"model": "claude", "invoke": "hook-agent", "prompt": "prompts/debrief.md", "timeout": 120},
    "triage": {"block_on": ["critical", "major"], "max_remediation_cycles": 2, "convergence_threshold": 2},
    "modes": {
        "code": {"prompt": "prompts/sortie-code.md", "trigger": "merge", "roster": ["claude"]},
        "tests": {"prompt": "prompts/sortie-tests.md", "trigger": "milestone"},
    },
    "ledger": {"path": ".sortie/ledger.yaml"},
    "deposition": {"dir": ".sortie/{tree_sha}-{cycle}/", "keep_individual": True},
}


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "sortie.yaml"
    with open(path, "w") as f:
        yaml.dump(MINIMAL_CONFIG, f)
    return str(path)


class TestLoadConfig:
    def test_loads_valid_config(self, config_file):
        cfg = load_config(config_file)
        assert cfg["debrief"]["model"] == "claude"
        assert len(cfg["roster"]) == 1

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/sortie.yaml")

    def test_missing_required_key_raises(self, tmp_path):
        path = tmp_path / "sortie.yaml"
        with open(path, "w") as f:
            yaml.dump({"roster": []}, f)
        with pytest.raises(ValueError, match="debrief"):
            load_config(str(path))


class TestResolveMode:
    def test_mode_inherits_triage_defaults(self, config_file):
        cfg = load_config(config_file)
        resolved = resolve_mode(cfg, "tests")
        assert resolved["triage"]["max_remediation_cycles"] == 2
        assert resolved["triage"]["convergence_threshold"] == 2

    def test_mode_overrides_roster(self, config_file):
        cfg = load_config(config_file)
        resolved = resolve_mode(cfg, "code")
        assert resolved["roster_names"] == ["claude"]

    def test_mode_without_roster_inherits(self, config_file):
        cfg = load_config(config_file)
        resolved = resolve_mode(cfg, "tests")
        assert resolved["roster_names"] is None  # inherits from top-level

    def test_unknown_mode_raises(self, config_file):
        cfg = load_config(config_file)
        with pytest.raises(ValueError, match="Unknown mode"):
            resolve_mode(cfg, "nonexistent")

    def test_resolved_has_prompt(self, config_file):
        cfg = load_config(config_file)
        resolved = resolve_mode(cfg, "code")
        assert resolved["prompt"] == "prompts/sortie-code.md"

    def test_resolved_has_trigger(self, config_file):
        cfg = load_config(config_file)
        resolved = resolve_mode(cfg, "code")
        assert resolved["trigger"] == "merge"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mrkai/code/sortie && python3 -m pytest tests/test_config.py -v`
Expected: FAIL -- `ModuleNotFoundError`

- [ ] **Step 3: Write the config module**

```python
# scripts/config.py
"""Load and validate sortie.yaml, resolve mode-level overrides."""

from typing import Any

import yaml


REQUIRED_KEYS = ["roster", "debrief", "triage", "modes", "ledger", "deposition"]


def load_config(path: str) -> dict[str, Any]:
    """Load sortie.yaml and validate required keys are present."""
    with open(path, "r") as f:
        cfg = yaml.safe_load(f)
    if cfg is None:
        raise ValueError("Empty config file")
    for key in REQUIRED_KEYS:
        if key not in cfg:
            raise ValueError(f"Missing required config key: {key}")
    return cfg


def resolve_mode(cfg: dict, mode: str) -> dict[str, Any]:
    """Resolve a mode's config by merging with top-level defaults.

    Returns a dict with:
        prompt: str - the prompt file for this mode
        trigger: str - when this mode runs (merge, milestone)
        roster_names: list[str] | None - model names to use, or None to inherit top-level roster
        triage: dict - merged triage config (mode overrides top-level)
    """
    modes = cfg.get("modes", {})
    if mode not in modes:
        raise ValueError(f"Unknown mode: {mode}")

    mode_cfg = modes[mode]
    top_triage = cfg.get("triage", {})
    mode_triage = mode_cfg.get("triage", {})

    # Mode triage inherits top-level defaults, then overrides
    merged_triage = {**top_triage, **mode_triage}

    # Mode roster overrides top-level. None means inherit.
    roster_names = mode_cfg.get("roster")

    return {
        "prompt": mode_cfg["prompt"],
        "trigger": mode_cfg.get("trigger", "milestone"),
        "roster_names": roster_names,
        "triage": merged_triage,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mrkai/code/sortie && python3 -m pytest tests/test_config.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/mrkai/code/sortie
git add scripts/config.py tests/test_config.py
git commit -m "feat: config module -- load sortie.yaml with mode resolution"
```

---

### Task 3: Identity Module

**Files:**
- Create: `scripts/identity.py`
- Create: `tests/test_identity.py`

Tree hash computation, run ID generation, cycle counting.

- [ ] **Step 1: Write failing tests for identity**

```python
# tests/test_identity.py
import os
import pytest

from scripts.identity import get_tree_sha, next_cycle, run_id, run_dir


class TestGetTreeSha:
    def test_returns_hex_string(self, tmp_path, monkeypatch):
        """Tree SHA should be a hex string from git write-tree."""
        # Create a minimal git repo with staged content
        monkeypatch.chdir(tmp_path)
        os.system("git init")
        os.system("git config user.email test@test.com")
        os.system("git config user.name test")
        (tmp_path / "file.txt").write_text("hello")
        os.system("git add file.txt")
        sha = get_tree_sha(str(tmp_path))
        assert len(sha) == 40
        assert all(c in "0123456789abcdef" for c in sha)

    def test_same_content_same_sha(self, tmp_path, monkeypatch):
        """Same staged content produces same tree SHA."""
        monkeypatch.chdir(tmp_path)
        os.system("git init")
        os.system("git config user.email test@test.com")
        os.system("git config user.name test")
        (tmp_path / "file.txt").write_text("hello")
        os.system("git add file.txt")
        sha1 = get_tree_sha(str(tmp_path))
        sha2 = get_tree_sha(str(tmp_path))
        assert sha1 == sha2


class TestNextCycle:
    def test_first_cycle_is_1(self, tmp_path):
        assert next_cycle(str(tmp_path), "abc123ef") == 1

    def test_increments_after_existing(self, tmp_path):
        (tmp_path / "abc123ef-1").mkdir()
        assert next_cycle(str(tmp_path), "abc123ef") == 2

    def test_increments_multiple(self, tmp_path):
        (tmp_path / "abc123ef-1").mkdir()
        (tmp_path / "abc123ef-2").mkdir()
        assert next_cycle(str(tmp_path), "abc123ef") == 3

    def test_ignores_other_shas(self, tmp_path):
        (tmp_path / "other999-1").mkdir()
        assert next_cycle(str(tmp_path), "abc123ef") == 1


class TestRunId:
    def test_format(self):
        assert run_id("abc123ef", 1) == "abc123ef-1"
        assert run_id("abc123ef", 3) == "abc123ef-3"


class TestRunDir:
    def test_format(self):
        result = run_dir("/base/.sortie", "abc123ef", 1)
        assert result == "/base/.sortie/abc123ef-1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mrkai/code/sortie && python3 -m pytest tests/test_identity.py -v`
Expected: FAIL -- `ModuleNotFoundError`

- [ ] **Step 3: Write the identity module**

```python
# scripts/identity.py
"""Tree hash computation, run ID generation, cycle counting."""

import os
import subprocess


def get_tree_sha(repo_path: str) -> str:
    """Get the tree SHA of the current staging area via git write-tree."""
    result = subprocess.run(
        ["git", "write-tree"],
        cwd=repo_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def next_cycle(sortie_dir: str, tree_sha: str) -> int:
    """Determine the next cycle number for a tree SHA.

    Counts existing {tree_sha}-N directories and returns N+1.
    """
    if not os.path.exists(sortie_dir):
        return 1
    existing = [
        d
        for d in os.listdir(sortie_dir)
        if os.path.isdir(os.path.join(sortie_dir, d))
        and d.startswith(f"{tree_sha}-")
    ]
    return len(existing) + 1


def run_id(tree_sha: str, cycle: int) -> str:
    """Format a run ID from tree SHA and cycle."""
    return f"{tree_sha}-{cycle}"


def run_dir(sortie_dir: str, tree_sha: str, cycle: int) -> str:
    """Build the deposition directory path for a run."""
    return os.path.join(sortie_dir, run_id(tree_sha, cycle))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mrkai/code/sortie && python3 -m pytest tests/test_identity.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/mrkai/code/sortie
git add scripts/identity.py tests/test_identity.py
git commit -m "feat: identity module -- tree hash, run ID, cycle counting"
```

---

### Task 4: Attestation Module

**Files:**
- Create: `scripts/attestation.py`
- Create: `tests/test_attestation.py`

Write, read, and verify attestation YAML files.

- [ ] **Step 1: Write failing tests for attestation**

```python
# tests/test_attestation.py
import os
import pytest
import yaml

from scripts.attestation import write_attestation, read_attestation, verify_attestations


@pytest.fixture
def run_path(tmp_path):
    d = tmp_path / "abc123ef-1" / "attestations"
    d.mkdir(parents=True)
    return str(tmp_path / "abc123ef-1")


class TestWriteAttestation:
    def test_writes_yaml_file(self, run_path):
        write_attestation(
            run_path=run_path,
            step="sortie-claude",
            tree_sha="abc123ef",
            cycle=1,
            verdict="pass",
            findings_count={"critical": 0, "major": 0, "minor": 0},
            tokens={"prompt": 1000, "completion": 500},
            wall_time_ms=5000,
        )
        att_path = os.path.join(run_path, "attestations", "sortie-claude.yaml")
        assert os.path.exists(att_path)
        with open(att_path) as f:
            data = yaml.safe_load(f)
        assert data["step"] == "sortie-claude"
        assert data["verdict"] == "pass"
        assert data["tree_sha"] == "abc123ef"
        assert data["cycle"] == 1
        assert "timestamp" in data

    def test_writes_debrief_attestation(self, run_path):
        write_attestation(
            run_path=run_path,
            step="debrief",
            tree_sha="abc123ef",
            cycle=1,
            verdict="fail",
            findings_count={"critical": 1, "major": 0, "minor": 0},
            tokens={"prompt": 2000, "completion": 800},
            wall_time_ms=8000,
        )
        att_path = os.path.join(run_path, "attestations", "debrief.yaml")
        assert os.path.exists(att_path)


class TestReadAttestation:
    def test_reads_existing(self, run_path):
        write_attestation(
            run_path=run_path,
            step="sortie-claude",
            tree_sha="abc123ef",
            cycle=1,
            verdict="pass",
            findings_count={"critical": 0, "major": 0, "minor": 0},
            tokens={"prompt": 1000, "completion": 500},
            wall_time_ms=5000,
        )
        att = read_attestation(run_path, "sortie-claude")
        assert att["verdict"] == "pass"

    def test_returns_none_for_missing(self, run_path):
        assert read_attestation(run_path, "nonexistent") is None


class TestVerifyAttestations:
    def test_all_present_passes(self, run_path):
        for step in ["sortie-claude", "sortie-codex", "debrief"]:
            write_attestation(
                run_path=run_path,
                step=step,
                tree_sha="abc123ef",
                cycle=1,
                verdict="pass",
                findings_count={"critical": 0, "major": 0, "minor": 0},
                tokens={"prompt": 100, "completion": 50},
                wall_time_ms=1000,
            )
        missing = verify_attestations(
            run_path, ["sortie-claude", "sortie-codex", "debrief"]
        )
        assert missing == []

    def test_missing_attestation_reported(self, run_path):
        write_attestation(
            run_path=run_path,
            step="sortie-claude",
            tree_sha="abc123ef",
            cycle=1,
            verdict="pass",
            findings_count={"critical": 0, "major": 0, "minor": 0},
            tokens={"prompt": 100, "completion": 50},
            wall_time_ms=1000,
        )
        missing = verify_attestations(
            run_path, ["sortie-claude", "sortie-codex", "debrief"]
        )
        assert "sortie-codex" in missing
        assert "debrief" in missing
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mrkai/code/sortie && python3 -m pytest tests/test_attestation.py -v`
Expected: FAIL -- `ModuleNotFoundError`

- [ ] **Step 3: Write the attestation module**

```python
# scripts/attestation.py
"""Write, read, and verify attestation YAML files."""

import os
from datetime import datetime, timezone

import yaml


def write_attestation(
    run_path: str,
    step: str,
    tree_sha: str,
    cycle: int,
    verdict: str,
    findings_count: dict[str, int],
    tokens: dict[str, int],
    wall_time_ms: int,
) -> str:
    """Write an attestation YAML file for a sortie step.

    Returns the path to the written file.
    """
    att_dir = os.path.join(run_path, "attestations")
    os.makedirs(att_dir, exist_ok=True)

    data = {
        "step": step,
        "tree_sha": tree_sha,
        "cycle": cycle,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "findings_count": findings_count,
        "tokens": tokens,
        "wall_time_ms": wall_time_ms,
    }

    path = os.path.join(att_dir, f"{step}.yaml")
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    return path


def read_attestation(run_path: str, step: str) -> dict | None:
    """Read an attestation file. Returns None if not found."""
    path = os.path.join(run_path, "attestations", f"{step}.yaml")
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return yaml.safe_load(f)


def verify_attestations(run_path: str, required_steps: list[str]) -> list[str]:
    """Check which required attestations are missing.

    Returns a list of missing step names. Empty list means all present.
    """
    missing = []
    for step in required_steps:
        if read_attestation(run_path, step) is None:
            missing.append(step)
    return missing
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mrkai/code/sortie && python3 -m pytest tests/test_attestation.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/mrkai/code/sortie
git add scripts/attestation.py tests/test_attestation.py
git commit -m "feat: attestation module -- write, read, verify step attestations"
```

---

### Task 5: Invoker Module

**Files:**
- Create: `scripts/invoker.py`
- Create: `tests/test_invoker.py`

Fans out to roster models in parallel. Supports `cli` invocation (subprocess) and `hook-agent` (stubbed for now -- real hook integration depends on Claude Code runtime). Collects structured YAML output.

- [ ] **Step 1: Write failing tests for invoker**

```python
# tests/test_invoker.py
import os
import json
import pytest
import yaml

from scripts.invoker import (
    build_prompt,
    invoke_cli,
    invoke_all,
    parse_sortie_output,
    SortieResult,
)


SAMPLE_DIFF = """diff --git a/src/auth.ts b/src/auth.ts
index 1234567..abcdefg 100644
--- a/src/auth.ts
+++ b/src/auth.ts
@@ -40,6 +40,8 @@ function cacheToken(token: string) {
+  // BUG: no expiry check
+  cache.set('token', token);
"""

SAMPLE_YAML_OUTPUT = """findings:
  - id: f-001
    severity: major
    file: src/auth.ts
    line: 42
    category: security
    summary: "Token cached without expiry validation"
    detail: "The token is stored without checking expiry."

verdict: pass_with_findings
"""


class TestBuildPrompt:
    def test_appends_diff_to_prompt(self, tmp_path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("Review this code:\n\n## Context\nBranch: {branch}\n")
        result = build_prompt(str(prompt_file), SAMPLE_DIFF, branch="worktree/wb")
        assert "Review this code:" in result
        assert "worktree/wb" in result
        assert "BUG: no expiry check" in result

    def test_diff_separator(self, tmp_path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("Review:\n")
        result = build_prompt(str(prompt_file), SAMPLE_DIFF, branch="wb")
        assert "\n---\n" in result


class TestParseSortieOutput:
    def test_parses_valid_yaml(self):
        result = parse_sortie_output(SAMPLE_YAML_OUTPUT)
        assert result.verdict == "pass_with_findings"
        assert len(result.findings) == 1
        assert result.findings[0]["severity"] == "major"

    def test_handles_empty_findings(self):
        output = "findings: []\n\nverdict: pass\n"
        result = parse_sortie_output(output)
        assert result.verdict == "pass"
        assert result.findings == []

    def test_handles_malformed_output(self):
        result = parse_sortie_output("this is not yaml: [[[")
        assert result.verdict == "error"
        assert result.error is not None


class TestInvokeCli:
    def test_captures_stdout(self, tmp_path):
        """Use echo as a trivial CLI stand-in."""
        result = invoke_cli(
            command='echo "findings: []\\nverdict: pass"',
            stdin_text=None,
            timeout=10,
            cwd=str(tmp_path),
        )
        assert result.returncode == 0
        assert "findings" in result.stdout

    def test_timeout_returns_error(self, tmp_path):
        result = invoke_cli(
            command="sleep 10",
            stdin_text=None,
            timeout=1,
            cwd=str(tmp_path),
        )
        assert result.returncode != 0
        assert result.timed_out


class TestInvokeAll:
    def test_parallel_execution(self, tmp_path):
        """Two echo-based roster entries should both return results."""
        roster = [
            {
                "name": "model-a",
                "invoke": "cli",
                "command": f'echo "findings: []\\nverdict: pass"',
                "timeout": 10,
            },
            {
                "name": "model-b",
                "invoke": "cli",
                "command": f'echo "findings: []\\nverdict: pass"',
                "timeout": 10,
            },
        ]
        results = invoke_all(
            roster=roster,
            diff=SAMPLE_DIFF,
            prompt_path=None,
            branch="wb",
            cwd=str(tmp_path),
        )
        assert len(results) == 2
        assert "model-a" in results
        assert "model-b" in results
        assert results["model-a"].verdict == "pass"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mrkai/code/sortie && python3 -m pytest tests/test_invoker.py -v`
Expected: FAIL -- `ModuleNotFoundError`

- [ ] **Step 3: Write the invoker module**

```python
# scripts/invoker.py
"""Fan out review prompts to roster models in parallel, collect results."""

import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

import yaml


@dataclass
class CliResult:
    stdout: str
    stderr: str
    returncode: int
    timed_out: bool = False


@dataclass
class SortieResult:
    model: str
    verdict: str
    findings: list[dict] = field(default_factory=list)
    tokens: dict[str, int] = field(default_factory=dict)
    wall_time_ms: int = 0
    raw_output: str = ""
    error: str | None = None


def build_prompt(prompt_path: str, diff: str, branch: str = "") -> str:
    """Read prompt file, substitute variables, append diff."""
    with open(prompt_path, "r") as f:
        template = f.read()
    prompt = template.replace("{branch}", branch)
    return f"{prompt}\n---\n\n```diff\n{diff}\n```\n"


def parse_sortie_output(raw: str) -> SortieResult:
    """Parse YAML output from a sortie model into a SortieResult."""
    try:
        data = yaml.safe_load(raw)
        if not isinstance(data, dict):
            return SortieResult(
                model="unknown",
                verdict="error",
                error=f"Expected dict, got {type(data).__name__}",
                raw_output=raw,
            )
        return SortieResult(
            model="unknown",
            verdict=data.get("verdict", "error"),
            findings=data.get("findings", []),
            raw_output=raw,
        )
    except yaml.YAMLError as e:
        return SortieResult(
            model="unknown",
            verdict="error",
            error=f"YAML parse error: {e}",
            raw_output=raw,
        )


def invoke_cli(
    command: str,
    stdin_text: str | None,
    timeout: int,
    cwd: str,
) -> CliResult:
    """Run a CLI command, optionally piping stdin. Returns CliResult."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            input=stdin_text,
        )
        return CliResult(
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )
    except subprocess.TimeoutExpired:
        return CliResult(
            stdout="",
            stderr=f"Command timed out after {timeout}s",
            returncode=-1,
            timed_out=True,
        )


def _invoke_single(
    entry: dict,
    diff: str,
    prompt_path: str | None,
    branch: str,
    cwd: str,
) -> SortieResult:
    """Invoke a single roster entry and return its SortieResult."""
    import time

    name = entry["name"]
    invoke_method = entry["invoke"]
    timeout = entry.get("timeout", 180)
    start = time.monotonic()

    if invoke_method == "cli":
        command = entry.get("command", "")
        entry_prompt = entry.get("prompt", prompt_path)

        if entry_prompt:
            stdin_text = build_prompt(entry_prompt, diff, branch)
            cli_result = invoke_cli(command, stdin_text, timeout, cwd)
        else:
            # CLI uses its own review logic, no stdin prompt
            cli_result = invoke_cli(command, None, timeout, cwd)

        elapsed_ms = int((time.monotonic() - start) * 1000)

        if cli_result.timed_out:
            return SortieResult(
                model=name,
                verdict="error",
                error=f"Timed out after {timeout}s",
                wall_time_ms=elapsed_ms,
            )

        if cli_result.returncode != 0 and not cli_result.stdout.strip():
            return SortieResult(
                model=name,
                verdict="error",
                error=f"Exit {cli_result.returncode}: {cli_result.stderr}",
                wall_time_ms=elapsed_ms,
                raw_output=cli_result.stderr,
            )

        parsed = parse_sortie_output(cli_result.stdout)
        parsed.model = name
        parsed.wall_time_ms = elapsed_ms
        return parsed

    elif invoke_method == "hook-agent":
        # hook-agent is invoked within Claude Code runtime.
        # Outside that runtime, treat as a no-op with a clear message.
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return SortieResult(
            model=name,
            verdict="error",
            error="hook-agent invocation requires Claude Code runtime",
            wall_time_ms=elapsed_ms,
        )

    else:
        return SortieResult(
            model=name,
            verdict="error",
            error=f"Unknown invoke method: {invoke_method}",
        )


def invoke_all(
    roster: list[dict],
    diff: str,
    prompt_path: str | None,
    branch: str,
    cwd: str,
) -> dict[str, SortieResult]:
    """Invoke all roster entries in parallel. Returns {model_name: SortieResult}."""
    results = {}
    with ThreadPoolExecutor(max_workers=len(roster)) as executor:
        futures = {
            executor.submit(
                _invoke_single, entry, diff, prompt_path, branch, cwd
            ): entry["name"]
            for entry in roster
        }
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception as e:
                results[name] = SortieResult(
                    model=name,
                    verdict="error",
                    error=str(e),
                )
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mrkai/code/sortie && python3 -m pytest tests/test_invoker.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/mrkai/code/sortie
git add scripts/invoker.py tests/test_invoker.py
git commit -m "feat: invoker module -- parallel model fan-out with CLI and hook-agent support"
```

---

### Task 6: Debrief Module

**Files:**
- Create: `scripts/debrief.py`
- Create: `tests/test_debrief.py`

Feeds individual sortie outputs to the debrief model. Writes `verdict.yaml`.

- [ ] **Step 1: Write failing tests for debrief**

```python
# tests/test_debrief.py
import os
import pytest
import yaml

from scripts.debrief import build_debrief_prompt, write_verdict, load_sortie_outputs
from scripts.invoker import SortieResult


SORTIE_CLAUDE = SortieResult(
    model="claude",
    verdict="pass_with_findings",
    findings=[
        {"id": "f-001", "severity": "major", "file": "auth.ts", "line": 42,
         "category": "security", "summary": "Token expiry not checked"},
    ],
)

SORTIE_GEMINI = SortieResult(
    model="gemini",
    verdict="pass_with_findings",
    findings=[
        {"id": "gf-001", "severity": "major", "file": "auth.ts", "line": 40,
         "category": "security", "summary": "Cached token may be expired"},
        {"id": "gf-002", "severity": "minor", "file": "types.ts", "line": 10,
         "category": "quality", "summary": "Unused type export"},
    ],
)


class TestBuildDebriefPrompt:
    def test_includes_all_sortie_outputs(self, tmp_path):
        prompt_file = tmp_path / "debrief.md"
        prompt_file.write_text("Synthesize {n} reviews:\n{sortie_outputs}\n")
        results = {"claude": SORTIE_CLAUDE, "gemini": SORTIE_GEMINI}
        prompt = build_debrief_prompt(str(prompt_file), results, "abc123ef", "wb")
        assert "claude" in prompt
        assert "gemini" in prompt
        assert "Token expiry" in prompt
        assert "Cached token" in prompt

    def test_substitutes_n(self, tmp_path):
        prompt_file = tmp_path / "debrief.md"
        prompt_file.write_text("Reviews from {n} models:\n{sortie_outputs}\n")
        results = {"claude": SORTIE_CLAUDE}
        prompt = build_debrief_prompt(str(prompt_file), results, "abc123ef", "wb")
        assert "1 models" in prompt


class TestWriteVerdict:
    def test_writes_verdict_yaml(self, tmp_path):
        run_path = str(tmp_path / "abc123ef-1")
        os.makedirs(run_path)
        verdict_data = {
            "tree_sha": "abc123ef",
            "cycle": 1,
            "worker_branch": "wb",
            "mode": "code",
            "verdict": "fail",
            "debrief_model": "claude",
            "findings": [
                {"id": "v-001", "severity": "major", "convergence": "convergent",
                 "sources": ["f-001", "gf-001"], "file": "auth.ts", "line": 42,
                 "category": "security", "summary": "Token expiry",
                 "detail": "...", "disposition": None},
            ],
        }
        path = write_verdict(run_path, verdict_data)
        assert os.path.exists(path)
        with open(path) as f:
            loaded = yaml.safe_load(f)
        assert loaded["verdict"] == "fail"
        assert len(loaded["findings"]) == 1


class TestLoadSortieOutputs:
    def test_loads_existing_yamls(self, tmp_path):
        run_path = tmp_path / "abc123ef-1"
        run_path.mkdir()
        data = {"model": "claude", "findings": [], "verdict": "pass"}
        with open(run_path / "sortie-claude.yaml", "w") as f:
            yaml.dump(data, f)
        outputs = load_sortie_outputs(str(run_path))
        assert "claude" in outputs
        assert outputs["claude"]["verdict"] == "pass"

    def test_ignores_non_sortie_files(self, tmp_path):
        run_path = tmp_path / "abc123ef-1"
        run_path.mkdir()
        (run_path / "verdict.yaml").write_text("verdict: pass\n")
        (run_path / "sortie-claude.yaml").write_text("model: claude\nverdict: pass\n")
        outputs = load_sortie_outputs(str(run_path))
        assert "claude" in outputs
        assert len(outputs) == 1  # verdict.yaml excluded
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mrkai/code/sortie && python3 -m pytest tests/test_debrief.py -v`
Expected: FAIL -- `ModuleNotFoundError`

- [ ] **Step 3: Write the debrief module**

```python
# scripts/debrief.py
"""Debrief: feed sortie outputs to synthesis model, write verdict."""

import os

import yaml

from scripts.invoker import SortieResult


def build_debrief_prompt(
    prompt_path: str,
    sortie_results: dict[str, SortieResult],
    tree_sha: str,
    branch: str,
) -> str:
    """Build the debrief prompt with all sortie outputs embedded."""
    with open(prompt_path, "r") as f:
        template = f.read()

    # Format each sortie's output as a labeled YAML block
    sections = []
    for name, result in sortie_results.items():
        output_yaml = yaml.dump(
            {"model": name, "verdict": result.verdict, "findings": result.findings},
            default_flow_style=False,
            sort_keys=False,
        )
        sections.append(f"### {name}\n\n```yaml\n{output_yaml}```\n")

    sortie_outputs = "\n".join(sections)

    prompt = template.replace("{n}", str(len(sortie_results)))
    prompt = prompt.replace("{sortie_outputs}", sortie_outputs)
    prompt = prompt.replace("{tree_sha}", tree_sha)
    prompt = prompt.replace("{branch}", branch)
    return prompt


def write_verdict(run_path: str, verdict_data: dict) -> str:
    """Write verdict.yaml to the run directory."""
    path = os.path.join(run_path, "verdict.yaml")
    with open(path, "w") as f:
        yaml.dump(verdict_data, f, default_flow_style=False, sort_keys=False)
    return path


def load_sortie_outputs(run_path: str) -> dict[str, dict]:
    """Load all sortie-*.yaml files from a run directory.

    Returns {model_name: parsed_yaml_dict}.
    """
    outputs = {}
    for filename in os.listdir(run_path):
        if filename.startswith("sortie-") and filename.endswith(".yaml"):
            model_name = filename[len("sortie-") : -len(".yaml")]
            with open(os.path.join(run_path, filename), "r") as f:
                data = yaml.safe_load(f)
            outputs[model_name] = data
    return outputs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mrkai/code/sortie && python3 -m pytest tests/test_debrief.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/mrkai/code/sortie
git add scripts/debrief.py tests/test_debrief.py
git commit -m "feat: debrief module -- synthesis prompt building and verdict writing"
```

---

### Task 7: Triage Module

**Files:**
- Create: `scripts/triage.py`
- Create: `tests/test_triage.py`

Severity-gated triage logic. Reads verdict, determines pass/fail/pass-with-findings, returns exit code.

- [ ] **Step 1: Write failing tests for triage**

```python
# tests/test_triage.py
import pytest

from scripts.triage import triage_verdict, TriageResult


class TestTriageVerdict:
    def test_pass_clean(self):
        verdict = {"verdict": "pass", "findings": []}
        triage_cfg = {"block_on": ["critical", "major"], "convergence_threshold": 2}
        result = triage_verdict(verdict, triage_cfg)
        assert result.action == "merge"
        assert result.exit_code == 0

    def test_fail_on_convergent_major(self):
        verdict = {
            "verdict": "fail",
            "findings": [
                {"id": "v-001", "severity": "major", "convergence": "convergent"},
            ],
        }
        triage_cfg = {"block_on": ["critical", "major"], "convergence_threshold": 2}
        result = triage_verdict(verdict, triage_cfg)
        assert result.action == "block"
        assert result.exit_code == 1

    def test_pass_with_minor_only(self):
        verdict = {
            "verdict": "pass_with_findings",
            "findings": [
                {"id": "v-001", "severity": "minor", "convergence": "convergent"},
            ],
        }
        triage_cfg = {"block_on": ["critical", "major"], "convergence_threshold": 2}
        result = triage_verdict(verdict, triage_cfg)
        assert result.action == "merge_with_findings"
        assert result.exit_code == 2

    def test_divergent_never_blocks(self):
        """Even a critical divergent finding should not block."""
        verdict = {
            "verdict": "pass_with_findings",
            "findings": [
                {"id": "v-001", "severity": "critical", "convergence": "divergent"},
            ],
        }
        triage_cfg = {"block_on": ["critical", "major"], "convergence_threshold": 2}
        result = triage_verdict(verdict, triage_cfg)
        assert result.action == "merge_with_findings"

    def test_loosened_triage(self):
        """With block_on=[critical] only, major findings don't block."""
        verdict = {
            "verdict": "fail",
            "findings": [
                {"id": "v-001", "severity": "major", "convergence": "convergent"},
            ],
        }
        triage_cfg = {"block_on": ["critical"], "convergence_threshold": 2}
        result = triage_verdict(verdict, triage_cfg)
        assert result.action == "merge_with_findings"

    def test_empty_block_on_never_blocks(self):
        """Docs mode: block_on=[] means advisory only."""
        verdict = {
            "verdict": "fail",
            "findings": [
                {"id": "v-001", "severity": "critical", "convergence": "convergent"},
            ],
        }
        triage_cfg = {"block_on": [], "convergence_threshold": 2}
        result = triage_verdict(verdict, triage_cfg)
        assert result.action == "merge_with_findings"

    def test_blocking_findings_listed(self):
        verdict = {
            "verdict": "fail",
            "findings": [
                {"id": "v-001", "severity": "major", "convergence": "convergent"},
                {"id": "v-002", "severity": "minor", "convergence": "convergent"},
            ],
        }
        triage_cfg = {"block_on": ["critical", "major"], "convergence_threshold": 2}
        result = triage_verdict(verdict, triage_cfg)
        assert result.action == "block"
        assert "v-001" in [f["id"] for f in result.blocking_findings]
        assert "v-002" not in [f["id"] for f in result.blocking_findings]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mrkai/code/sortie && python3 -m pytest tests/test_triage.py -v`
Expected: FAIL -- `ModuleNotFoundError`

- [ ] **Step 3: Write the triage module**

```python
# scripts/triage.py
"""Severity-gated triage: verdict -> action + exit code."""

from dataclasses import dataclass, field


@dataclass
class TriageResult:
    action: str  # "merge", "merge_with_findings", "block"
    exit_code: int  # 0=pass, 1=fail, 2=pass_with_findings
    blocking_findings: list[dict] = field(default_factory=list)
    advisory_findings: list[dict] = field(default_factory=list)


def triage_verdict(verdict: dict, triage_cfg: dict) -> TriageResult:
    """Apply severity-gated triage to a verdict.

    Only convergent findings can block. Divergent findings are always advisory.
    block_on list determines which severities trigger a block.
    """
    block_on = set(triage_cfg.get("block_on", []))
    findings = verdict.get("findings", [])

    blocking = []
    advisory = []

    for f in findings:
        convergence = f.get("convergence", "divergent")
        severity = f.get("severity", "minor")

        if convergence == "convergent" and severity in block_on:
            blocking.append(f)
        else:
            advisory.append(f)

    if blocking:
        return TriageResult(
            action="block",
            exit_code=1,
            blocking_findings=blocking,
            advisory_findings=advisory,
        )
    elif advisory:
        return TriageResult(
            action="merge_with_findings",
            exit_code=2,
            blocking_findings=[],
            advisory_findings=advisory,
        )
    else:
        return TriageResult(
            action="merge",
            exit_code=0,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mrkai/code/sortie && python3 -m pytest tests/test_triage.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/mrkai/code/sortie
git add scripts/triage.py tests/test_triage.py
git commit -m "feat: triage module -- severity-gated verdict evaluation"
```

---

### Task 8: CLI Entry Point

**Files:**
- Create: `scripts/sortie.py`
- Create: `tests/test_sortie_cli.py`

Thin CLI that composes all modules. Subcommands: `pipeline`, `run`, `debrief`, `status`, `dispose`.

- [ ] **Step 1: Write failing tests for CLI**

```python
# tests/test_sortie_cli.py
import os
import subprocess
import pytest
import yaml


SORTIE_DIR = os.path.join(os.path.dirname(__file__), "..")


class TestSortieCliHelp:
    def test_help_prints_usage(self):
        result = subprocess.run(
            ["python3", "scripts/sortie.py", "--help"],
            capture_output=True,
            text=True,
            cwd=SORTIE_DIR,
        )
        assert result.returncode == 0
        assert "pipeline" in result.stdout
        assert "status" in result.stdout
        assert "dispose" in result.stdout

    def test_unknown_subcommand_fails(self):
        result = subprocess.run(
            ["python3", "scripts/sortie.py", "nonexistent"],
            capture_output=True,
            text=True,
            cwd=SORTIE_DIR,
        )
        assert result.returncode != 0


class TestSortieStatus:
    def test_status_no_runs(self, tmp_path):
        cfg_path = tmp_path / "sortie.yaml"
        cfg_path.write_text(yaml.dump({
            "roster": [],
            "debrief": {"model": "claude", "invoke": "hook-agent", "prompt": "p.md", "timeout": 60},
            "triage": {"block_on": [], "max_remediation_cycles": 2, "convergence_threshold": 2},
            "modes": {"code": {"prompt": "p.md", "trigger": "merge"}},
            "ledger": {"path": str(tmp_path / ".sortie" / "ledger.yaml")},
            "deposition": {"dir": str(tmp_path / ".sortie") + "/{tree_sha}-{cycle}/", "keep_individual": True},
        }))
        result = subprocess.run(
            ["python3", os.path.join(SORTIE_DIR, "scripts", "sortie.py"),
             "status", "--config", str(cfg_path)],
            capture_output=True,
            text=True,
            cwd=SORTIE_DIR,
        )
        assert result.returncode == 0
        assert "No runs" in result.stdout or "0 runs" in result.stdout


class TestSortieDispose:
    def test_dispose_updates_verdict_and_ledger(self, tmp_path):
        # Set up a minimal run with verdict and ledger
        sortie_dir = tmp_path / ".sortie"
        run_path = sortie_dir / "abc123ef-1"
        run_path.mkdir(parents=True)

        verdict_data = {
            "tree_sha": "abc123ef",
            "cycle": 1,
            "verdict": "fail",
            "findings": [
                {"id": "v-001", "severity": "major", "disposition": None},
            ],
        }
        with open(run_path / "verdict.yaml", "w") as f:
            yaml.dump(verdict_data, f)

        ledger_data = {
            "runs": [
                {"tree_sha": "abc123ef", "cycle": 1, "verdict": "fail", "dispositions": {}},
            ]
        }
        with open(sortie_dir / "ledger.yaml", "w") as f:
            yaml.dump(ledger_data, f)

        cfg_path = tmp_path / "sortie.yaml"
        cfg_path.write_text(yaml.dump({
            "roster": [],
            "debrief": {"model": "claude", "invoke": "hook-agent", "prompt": "p.md", "timeout": 60},
            "triage": {"block_on": [], "max_remediation_cycles": 2, "convergence_threshold": 2},
            "modes": {"code": {"prompt": "p.md", "trigger": "merge"}},
            "ledger": {"path": str(sortie_dir / "ledger.yaml")},
            "deposition": {"dir": str(sortie_dir) + "/{tree_sha}-{cycle}/", "keep_individual": True},
        }))

        result = subprocess.run(
            ["python3", os.path.join(SORTIE_DIR, "scripts", "sortie.py"),
             "dispose", "abc123ef-1", "v-001", "fixed",
             "--config", str(cfg_path)],
            capture_output=True,
            text=True,
            cwd=SORTIE_DIR,
        )
        assert result.returncode == 0

        # Verify verdict updated
        with open(run_path / "verdict.yaml") as f:
            updated = yaml.safe_load(f)
        assert updated["findings"][0]["disposition"] == "fixed"

        # Verify ledger updated
        with open(sortie_dir / "ledger.yaml") as f:
            ledger = yaml.safe_load(f)
        assert ledger["runs"][0]["dispositions"]["v-001"] == "fixed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mrkai/code/sortie && python3 -m pytest tests/test_sortie_cli.py -v`
Expected: FAIL -- script doesn't exist

- [ ] **Step 3: Write the CLI entry point**

```python
#!/usr/bin/env python3
# scripts/sortie.py
"""Sortie CLI -- async adversarial review for swarm workflows."""

import argparse
import os
import sys
import time

import yaml

from scripts.config import load_config, resolve_mode
from scripts.identity import get_tree_sha, next_cycle, run_id, run_dir
from scripts.attestation import write_attestation, verify_attestations
from scripts.invoker import invoke_all, SortieResult
from scripts.debrief import (
    build_debrief_prompt,
    write_verdict,
    load_sortie_outputs,
)
from scripts.triage import triage_verdict
from scripts.ledger import Ledger


def get_diff(branch: str, cwd: str) -> str:
    """Get the diff of a branch against main."""
    import subprocess

    result = subprocess.run(
        ["git", "diff", "main...", branch],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    return result.stdout


def get_diff_stats(branch: str, cwd: str) -> dict:
    """Get diff statistics for a branch."""
    import subprocess

    result = subprocess.run(
        ["git", "diff", "--stat", "--numstat", "main...", branch],
        capture_output=True,
        text=True,
        cwd=cwd,
    )
    files = 0
    insertions = 0
    deletions = 0
    for line in result.stdout.strip().split("\n"):
        parts = line.split("\t")
        if len(parts) == 3:
            try:
                insertions += int(parts[0])
                deletions += int(parts[1])
                files += 1
            except ValueError:
                pass
    return {"files": files, "insertions": insertions, "deletions": deletions}


def write_sortie_output(run_path: str, name: str, result: SortieResult) -> None:
    """Write an individual sortie result as YAML."""
    data = {
        "model": result.model,
        "verdict": result.verdict,
        "findings": result.findings,
    }
    path = os.path.join(run_path, f"sortie-{name}.yaml")
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def cmd_pipeline(args, cfg):
    """Full pipeline: run all sorties + debrief + triage."""
    cwd = os.getcwd()
    mode_cfg = resolve_mode(cfg, args.mode)

    # Get diff
    diff = get_diff(args.branch, cwd)
    if not diff.strip():
        print(f"No diff found for branch {args.branch} against main.")
        return 0

    diff_stats = get_diff_stats(args.branch, cwd)

    # Resolve roster
    roster_names = mode_cfg["roster_names"]
    if roster_names:
        roster = [r for r in cfg["roster"] if r["name"] in roster_names]
    else:
        roster = cfg["roster"]

    if not roster:
        print("No models in roster for this mode.")
        return 1

    # Identity
    sortie_dir_template = cfg["deposition"]["dir"]
    base_sortie_dir = os.path.dirname(
        sortie_dir_template.replace("{tree_sha}", "x").replace("{cycle}", "1")
    )
    os.makedirs(base_sortie_dir, exist_ok=True)

    tree_sha = get_tree_sha(cwd)
    tree_sha_short = tree_sha[:8]
    cycle = next_cycle(base_sortie_dir, tree_sha_short)
    current_run_dir = run_dir(base_sortie_dir, tree_sha_short, cycle)
    os.makedirs(current_run_dir, exist_ok=True)
    os.makedirs(os.path.join(current_run_dir, "attestations"), exist_ok=True)

    print(f"Sortie {tree_sha_short}-{cycle} | mode={args.mode} | roster={[r['name'] for r in roster]}")

    # Invoke all sorties in parallel
    start = time.monotonic()
    results = invoke_all(
        roster=roster,
        diff=diff,
        prompt_path=mode_cfg["prompt"],
        branch=args.branch,
        cwd=cwd,
    )
    total_wall_ms = int((time.monotonic() - start) * 1000)

    # Write individual outputs and attestations
    total_tokens = {}
    for name, result in results.items():
        write_sortie_output(current_run_dir, name, result)

        severity_counts = {"critical": 0, "major": 0, "minor": 0}
        for f in result.findings:
            sev = f.get("severity", "minor")
            if sev in severity_counts:
                severity_counts[sev] += 1

        write_attestation(
            run_path=current_run_dir,
            step=f"sortie-{name}",
            tree_sha=tree_sha_short,
            cycle=cycle,
            verdict=result.verdict,
            findings_count=severity_counts,
            tokens=result.tokens,
            wall_time_ms=result.wall_time_ms,
        )
        total_tokens[name] = sum(result.tokens.values()) if result.tokens else 0
        print(f"  {name}: {result.verdict} ({len(result.findings)} findings, {result.wall_time_ms}ms)")

    # Debrief
    debrief_cfg = cfg["debrief"]
    debrief_prompt = build_debrief_prompt(
        debrief_cfg["prompt"], results, tree_sha_short, args.branch
    )

    # For now, debrief uses the same invoke mechanism as a roster entry
    from scripts.invoker import _invoke_single

    debrief_entry = {
        "name": "debrief",
        "invoke": debrief_cfg["invoke"],
        "command": debrief_cfg.get("command", ""),
        "prompt": debrief_cfg["prompt"],
        "timeout": debrief_cfg.get("timeout", 120),
    }

    debrief_result = _invoke_single(
        debrief_entry, diff="", prompt_path=None, branch=args.branch, cwd=cwd
    )

    # If debrief returned a valid verdict, use it. Otherwise construct from individual results.
    if debrief_result.verdict != "error" and debrief_result.findings:
        verdict_data = {
            "tree_sha": tree_sha_short,
            "cycle": cycle,
            "worker_branch": args.branch,
            "mode": args.mode,
            "verdict": debrief_result.verdict,
            "debrief_model": debrief_cfg["model"],
            "findings": debrief_result.findings,
        }
    else:
        # Fallback: aggregate individual sortie findings (no convergence analysis)
        all_findings = []
        for name, result in results.items():
            for f in result.findings:
                f_copy = dict(f)
                f_copy["convergence"] = "divergent"
                f_copy["sources"] = [f.get("id", "unknown")]
                f_copy.setdefault("disposition", None)
                all_findings.append(f_copy)

        max_severity = "minor"
        for f in all_findings:
            sev = f.get("severity", "minor")
            if sev == "critical":
                max_severity = "critical"
                break
            elif sev == "major" and max_severity != "critical":
                max_severity = "major"

        if not all_findings:
            verdict_str = "pass"
        elif max_severity in ("critical", "major"):
            verdict_str = "fail"
        else:
            verdict_str = "pass_with_findings"

        verdict_data = {
            "tree_sha": tree_sha_short,
            "cycle": cycle,
            "worker_branch": args.branch,
            "mode": args.mode,
            "verdict": verdict_str,
            "debrief_model": debrief_cfg["model"],
            "findings": all_findings,
        }

    write_verdict(current_run_dir, verdict_data)

    # Attestation for debrief
    debrief_severity = {"critical": 0, "major": 0, "minor": 0}
    for f in verdict_data.get("findings", []):
        sev = f.get("severity", "minor")
        if sev in debrief_severity:
            debrief_severity[sev] += 1

    write_attestation(
        run_path=current_run_dir,
        step="debrief",
        tree_sha=tree_sha_short,
        cycle=cycle,
        verdict=verdict_data["verdict"],
        findings_count=debrief_severity,
        tokens=debrief_result.tokens,
        wall_time_ms=debrief_result.wall_time_ms,
    )

    # Triage
    triage_result = triage_verdict(verdict_data, mode_cfg["triage"])

    # Ledger
    ledger = Ledger(cfg["ledger"]["path"])
    ledger_entry = {
        "tree_sha": tree_sha_short,
        "cycle": cycle,
        "timestamp": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "mode": args.mode,
        "worker_branch": args.branch,
        "verdict": verdict_data["verdict"],
        "roster": [r["name"] for r in roster],
        "debrief_model": debrief_cfg["model"],
        "findings_total": len(verdict_data.get("findings", [])),
        "findings_convergent": sum(
            1
            for f in verdict_data.get("findings", [])
            if f.get("convergence") == "convergent"
        ),
        "findings_divergent": sum(
            1
            for f in verdict_data.get("findings", [])
            if f.get("convergence") == "divergent"
        ),
        "by_severity": debrief_severity,
        "tokens": {
            "total": sum(total_tokens.values()),
            "by_model": total_tokens,
        },
        "wall_time_ms": total_wall_ms,
        "diff_stats": diff_stats,
        "remediation_cycle": cycle,
        "dispositions": {},
    }
    ledger.append(ledger_entry)

    # Print verdict
    print(f"\nVerdict: {verdict_data['verdict'].upper()}")
    print(f"Action: {triage_result.action}")
    if triage_result.blocking_findings:
        print(f"Blocking findings ({len(triage_result.blocking_findings)}):")
        for f in triage_result.blocking_findings:
            print(f"  [{f['severity']}] {f.get('file', '?')}:{f.get('line', '?')} -- {f.get('summary', '')}")
    if triage_result.advisory_findings:
        print(f"Advisory findings ({len(triage_result.advisory_findings)}):")
        for f in triage_result.advisory_findings:
            print(f"  [{f['severity']}] {f.get('file', '?')}:{f.get('line', '?')} -- {f.get('summary', '')}")

    return triage_result.exit_code


def cmd_status(args, cfg):
    """Show current sortie state."""
    ledger = Ledger(cfg["ledger"]["path"])
    data = ledger.load()
    runs = data.get("runs", [])
    if not runs:
        print("No runs recorded.")
        return 0
    print(f"{len(runs)} runs recorded:\n")
    for run in runs[-10:]:  # Last 10
        print(
            f"  {run.get('tree_sha', '?')}-{run.get('cycle', '?')} "
            f"| {run.get('mode', '?')} "
            f"| {run.get('verdict', '?').upper()} "
            f"| {run.get('worker_branch', '?')} "
            f"| {run.get('findings_total', 0)} findings"
        )
    return 0


def cmd_dispose(args, cfg):
    """Annotate a finding's disposition."""
    # Parse run_id into tree_sha and cycle
    parts = args.run_id.rsplit("-", 1)
    if len(parts) != 2:
        print(f"Invalid run ID: {args.run_id} (expected format: tree_sha-cycle)")
        return 1
    tree_sha, cycle_str = parts
    try:
        cycle = int(cycle_str)
    except ValueError:
        print(f"Invalid cycle number: {cycle_str}")
        return 1

    valid_dispositions = ("fixed", "false-positive", "deferred", "disagree")
    if args.disposition not in valid_dispositions:
        print(f"Invalid disposition: {args.disposition}. Must be one of: {valid_dispositions}")
        return 1

    # Update verdict.yaml
    sortie_dir_template = cfg["deposition"]["dir"]
    base_sortie_dir = os.path.dirname(
        sortie_dir_template.replace("{tree_sha}", "x").replace("{cycle}", "1")
    )
    current_run_dir = run_dir(base_sortie_dir, tree_sha, cycle)
    verdict_path = os.path.join(current_run_dir, "verdict.yaml")

    if not os.path.exists(verdict_path):
        print(f"Verdict not found at {verdict_path}")
        return 1

    with open(verdict_path, "r") as f:
        verdict_data = yaml.safe_load(f)

    found = False
    for finding in verdict_data.get("findings", []):
        if finding.get("id") == args.finding_id:
            finding["disposition"] = args.disposition
            found = True
            break

    if not found:
        print(f"Finding {args.finding_id} not found in verdict.")
        return 1

    with open(verdict_path, "w") as f:
        yaml.dump(verdict_data, f, default_flow_style=False, sort_keys=False)

    # Update ledger
    ledger = Ledger(cfg["ledger"]["path"])
    ledger.update_disposition(tree_sha, cycle, args.finding_id, args.disposition)

    print(f"Disposed {args.finding_id} as '{args.disposition}' in {args.run_id}")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Sortie: async adversarial review for swarm workflows"
    )
    parser.add_argument(
        "--config",
        default="sortie.yaml",
        help="Path to sortie.yaml (default: sortie.yaml)",
    )
    subparsers = parser.add_subparsers(dest="command")

    # pipeline
    p_pipeline = subparsers.add_parser("pipeline", help="Full sortie pipeline")
    p_pipeline.add_argument("branch", help="Worker branch to review")
    p_pipeline.add_argument("--mode", default="code", help="Review mode (default: code)")

    # status
    subparsers.add_parser("status", help="Show sortie run status")

    # dispose
    p_dispose = subparsers.add_parser("dispose", help="Annotate finding disposition")
    p_dispose.add_argument("run_id", help="Run ID (tree_sha-cycle)")
    p_dispose.add_argument("finding_id", help="Finding ID (e.g., v-001)")
    p_dispose.add_argument("disposition", help="fixed|false-positive|deferred|disagree")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    cfg = load_config(args.config)

    if args.command == "pipeline":
        return cmd_pipeline(args, cfg)
    elif args.command == "status":
        return cmd_status(args, cfg)
    elif args.command == "dispose":
        return cmd_dispose(args, cfg)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mrkai/code/sortie && python3 -m pytest tests/test_sortie_cli.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/mrkai/code/sortie
git add scripts/sortie.py tests/test_sortie_cli.py
git commit -m "feat: CLI entry point -- pipeline, status, dispose subcommands"
```

---

### Task 9: Hook Module

**Files:**
- Create: `scripts/sortie_hook.py`
- Create: `tests/test_hook.py`
- Create: `hooks/settings.json`

Pre-merge gate for Claude Code.

- [ ] **Step 1: Write failing tests for hook**

```python
# tests/test_hook.py
import os
import json
import pytest
import yaml

from scripts.sortie_hook import check_pre_merge


@pytest.fixture
def sortie_env(tmp_path):
    """Set up a minimal .sortie directory with a run and verdict."""
    sortie_dir = tmp_path / ".sortie"
    run_path = sortie_dir / "abc123ef-1"
    run_path.mkdir(parents=True)
    return {
        "sortie_dir": str(sortie_dir),
        "run_path": str(run_path),
        "tree_sha": "abc123ef",
    }


class TestCheckPreMerge:
    def test_no_verdict_blocks(self, sortie_env):
        result = check_pre_merge(
            sortie_dir=sortie_env["sortie_dir"],
            tree_sha=sortie_env["tree_sha"],
        )
        assert result["ok"] is False
        assert "no verdict" in result["reason"].lower() or "not found" in result["reason"].lower()

    def test_passing_verdict_allows(self, sortie_env):
        verdict = {"verdict": "pass", "findings": []}
        with open(os.path.join(sortie_env["run_path"], "verdict.yaml"), "w") as f:
            yaml.dump(verdict, f)
        result = check_pre_merge(
            sortie_dir=sortie_env["sortie_dir"],
            tree_sha=sortie_env["tree_sha"],
        )
        assert result["ok"] is True

    def test_pass_with_findings_allows(self, sortie_env):
        verdict = {
            "verdict": "pass_with_findings",
            "findings": [{"id": "v-001", "severity": "minor"}],
        }
        with open(os.path.join(sortie_env["run_path"], "verdict.yaml"), "w") as f:
            yaml.dump(verdict, f)
        result = check_pre_merge(
            sortie_dir=sortie_env["sortie_dir"],
            tree_sha=sortie_env["tree_sha"],
        )
        assert result["ok"] is True

    def test_failing_verdict_blocks(self, sortie_env):
        verdict = {
            "verdict": "fail",
            "findings": [
                {"id": "v-001", "severity": "major", "file": "auth.ts",
                 "summary": "Token expiry not checked"},
            ],
        }
        with open(os.path.join(sortie_env["run_path"], "verdict.yaml"), "w") as f:
            yaml.dump(verdict, f)
        result = check_pre_merge(
            sortie_dir=sortie_env["sortie_dir"],
            tree_sha=sortie_env["tree_sha"],
        )
        assert result["ok"] is False
        assert "fail" in result["reason"].lower()

    def test_uses_latest_cycle(self, sortie_env):
        """If multiple cycles exist, use the latest."""
        # Cycle 1 fails
        verdict1 = {"verdict": "fail", "findings": [{"id": "v-001", "severity": "major"}]}
        with open(os.path.join(sortie_env["run_path"], "verdict.yaml"), "w") as f:
            yaml.dump(verdict1, f)

        # Cycle 2 passes
        run2 = os.path.join(sortie_env["sortie_dir"], "abc123ef-2")
        os.makedirs(run2)
        verdict2 = {"verdict": "pass", "findings": []}
        with open(os.path.join(run2, "verdict.yaml"), "w") as f:
            yaml.dump(verdict2, f)

        result = check_pre_merge(
            sortie_dir=sortie_env["sortie_dir"],
            tree_sha=sortie_env["tree_sha"],
        )
        assert result["ok"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mrkai/code/sortie && python3 -m pytest tests/test_hook.py -v`
Expected: FAIL -- `ModuleNotFoundError`

- [ ] **Step 3: Write the hook module**

```python
#!/usr/bin/env python3
# scripts/sortie_hook.py
"""Claude Code pre-merge hook: blocks merge if no passing sortie verdict exists."""

import json
import os
import sys

import yaml


def check_pre_merge(sortie_dir: str, tree_sha: str) -> dict:
    """Check if a passing verdict exists for the given tree SHA.

    Returns {"ok": True/False, "reason": "..."}.
    """
    tree_sha_short = tree_sha[:8] if len(tree_sha) > 8 else tree_sha

    # Find the latest cycle for this tree SHA
    if not os.path.exists(sortie_dir):
        return {
            "ok": False,
            "reason": f"No sortie directory found. Run `just sortie-all <branch>` before merging.",
        }

    cycles = sorted(
        [
            d
            for d in os.listdir(sortie_dir)
            if os.path.isdir(os.path.join(sortie_dir, d))
            and d.startswith(f"{tree_sha_short}-")
        ]
    )

    if not cycles:
        return {
            "ok": False,
            "reason": f"No verdict found for tree {tree_sha_short}. Run `just sortie-all <branch>` before merging.",
        }

    latest_run = os.path.join(sortie_dir, cycles[-1])
    verdict_path = os.path.join(latest_run, "verdict.yaml")

    if not os.path.exists(verdict_path):
        return {
            "ok": False,
            "reason": f"No verdict.yaml in {cycles[-1]}. Sortie may not have completed.",
        }

    with open(verdict_path, "r") as f:
        verdict = yaml.safe_load(f)

    verdict_str = verdict.get("verdict", "unknown")

    if verdict_str == "fail":
        findings = verdict.get("findings", [])
        summary_lines = []
        for f in findings[:5]:  # Show up to 5
            summary_lines.append(
                f"  [{f.get('severity', '?')}] {f.get('file', '?')}:{f.get('line', '?')} -- {f.get('summary', '')}"
            )
        summary = "\n".join(summary_lines)
        return {
            "ok": False,
            "reason": f"Sortie FAIL ({cycles[-1]}). Blocking findings:\n{summary}",
        }

    return {"ok": True, "reason": f"Sortie {verdict_str.upper()} ({cycles[-1]})."}


def main():
    """Entry point for Claude Code hook invocation.

    Reads tree SHA from git, checks for passing verdict.
    Prints result as text (stdout is injected into Claude's context).
    Exit 0 = allow, exit 2 = block.
    """
    import subprocess

    sortie_dir = os.path.join(os.getcwd(), ".sortie")

    # Get current tree SHA
    try:
        result = subprocess.run(
            ["git", "write-tree"],
            capture_output=True,
            text=True,
            check=True,
        )
        tree_sha = result.stdout.strip()
    except subprocess.CalledProcessError:
        print("Could not determine tree SHA. Allowing merge.")
        sys.exit(0)

    check = check_pre_merge(sortie_dir, tree_sha)
    print(check["reason"])
    sys.exit(0 if check["ok"] else 2)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mrkai/code/sortie && python3 -m pytest tests/test_hook.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Write the reference hook config**

```json
// hooks/settings.json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 scripts/sortie_hook.py pre-merge",
            "if": "Bash(git merge *)"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 6: Commit**

```bash
cd /Users/mrkai/code/sortie
git add scripts/sortie_hook.py tests/test_hook.py hooks/settings.json
git commit -m "feat: pre-merge hook -- blocks unreviewed worktree merges"
```

---

### Task 10: Prompts

**Files:**
- Create: `prompts/sortie-code.md`
- Create: `prompts/sortie-tests.md`
- Create: `prompts/sortie-docs.md`
- Create: `prompts/debrief.md`

No tests -- these are Markdown templates. Validation is via the invoker and debrief tests.

- [ ] **Step 1: Write the code review prompt**

```markdown
<!-- prompts/sortie-code.md -->
You are an adversarial code reviewer examining changes from a parallel worker
in a swarm development workflow. Your role is to find real issues, not to
nitpick style.

## Context

- Worker branch: {branch}
- The worker implemented their tasks independently in an isolated worktree
- Other workers are building adjacent modules concurrently
- Diff follows below

## Review for

1. **Correctness** -- logic errors, off-by-ones, missing edge cases, race conditions
2. **Security** -- injection, auth bypass, secret exposure, unsafe defaults
3. **Interface contracts** -- does this break assumptions other workers depend on?
4. **Error handling** -- unhandled failures, swallowed errors, missing retries
5. **Type safety** -- any casts, type assertions, or schema mismatches

## Do NOT review for

- Style, formatting, naming preferences
- Missing tests (tests are a separate worker's responsibility)
- Documentation gaps
- Performance unless it's a clear algorithmic issue (O(n^2) on large input)

## Output format

Return YAML exactly matching this schema. Nothing else -- no commentary, no markdown fences, just YAML:

findings:
  - id: f-NNN
    severity: critical | major | minor
    file: <path>
    line: <number>
    category: correctness | security | interface | error-handling | type-safety
    summary: <one line>
    detail: <explanation of the issue and why it matters>

verdict: pass | pass_with_findings | fail

If no findings, return empty findings list and verdict: pass.
```

- [ ] **Step 2: Write the test review prompt**

```markdown
<!-- prompts/sortie-tests.md -->
You are reviewing test code written by a parallel worker in a swarm workflow.
Your role is to find tests that create false confidence -- not missing tests,
but bad tests.

## Context

- Worker branch: {branch}
- The worker wrote tests for modules they implemented in isolation
- Diff follows below

## Review for

1. **False greens** -- tests that pass but don't actually verify the behavior they claim to
2. **Stub fidelity** -- do stubs/mocks match the real API? Would the test pass even if the real integration broke?
3. **Assertion quality** -- are assertions testing the right thing, or just `expect(result).toBeDefined()`?
4. **Missing edge cases** -- error paths, boundary values, empty inputs, concurrent scenarios
5. **Coverage gaps** -- code paths exercised by implementation but not by any test

## Do NOT review for

- Implementation quality (that's the code review's job)
- Style, naming, test organization preferences
- Framework-specific idioms

## Output format

Return YAML exactly matching this schema. Nothing else -- no commentary, no markdown fences, just YAML:

findings:
  - id: f-NNN
    severity: critical | major | minor
    file: <path>
    line: <number>
    category: false-green | stub-fidelity | assertion-quality | edge-case | coverage-gap
    summary: <one line>
    detail: <explanation>

verdict: pass | pass_with_findings | fail

If no findings, return empty findings list and verdict: pass.
```

- [ ] **Step 3: Write the docs review prompt**

```markdown
<!-- prompts/sortie-docs.md -->
You are reviewing documentation changes from a parallel worker in a swarm
workflow. Your role is to find inaccuracies -- not style issues.

## Context

- Worker branch: {branch}
- The worker wrote documentation alongside their implementation
- Other workers may have changed the code these docs reference
- Diff follows below

## Review for

1. **Accuracy** -- does the documentation match the actual code behavior?
2. **Missing steps** -- are there setup steps, prerequisites, or configuration that readers need but aren't documented?
3. **Stale references** -- do file paths, function names, or API endpoints mentioned actually exist?
4. **Internal contradictions** -- does the doc contradict itself or other docs in the same changeset?

## Do NOT review for

- Prose style, grammar, tone
- Formatting, markdown conventions
- Completeness of coverage (focus on accuracy of what IS written)

## Output format

Return YAML exactly matching this schema. Nothing else -- no commentary, no markdown fences, just YAML:

findings:
  - id: f-NNN
    severity: critical | major | minor
    file: <path>
    line: <number>
    category: accuracy | missing-steps | stale-reference | contradiction
    summary: <one line>
    detail: <explanation>

verdict: pass | pass_with_findings | fail

If no findings, return empty findings list and verdict: pass.
```

- [ ] **Step 4: Write the debrief prompt**

```markdown
<!-- prompts/debrief.md -->
You are synthesizing adversarial code reviews from {n} independent models
that reviewed the same diff. Your job is triangulation -- identify what's
real signal vs. model-specific noise.

## Inputs

{sortie_outputs}

## Tasks

1. **Map findings across models** -- identify when different models describe
   the same issue (same file, same concern, possibly different wording or
   line numbers). Two findings about "token expiry" in auth.ts from different
   models are the same issue even if they use different words.

2. **Score convergence:**
   - Convergent: 2+ models found the same issue --> high confidence, real problem
   - Divergent: 1 model only --> log but do not block. May be a false positive
     or may reveal a blind spot. Flag it either way.

3. **Assign final severity** per finding. You may upgrade (a minor that multiple
   models flagged may warrant major) or downgrade (a major that only one model
   found and seems speculative).

4. **Produce a single verdict** based on the highest severity of CONVERGENT
   findings only:
   - pass: no convergent findings
   - pass_with_findings: convergent findings are all minor
   - fail: any convergent finding is major or critical

## Output format

Return YAML exactly matching this schema. Nothing else -- no commentary, no markdown fences, just YAML:

tree_sha: {tree_sha}
worker_branch: {branch}
verdict: pass | pass_with_findings | fail
debrief_model: your_model_name
findings:
  - id: v-NNN
    severity: critical | major | minor
    convergence: convergent | divergent
    sources: [list of finding IDs from individual sorties that map to this issue]
    file: <path>
    line: <number>
    category: <category>
    summary: <one line>
    detail: <synthesized explanation combining insights from all models that found it>
    disposition: null
```

- [ ] **Step 5: Commit**

```bash
cd /Users/mrkai/code/sortie
git add prompts/
git commit -m "feat: review prompts -- code, tests, docs, and debrief synthesis"
```

---

### Task 11: Project Scaffolding

**Files:**
- Create: `sortie.yaml`
- Create: `justfile`
- Create: `.gitignore`
- Create: `CLAUDE.md`
- Create: `scripts/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Write sortie.yaml**

```yaml
# sortie.yaml -- Sortie configuration
# See docs/superpowers/specs/2026-03-30-sortie-design.md for full reference.

roster:
  - name: claude
    invoke: hook-agent
    prompt: prompts/sortie-code.md
    timeout: 180

  - name: codex
    invoke: cli
    command: "codex exec review --uncommitted"
    timeout: 180

  - name: gemini
    invoke: cli
    command: "gemini -p"
    prompt: prompts/sortie-code.md
    output_format: json
    timeout: 180

debrief:
  model: claude
  invoke: hook-agent
  prompt: prompts/debrief.md
  timeout: 120

triage:
  block_on:
    - critical
    - major
  max_remediation_cycles: 2
  convergence_threshold: 2

modes:
  code:
    prompt: prompts/sortie-code.md
    trigger: merge
    roster: [claude, codex, gemini]
    triage:
      block_on: [critical, major]

  tests:
    prompt: prompts/sortie-tests.md
    trigger: milestone
    roster: [claude, gemini]
    triage:
      block_on: [critical]

  docs:
    prompt: prompts/sortie-docs.md
    trigger: milestone
    roster: [claude]
    triage:
      block_on: []

ledger:
  path: .sortie/ledger.yaml
  capture:
    - findings
    - convergence
    - tokens
    - wall_time
    - diff_stats
    - disposition

deposition:
  dir: .sortie/{tree_sha}-{cycle}/
  keep_individual: true
```

- [ ] **Step 2: Write justfile**

```makefile
# justfile -- Sortie orchestration targets

# Full pipeline: parallel sorties + debrief + triage
sortie-all branch mode='code':
    python3 scripts/sortie.py pipeline {{branch}} --mode {{mode}}

# Show current sortie state
sortie-status:
    python3 scripts/sortie.py status

# Annotate finding disposition
sortie-dispose run_id finding_id disposition:
    python3 scripts/sortie.py dispose {{run_id}} {{finding_id}} {{disposition}}

# Run all tests
test:
    python3 -m pytest tests/ -v

# Run a single test file
test-one file:
    python3 -m pytest {{file}} -v
```

- [ ] **Step 3: Write .gitignore**

```gitignore
# .gitignore

# Sortie runtime artifacts (except ledger)
# Individual run directories are gitignored; ledger.yaml is tracked
.sortie/*/
!.sortie/ledger.yaml

# Python
__pycache__/
*.pyc
.pytest_cache/

# Environment
.env
.env.local
```

- [ ] **Step 4: Write CLAUDE.md**

```markdown
# CLAUDE.md

## Project

Sortie -- async adversarial review for Claude Code Teams swarm workflows.
Runs a configurable roster of LLMs against worker diffs at merge boundary,
synthesizes findings through debrief, triages by severity, gates merges.

Full spec: `docs/superpowers/specs/2026-03-30-sortie-design.md`

## Commands

```bash
# Run all tests
just test

# Run a single test file
just test-one tests/test_ledger.py

# Full sortie pipeline
just sortie-all <branch> [mode]

# Show run status
just sortie-status

# Annotate a finding
just sortie-dispose <run_id> <finding_id> <disposition>
```

## Architecture

```
scripts/
  sortie.py          # CLI entry point (pipeline, status, dispose)
  config.py          # Load sortie.yaml, resolve mode overrides
  identity.py        # Tree hash, run ID, cycle counting
  attestation.py     # Write/read/verify attestation YAML
  invoker.py         # Parallel model fan-out (cli, hook-agent)
  debrief.py         # Synthesis prompt building, verdict writing
  triage.py          # Severity-gated verdict evaluation
  ledger.py          # Append-only YAML run data store
  sortie_hook.py     # Claude Code pre-merge hook

prompts/             # Markdown review prompts (code, tests, docs, debrief)
.sortie/             # Runtime artifacts (gitignored except ledger.yaml)
```

## Key concepts

- **Tree hash identity**: `git write-tree` keys artifacts to staged content
- **Run ID**: `{tree_sha_8}-{cycle}` where cycle counts remediation attempts
- **Convergent finding**: 2+ models found the same issue (high confidence)
- **Divergent finding**: 1 model only (logged, never blocks)
- **Triage**: `block_on` in sortie.yaml controls which severities gate merges

## Dependencies

- Python 3.10+
- PyYAML (`pip install pyyaml`)
- pytest (`pip install pytest`)
```

- [ ] **Step 5: Write __init__.py files**

```python
# scripts/__init__.py
# (empty -- marks scripts as a package for pytest imports)
```

```python
# tests/__init__.py
# (empty -- marks tests as a package for pytest imports)
```

- [ ] **Step 6: Commit**

```bash
cd /Users/mrkai/code/sortie
git add sortie.yaml justfile .gitignore CLAUDE.md scripts/__init__.py tests/__init__.py
git commit -m "feat: project scaffolding -- config, justfile, gitignore, CLAUDE.md"
```

---

### Task 12: Integration Smoke Test

**Files:**
- Create: `tests/test_integration.py`

End-to-end test using echo-based CLI stubs to verify the full pipeline works.

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration.py
"""End-to-end smoke test: full pipeline with echo-based CLI stubs."""

import os
import subprocess
import pytest
import yaml


SORTIE_DIR = os.path.join(os.path.dirname(__file__), "..")

STUB_SORTIE_OUTPUT = """findings:
  - id: f-001
    severity: major
    file: src/auth.ts
    line: 42
    category: security
    summary: Token cached without expiry validation
    detail: The OAuth token is stored but expiry is not checked.

verdict: pass_with_findings
"""


@pytest.fixture
def integration_env(tmp_path):
    """Set up a git repo with a branch to review and a sortie config."""
    repo = tmp_path / "repo"
    repo.mkdir()

    # Init git repo
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(repo), capture_output=True)

    # Create initial commit on main
    (repo / "README.md").write_text("# Test\n")
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), capture_output=True)

    # Create a worker branch with changes
    subprocess.run(["git", "checkout", "-b", "worktree/worker-b"], cwd=str(repo), capture_output=True)
    (repo / "src").mkdir()
    (repo / "src" / "auth.ts").write_text("export function auth() { return true; }\n")
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "commit", "-m", "add auth"], cwd=str(repo), capture_output=True)
    subprocess.run(["git", "checkout", "main"], cwd=str(repo), capture_output=True)

    # Write a stub prompt
    prompts_dir = repo / "prompts"
    prompts_dir.mkdir()
    (prompts_dir / "sortie-code.md").write_text("Review branch {branch}:\n")
    (prompts_dir / "debrief.md").write_text("Synthesize {n} reviews:\n{sortie_outputs}\n")

    # Write echo-based config that returns stub output
    escaped_output = STUB_SORTIE_OUTPUT.replace("\n", "\\n")
    cfg = {
        "roster": [
            {
                "name": "stub-a",
                "invoke": "cli",
                "command": f'printf "{escaped_output}"',
                "prompt": "prompts/sortie-code.md",
                "timeout": 10,
            },
            {
                "name": "stub-b",
                "invoke": "cli",
                "command": f'printf "{escaped_output}"',
                "prompt": "prompts/sortie-code.md",
                "timeout": 10,
            },
        ],
        "debrief": {
            "model": "stub",
            "invoke": "cli",
            "command": f'printf "{escaped_output}"',
            "prompt": "prompts/debrief.md",
            "timeout": 10,
        },
        "triage": {
            "block_on": ["critical", "major"],
            "max_remediation_cycles": 2,
            "convergence_threshold": 2,
        },
        "modes": {
            "code": {
                "prompt": "prompts/sortie-code.md",
                "trigger": "merge",
                "roster": ["stub-a", "stub-b"],
                "triage": {"block_on": ["critical", "major"]},
            },
        },
        "ledger": {"path": str(repo / ".sortie" / "ledger.yaml")},
        "deposition": {
            "dir": str(repo / ".sortie") + "/{tree_sha}-{cycle}/",
            "keep_individual": True,
        },
    }
    cfg_path = repo / "sortie.yaml"
    with open(cfg_path, "w") as f:
        yaml.dump(cfg, f)

    return {"repo": str(repo), "cfg_path": str(cfg_path)}


class TestFullPipeline:
    def test_pipeline_produces_verdict_and_ledger(self, integration_env):
        result = subprocess.run(
            [
                "python3",
                os.path.join(SORTIE_DIR, "scripts", "sortie.py"),
                "pipeline",
                "worktree/worker-b",
                "--mode",
                "code",
                "--config",
                integration_env["cfg_path"],
            ],
            capture_output=True,
            text=True,
            cwd=integration_env["repo"],
        )

        # Pipeline should complete (exit code depends on triage)
        assert result.returncode in (0, 1, 2), f"Unexpected exit: {result.stderr}\n{result.stdout}"

        # Verdict should exist
        sortie_dir = os.path.join(integration_env["repo"], ".sortie")
        run_dirs = [
            d
            for d in os.listdir(sortie_dir)
            if os.path.isdir(os.path.join(sortie_dir, d))
        ]
        assert len(run_dirs) >= 1, f"No run directories found in {sortie_dir}"

        verdict_path = os.path.join(sortie_dir, run_dirs[0], "verdict.yaml")
        assert os.path.exists(verdict_path), f"verdict.yaml not found in {run_dirs[0]}"

        # Ledger should have an entry
        ledger_path = os.path.join(sortie_dir, "ledger.yaml")
        assert os.path.exists(ledger_path)
        with open(ledger_path) as f:
            ledger = yaml.safe_load(f)
        assert len(ledger["runs"]) >= 1

        # Individual sortie files should exist
        for model in ["stub-a", "stub-b"]:
            model_path = os.path.join(sortie_dir, run_dirs[0], f"sortie-{model}.yaml")
            assert os.path.exists(model_path), f"Missing {model_path}"
```

- [ ] **Step 2: Run integration test to verify it fails**

Run: `cd /Users/mrkai/code/sortie && python3 -m pytest tests/test_integration.py -v`
Expected: FAIL (scripts not yet wired together, or pass if all previous tasks are done)

- [ ] **Step 3: Fix any issues found by the integration test**

This step is conditional -- if the pipeline works end-to-end, skip. If there are wiring issues between modules, fix them here.

- [ ] **Step 4: Run full test suite**

Run: `cd /Users/mrkai/code/sortie && python3 -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/mrkai/code/sortie
git add tests/test_integration.py
git commit -m "test: integration smoke test -- full pipeline with echo stubs"
```

---

## Task Dependency Summary

```
Task 1 (ledger) ──────────────────────────────┐
Task 2 (config) ──────────────────────────────┤
Task 3 (identity) ────────────────────────────┤
Task 4 (attestation) ─────────────────────────┼──> Task 8 (CLI) ──> Task 12 (integration)
Task 5 (invoker) ─────────────────────────────┤
Task 6 (debrief) ─────────────────────────────┤
Task 7 (triage) ──────────────────────────────┘
Task 9 (hook) ── standalone
Task 10 (prompts) ── standalone
Task 11 (scaffolding) ── standalone, but commit last
```

Tasks 1-7 can be done in any order (they are independent modules). Task 8 depends on all of them. Tasks 9-11 are independent. Task 12 requires everything.
