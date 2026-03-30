"""Append-only YAML ledger for sortie run data."""

from __future__ import annotations

import os
from typing import Optional

import yaml


class Ledger:
    """Append-only YAML data store for sortie run data.

    The on-disk format is a single YAML file with a top-level ``runs`` list.
    Every mutating operation (append, update_disposition) immediately writes
    the full file back to disk so the ledger is always durable.
    """

    def __init__(self, path: str) -> None:
        self._path = path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self) -> dict:
        """Load ledger from disk.

        Creates an empty ``{"runs": []}`` structure if the file does not exist.
        """
        if not os.path.exists(self._path):
            empty: dict = {"runs": []}
            self._write(empty)
            return empty

        with open(self._path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        # Guard against an empty/null file
        if data is None:
            data = {"runs": []}
        if "runs" not in data:
            data["runs"] = []
        return data

    def append(self, entry: dict) -> None:
        """Append a run entry to the ledger."""
        data = self.load()
        data["runs"].append(entry)
        self._write(data)

    def find_run(self, tree_sha: str, cycle: int) -> Optional[dict]:
        """Return the run matching *tree_sha* and *cycle*, or ``None``."""
        data = self.load()
        for run in data["runs"]:
            if run.get("tree_sha") == tree_sha and run.get("cycle") == cycle:
                return run
        return None

    def runs_for_branch(self, worker_branch: str) -> list[dict]:
        """Return all runs whose ``worker_branch`` matches *worker_branch*."""
        data = self.load()
        return [r for r in data["runs"] if r.get("worker_branch") == worker_branch]

    def update_disposition(
        self, tree_sha: str, cycle: int, finding_id: str, disposition: str
    ) -> None:
        """Update the disposition of a finding in a specific run.

        Raises:
            ValueError: if the run identified by *tree_sha* + *cycle* is not found.
        """
        data = self.load()

        # Locate the run (we need to mutate in-place so work on the list directly)
        target_run: Optional[dict] = None
        for run in data["runs"]:
            if run.get("tree_sha") == tree_sha and run.get("cycle") == cycle:
                target_run = run
                break

        if target_run is None:
            raise ValueError(
                f"Run not found: tree_sha={tree_sha!r} cycle={cycle}"
            )

        findings = target_run.get("findings", [])
        for finding in findings:
            if finding.get("id") == finding_id:
                finding["disposition"] = disposition

        self._write(data)

    def bulk_dispose(self, tree_sha: str, cycle: int, disposition: str) -> int:
        """Mark all findings in a run with the same disposition.
        Returns the number of findings updated.
        Raises ValueError if run not found.
        """
        data = self.load()
        target_run = None
        for run in data["runs"]:
            if run.get("tree_sha") == tree_sha and run.get("cycle") == cycle:
                target_run = run
                break
        if target_run is None:
            raise ValueError(f"Run not found: tree_sha={tree_sha!r} cycle={cycle}")
        count = 0
        for finding in target_run.get("findings", []):
            finding["disposition"] = disposition
            count += 1
        self._write(data)
        return count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _write(self, data: dict) -> None:
        """Atomically write *data* to the ledger file."""
        tmp_path = self._path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            yaml.dump(data, fh, default_flow_style=False, allow_unicode=True)
        os.replace(tmp_path, self._path)
