"""Tests for the Ledger module."""

import pytest
import yaml
from scripts.ledger import Ledger


class TestLedgerInit:
    def test_creates_file_if_missing(self, tmp_path):
        path = tmp_path / "ledger.yaml"
        assert not path.exists()
        ledger = Ledger(str(path))
        data = ledger.load()
        assert path.exists()
        assert data == {"runs": []}

    def test_loads_empty_ledger(self, tmp_path):
        path = tmp_path / "ledger.yaml"
        path.write_text(yaml.dump({"runs": []}))
        ledger = Ledger(str(path))
        data = ledger.load()
        assert data == {"runs": []}

    def test_loads_existing_ledger(self, tmp_path):
        path = tmp_path / "ledger.yaml"
        existing = {"runs": [{"tree_sha": "abc123", "cycle": 1}]}
        path.write_text(yaml.dump(existing))
        ledger = Ledger(str(path))
        data = ledger.load()
        assert data == existing


class TestLedgerAppend:
    def test_append_single_run(self, tmp_path):
        path = tmp_path / "ledger.yaml"
        ledger = Ledger(str(path))
        entry = {"tree_sha": "abc123", "cycle": 1, "worker_branch": "worker-a"}
        ledger.append(entry)
        data = ledger.load()
        assert len(data["runs"]) == 1
        assert data["runs"][0] == entry

    def test_append_preserves_existing(self, tmp_path):
        path = tmp_path / "ledger.yaml"
        ledger = Ledger(str(path))
        entry1 = {"tree_sha": "abc123", "cycle": 1, "worker_branch": "worker-a"}
        entry2 = {"tree_sha": "def456", "cycle": 1, "worker_branch": "worker-b"}
        ledger.append(entry1)
        ledger.append(entry2)
        data = ledger.load()
        assert len(data["runs"]) == 2
        assert data["runs"][0] == entry1
        assert data["runs"][1] == entry2

    def test_append_persists_to_disk(self, tmp_path):
        path = tmp_path / "ledger.yaml"
        ledger = Ledger(str(path))
        entry = {"tree_sha": "abc123", "cycle": 1}
        ledger.append(entry)
        # Re-instantiate to confirm it reads from disk
        ledger2 = Ledger(str(path))
        data = ledger2.load()
        assert len(data["runs"]) == 1
        assert data["runs"][0] == entry


class TestLedgerDisposition:
    def test_update_disposition(self, tmp_path):
        path = tmp_path / "ledger.yaml"
        ledger = Ledger(str(path))
        entry = {
            "tree_sha": "abc123",
            "cycle": 1,
            "findings": [{"id": "F-001", "disposition": "pending"}],
        }
        ledger.append(entry)
        ledger.update_disposition("abc123", 1, "F-001", "accepted")
        data = ledger.load()
        run = data["runs"][0]
        finding = next(f for f in run["findings"] if f["id"] == "F-001")
        assert finding["disposition"] == "accepted"

    def test_update_disposition_error_on_nonexistent_run(self, tmp_path):
        path = tmp_path / "ledger.yaml"
        ledger = Ledger(str(path))
        with pytest.raises(ValueError, match="Run not found"):
            ledger.update_disposition("nonexistent", 99, "F-001", "accepted")

    def test_update_disposition_persists(self, tmp_path):
        path = tmp_path / "ledger.yaml"
        ledger = Ledger(str(path))
        entry = {
            "tree_sha": "abc123",
            "cycle": 1,
            "findings": [{"id": "F-001", "disposition": "pending"}],
        }
        ledger.append(entry)
        ledger.update_disposition("abc123", 1, "F-001", "rejected")
        # Re-load from disk
        ledger2 = Ledger(str(path))
        data = ledger2.load()
        finding = next(f for f in data["runs"][0]["findings"] if f["id"] == "F-001")
        assert finding["disposition"] == "rejected"


class TestLedgerQuery:
    def test_find_run(self, tmp_path):
        path = tmp_path / "ledger.yaml"
        ledger = Ledger(str(path))
        entry = {"tree_sha": "abc123", "cycle": 1, "worker_branch": "worker-a"}
        ledger.append(entry)
        result = ledger.find_run("abc123", 1)
        assert result == entry

    def test_find_run_missing(self, tmp_path):
        path = tmp_path / "ledger.yaml"
        ledger = Ledger(str(path))
        result = ledger.find_run("nonexistent", 1)
        assert result is None

    def test_find_run_matches_correct_cycle(self, tmp_path):
        path = tmp_path / "ledger.yaml"
        ledger = Ledger(str(path))
        entry1 = {"tree_sha": "abc123", "cycle": 1}
        entry2 = {"tree_sha": "abc123", "cycle": 2}
        ledger.append(entry1)
        ledger.append(entry2)
        result = ledger.find_run("abc123", 2)
        assert result == entry2

    def test_runs_for_branch(self, tmp_path):
        path = tmp_path / "ledger.yaml"
        ledger = Ledger(str(path))
        entry1 = {"tree_sha": "abc123", "cycle": 1, "worker_branch": "worker-a"}
        entry2 = {"tree_sha": "def456", "cycle": 1, "worker_branch": "worker-b"}
        entry3 = {"tree_sha": "ghi789", "cycle": 1, "worker_branch": "worker-a"}
        ledger.append(entry1)
        ledger.append(entry2)
        ledger.append(entry3)
        results = ledger.runs_for_branch("worker-a")
        assert len(results) == 2
        assert entry1 in results
        assert entry3 in results

    def test_runs_for_branch_empty(self, tmp_path):
        path = tmp_path / "ledger.yaml"
        ledger = Ledger(str(path))
        results = ledger.runs_for_branch("worker-a")
        assert results == []


class TestLedgerBulkDispose:
    def test_bulk_dispose_marks_all_findings(self, tmp_path):
        path = tmp_path / "ledger.yaml"
        ledger = Ledger(str(path))
        entry = {
            "tree_sha": "abc123",
            "cycle": 1,
            "findings": [
                {"id": "F-001", "disposition": "open"},
                {"id": "F-002", "disposition": "open"},
                {"id": "F-003", "disposition": "open"},
            ],
        }
        ledger.append(entry)
        count = ledger.bulk_dispose("abc123", 1, "fixed")
        assert count == 3
        data = ledger.load()
        run = data["runs"][0]
        for finding in run["findings"]:
            assert finding["disposition"] == "fixed"

    def test_bulk_dispose_nonexistent_run(self, tmp_path):
        path = tmp_path / "ledger.yaml"
        ledger = Ledger(str(path))
        with pytest.raises(ValueError, match="Run not found"):
            ledger.bulk_dispose("nonexistent", 99, "fixed")

    def test_bulk_dispose_overwrites_existing(self, tmp_path):
        path = tmp_path / "ledger.yaml"
        ledger = Ledger(str(path))
        entry = {
            "tree_sha": "abc123",
            "cycle": 1,
            "findings": [
                {"id": "F-001", "disposition": "deferred"},
                {"id": "F-002", "disposition": "false-positive"},
            ],
        }
        ledger.append(entry)
        count = ledger.bulk_dispose("abc123", 1, "disagree")
        assert count == 2
        data = ledger.load()
        run = data["runs"][0]
        for finding in run["findings"]:
            assert finding["disposition"] == "disagree"
