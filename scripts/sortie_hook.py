"""Pre-merge hook for Sortie.

Checks whether the current worktree has a passing sortie verdict before
allowing a merge. Intended to be wired up as a git pre-merge-commit hook
or called from CI.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional

import yaml


def _cycle_number(dirname: str) -> int:
    """Extract the numeric cycle suffix from a run directory name."""
    try:
        return int(dirname.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return 0


def check_pre_merge(sortie_dir: str, tree_sha: str) -> dict:
    """Check whether a passing verdict exists for the given tree SHA.

    Args:
        sortie_dir: Path to the ``.sortie`` directory.
        tree_sha:   Full (or at least 8-char) git tree SHA to look up.

    Returns:
        ``{"ok": True, "reason": "..."}``  if verdict is "pass" or
        "pass_with_findings".

        ``{"ok": False, "reason": "..."}`` for "fail", missing directory,
        no matching cycle dirs, or missing verdict.yaml.
    """
    tree_sha_short = tree_sha[:8]

    # ------------------------------------------------------------------
    # 1. Confirm sortie_dir exists
    # ------------------------------------------------------------------
    if not os.path.isdir(sortie_dir):
        return {
            "ok": False,
            "reason": f"No sortie directory found at {sortie_dir!r}.",
        }

    # ------------------------------------------------------------------
    # 2. Find all cycle directories matching {tree_sha_short}-*
    # ------------------------------------------------------------------
    try:
        entries = os.listdir(sortie_dir)
    except OSError as exc:
        return {"ok": False, "reason": f"Cannot read sortie dir: {exc}"}

    prefix = f"{tree_sha_short}-"
    matching = sorted(
        (entry for entry in entries
         if entry.startswith(prefix) and os.path.isdir(os.path.join(sortie_dir, entry))),
        key=_cycle_number,
    )

    if not matching:
        return {
            "ok": False,
            "reason": (
                f"No sortie cycle directories found for tree SHA {tree_sha_short!r}. "
                "Run sortie before merging."
            ),
        }

    # ------------------------------------------------------------------
    # 3. Use the latest cycle (last when sorted lexicographically)
    # ------------------------------------------------------------------
    latest_cycle_dir = os.path.join(sortie_dir, matching[-1])
    verdict_path = os.path.join(latest_cycle_dir, "verdict.yaml")

    # ------------------------------------------------------------------
    # 4. Read verdict.yaml
    # ------------------------------------------------------------------
    if not os.path.isfile(verdict_path):
        return {
            "ok": False,
            "reason": (
                f"No verdict.yaml in {latest_cycle_dir!r}. "
                "Sortie cycle may be incomplete."
            ),
        }

    try:
        with open(verdict_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"Failed to parse verdict.yaml: {exc}"}

    if not isinstance(data, dict):
        return {"ok": False, "reason": "verdict.yaml has unexpected format."}

    # ------------------------------------------------------------------
    # 5. Verify full tree SHA when present in verdict (trust boundary)
    # ------------------------------------------------------------------
    verdict_tree_sha = data.get("tree_sha")
    if verdict_tree_sha is not None and verdict_tree_sha != tree_sha:
        return {
            "ok": False,
            "reason": (
                f"Verdict tree SHA mismatch: verdict contains {verdict_tree_sha!r} "
                f"but current tree is {tree_sha!r}."
            ),
        }

    # ------------------------------------------------------------------
    # 6. Verify attestations directory exists and is non-empty
    # ------------------------------------------------------------------
    attestations_dir = os.path.join(latest_cycle_dir, "attestations")
    if not os.path.isdir(attestations_dir):
        return {
            "ok": False,
            "reason": (
                f"No attestations found in {latest_cycle_dir!r}. "
                "Sortie cycle may be incomplete or tampered with."
            ),
        }
    try:
        attestation_files = [
            f for f in os.listdir(attestations_dir)
            if os.path.isfile(os.path.join(attestations_dir, f))
        ]
    except OSError as exc:
        return {"ok": False, "reason": f"Cannot read attestations dir: {exc}"}
    if not attestation_files:
        return {
            "ok": False,
            "reason": (
                f"Attestations directory is empty in {latest_cycle_dir!r}. "
                "Sortie cycle may be incomplete or tampered with."
            ),
        }

    verdict = data.get("verdict", "")

    # ------------------------------------------------------------------
    # 7. Evaluate verdict
    # ------------------------------------------------------------------
    if verdict in ("pass", "pass_with_findings"):
        return {
            "ok": True,
            "reason": (
                f"Sortie verdict is {verdict!r} for tree {tree_sha_short} "
                f"(cycle dir: {matching[-1]})."
            ),
        }

    if verdict == "fail":
        findings: list = data.get("findings", []) or []
        capped = findings[:5]
        finding_lines = "\n".join(
            f"  - [{f.get('id', '?')}] {f.get('summary', '')}" for f in capped
        )
        extra = f" (+{len(findings) - 5} more)" if len(findings) > 5 else ""
        reason = (
            f"Sortie verdict is 'fail' for tree {tree_sha_short} "
            f"(cycle dir: {matching[-1]})."
        )
        if finding_lines:
            reason += f"\nFindings{extra}:\n{finding_lines}"
        return {"ok": False, "reason": reason}

    # Unknown / missing verdict value
    return {
        "ok": False,
        "reason": (
            f"Sortie verdict is {verdict!r} (unrecognised) for tree "
            f"{tree_sha_short}. Expected 'pass', 'pass_with_findings', or 'fail'."
        ),
    }


def main() -> None:
    """CLI entry point: resolve tree SHA, run check, exit appropriately."""
    try:
        tree_sha = subprocess.check_output(
            ["git", "write-tree"], text=True
        ).strip()
    except subprocess.CalledProcessError as exc:
        print(f"Failed to get tree SHA via git write-tree: {exc}", file=sys.stderr)
        sys.exit(2)

    sortie_dir = ".sortie"
    result = check_pre_merge(sortie_dir, tree_sha)
    print(result["reason"])
    sys.exit(0 if result["ok"] else 2)


if __name__ == "__main__":
    main()
