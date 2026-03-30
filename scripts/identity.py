"""Identity module: tree SHA, run ID, and cycle counting for sortie runs."""

import os
import re
import subprocess


def get_tree_sha(repo_path: str) -> str:
    """Run `git write-tree` in repo_path and return the 40-char hex SHA."""
    result = subprocess.run(
        ["git", "write-tree"],
        cwd=repo_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def next_cycle(sortie_dir: str, tree_sha: str) -> int:
    """Count existing {tree_sha}-N directories in sortie_dir, return N+1.

    Returns 1 if none exist.
    """
    pattern = re.compile(r"^" + re.escape(tree_sha) + r"-(\d+)$")
    max_cycle = 0
    try:
        entries = os.listdir(sortie_dir)
    except FileNotFoundError:
        return 1
    for entry in entries:
        match = pattern.match(entry)
        if match:
            n = int(match.group(1))
            if n > max_cycle:
                max_cycle = n
    return max_cycle + 1


def run_id(tree_sha: str, cycle: int) -> str:
    """Return the run identifier string: '{tree_sha}-{cycle}'."""
    return f"{tree_sha}-{cycle}"


def run_dir(sortie_dir: str, tree_sha: str, cycle: int) -> str:
    """Return the full path for a run directory."""
    return os.path.join(sortie_dir, run_id(tree_sha, cycle))
