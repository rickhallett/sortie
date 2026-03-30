"""Attestation module — write, read, and verify step attestations."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import yaml


def write_attestation(
    run_path: str,
    step: str,
    tree_sha: str,
    cycle: int,
    verdict: str,
    findings_count: int,
    tokens: int,
    wall_time_ms: int,
) -> str:
    """Write a YAML attestation file to {run_path}/attestations/{step}.yaml.

    Creates the attestations directory if it does not exist. Returns the
    absolute path of the written file.
    """
    attestations_dir = Path(run_path) / "attestations"
    attestations_dir.mkdir(parents=True, exist_ok=True)

    file_path = attestations_dir / f"{step}.yaml"

    data = {
        "step": step,
        "tree_sha": tree_sha,
        "cycle": cycle,
        "verdict": verdict,
        "findings_count": findings_count,
        "tokens": tokens,
        "wall_time_ms": wall_time_ms,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    file_path.write_text(yaml.dump(data, default_flow_style=False))
    return str(file_path)


def read_attestation(run_path: str, step: str) -> dict | None:
    """Read an attestation from {run_path}/attestations/{step}.yaml.

    Returns None if the file does not exist.
    """
    file_path = Path(run_path) / "attestations" / f"{step}.yaml"
    if not file_path.exists():
        return None
    return yaml.safe_load(file_path.read_text())


def verify_attestations(run_path: str, required_steps: list[str]) -> list[str]:
    """Return a list of step names whose attestation files are missing.

    An empty list means all required steps are attested.
    """
    return [step for step in required_steps if read_attestation(run_path, step) is None]
