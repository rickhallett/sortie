"""Tests for sortie ledger analysis."""

import yaml
import pytest

from scripts.analyze import load_ledger, summary


@pytest.fixture
def sample_ledger(tmp_path):
    data = {
        "runs": [
            {
                "run_id": "abc-1",
                "tree_sha": "abc",
                "cycle": 1,
                "timestamp": "2026-03-30T10:00:00Z",
                "project": "eval-001",
                "branch": "worker-a",
                "mode": "code",
                "verdict": "fail",
                "model_status": {
                    "claude": {"verdict": "fail", "error": None, "findings_count": 3, "wall_time_ms": 5000, "tokens": {"total": 1000}},
                    "codex": {"verdict": "error", "error": "parse failed", "findings_count": 0, "wall_time_ms": 200, "tokens": {}},
                    "gemini": {"verdict": "pass_with_findings", "error": None, "findings_count": 2, "wall_time_ms": 8000, "tokens": {"total": 1500}},
                },
                "findings": [
                    {"id": "v-001", "severity": "critical", "category": "security", "convergence": "convergent", "disposition": "fixed"},
                    {"id": "v-002", "severity": "major", "category": "correctness", "convergence": "convergent", "disposition": "fixed"},
                    {"id": "v-003", "severity": "minor", "category": "correctness", "convergence": "divergent", "disposition": "false-positive"},
                ],
                "wall_time_ms": 15000,
                "tokens": {"total": 2500, "by_model": {"claude": 1000, "codex": 0, "gemini": 1500}},
            },
            {
                "run_id": "def-1",
                "tree_sha": "def",
                "cycle": 1,
                "timestamp": "2026-03-30T11:00:00Z",
                "project": "eval-001",
                "branch": "worker-b",
                "mode": "code",
                "verdict": "pass_with_findings",
                "model_status": {
                    "claude": {"verdict": "pass_with_findings", "error": None, "findings_count": 2, "wall_time_ms": 6000, "tokens": {"total": 900}},
                    "codex": {"verdict": "pass", "error": None, "findings_count": 0, "wall_time_ms": 3000, "tokens": {"total": 800}},
                },
                "findings": [
                    {"id": "v-004", "severity": "minor", "category": "interface", "convergence": "divergent", "disposition": None},
                ],
                "wall_time_ms": 10000,
                "tokens": {"total": 1700, "by_model": {"claude": 900, "codex": 800}},
            },
        ]
    }
    path = tmp_path / "ledger.yaml"
    with open(path, "w") as f:
        yaml.dump(data, f)
    return str(path)


class TestLoadLedger:
    def test_loads_runs(self, sample_ledger):
        runs = load_ledger(sample_ledger)
        assert len(runs) == 2

    def test_empty_file(self, tmp_path):
        path = tmp_path / "empty.yaml"
        path.write_text("")
        runs = load_ledger(str(path))
        assert runs == []


class TestSummary:
    def test_total_runs(self, sample_ledger):
        runs = load_ledger(sample_ledger)
        s = summary(runs)
        assert s["total_runs"] == 2

    def test_total_findings(self, sample_ledger):
        runs = load_ledger(sample_ledger)
        s = summary(runs)
        assert s["total_findings"] == 4

    def test_convergent_count(self, sample_ledger):
        runs = load_ledger(sample_ledger)
        s = summary(runs)
        assert s["convergent"] == 2
        assert s["divergent"] == 2

    def test_model_reliability(self, sample_ledger):
        runs = load_ledger(sample_ledger)
        s = summary(runs)
        # Claude: 2 runs, 2 successes
        assert s["model_reliability"]["claude"]["rate"] == "100%"
        # Codex: 2 runs, 1 success (first errored)
        assert s["model_reliability"]["codex"]["successes"] == 1
        # Gemini: 1 run, 1 success
        assert s["model_reliability"]["gemini"]["rate"] == "100%"

    def test_precision(self, sample_ledger):
        runs = load_ledger(sample_ledger)
        s = summary(runs)
        # 2 fixed, 1 false-positive -> 67% precision
        assert "67%" in s["precision"]

    def test_verdicts(self, sample_ledger):
        runs = load_ledger(sample_ledger)
        s = summary(runs)
        assert s["by_verdict"]["fail"] == 1
        assert s["by_verdict"]["pass_with_findings"] == 1

    def test_tokens(self, sample_ledger):
        runs = load_ledger(sample_ledger)
        s = summary(runs)
        assert s["total_tokens"] == 4200

    def test_multi_ledger_merge(self, tmp_path):
        """Two ledger files should merge runs."""
        for name, project in [("a.yaml", "eval-001"), ("b.yaml", "eval-002")]:
            data = {"runs": [{"project": project, "verdict": "pass", "findings": [], "model_status": {}}]}
            with open(tmp_path / name, "w") as f:
                yaml.dump(data, f)
        runs_a = load_ledger(str(tmp_path / "a.yaml"))
        runs_b = load_ledger(str(tmp_path / "b.yaml"))
        s = summary(runs_a + runs_b)
        assert s["total_runs"] == 2
        assert "eval-001" in s["projects"]
        assert "eval-002" in s["projects"]
