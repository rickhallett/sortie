"""Tests for the attestation module."""

import pytest
import yaml
from scripts.attestation import write_attestation, read_attestation, verify_attestations


@pytest.fixture
def run_path(tmp_path):
    run_dir = tmp_path / "abc123ef-1"
    attestations_dir = run_dir / "attestations"
    attestations_dir.mkdir(parents=True)
    return str(run_dir)


class TestWriteAttestation:
    def test_writes_yaml_file_with_correct_fields(self, run_path):
        path = write_attestation(
            run_path=run_path,
            step="audit",
            tree_sha="abc123ef",
            cycle=1,
            verdict="pass",
            findings_count=0,
            tokens=1500,
            wall_time_ms=3200,
        )
        assert path.endswith("attestations/audit.yaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data["step"] == "audit"
        assert data["tree_sha"] == "abc123ef"
        assert data["cycle"] == 1
        assert data["verdict"] == "pass"
        assert data["findings_count"] == 0
        assert data["tokens"] == 1500
        assert data["wall_time_ms"] == 3200
        assert "timestamp" in data

    def test_writes_debrief_attestation(self, run_path):
        path = write_attestation(
            run_path=run_path,
            step="debrief",
            tree_sha="def456ab",
            cycle=2,
            verdict="fail",
            findings_count=3,
            tokens=800,
            wall_time_ms=1100,
        )
        with open(path) as f:
            data = yaml.safe_load(f)
        assert data["step"] == "debrief"
        assert data["verdict"] == "fail"
        assert data["findings_count"] == 3
        assert data["cycle"] == 2

    def test_creates_attestations_dir_if_missing(self, tmp_path):
        run_dir = tmp_path / "newrun-1"
        run_dir.mkdir()
        # attestations dir does NOT exist yet
        path = write_attestation(
            run_path=str(run_dir),
            step="audit",
            tree_sha="abc",
            cycle=1,
            verdict="pass",
            findings_count=0,
            tokens=100,
            wall_time_ms=500,
        )
        assert (run_dir / "attestations" / "audit.yaml").exists()

    def test_timestamp_is_utc_iso_format(self, run_path):
        path = write_attestation(
            run_path=run_path,
            step="audit",
            tree_sha="abc123ef",
            cycle=1,
            verdict="pass",
            findings_count=0,
            tokens=100,
            wall_time_ms=200,
        )
        with open(path) as f:
            data = yaml.safe_load(f)
        ts = data["timestamp"]
        # Should be a string ending with Z or +00:00
        assert isinstance(ts, str)
        assert "T" in ts


class TestReadAttestation:
    def test_reads_existing_attestation(self, run_path):
        write_attestation(
            run_path=run_path,
            step="audit",
            tree_sha="abc123ef",
            cycle=1,
            verdict="pass",
            findings_count=2,
            tokens=900,
            wall_time_ms=1500,
        )
        data = read_attestation(run_path, "audit")
        assert data is not None
        assert data["step"] == "audit"
        assert data["verdict"] == "pass"
        assert data["findings_count"] == 2

    def test_returns_none_for_missing_attestation(self, run_path):
        result = read_attestation(run_path, "nonexistent")
        assert result is None


class TestVerifyAttestations:
    def test_all_present_returns_empty_list(self, run_path):
        for step in ["audit", "debrief", "patch"]:
            write_attestation(
                run_path=run_path,
                step=step,
                tree_sha="abc",
                cycle=1,
                verdict="pass",
                findings_count=0,
                tokens=100,
                wall_time_ms=200,
            )
        missing = verify_attestations(run_path, ["audit", "debrief", "patch"])
        assert missing == []

    def test_missing_attestation_reported(self, run_path):
        write_attestation(
            run_path=run_path,
            step="audit",
            tree_sha="abc",
            cycle=1,
            verdict="pass",
            findings_count=0,
            tokens=100,
            wall_time_ms=200,
        )
        missing = verify_attestations(run_path, ["audit", "debrief"])
        assert missing == ["debrief"]

    def test_all_missing_reported(self, run_path):
        missing = verify_attestations(run_path, ["audit", "debrief", "patch"])
        assert set(missing) == {"audit", "debrief", "patch"}
