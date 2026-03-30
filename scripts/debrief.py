"""Debrief module -- builds synthesis prompts and writes verdict output."""

from __future__ import annotations

import glob
import os

import yaml

from scripts.invoker import SortieResult


def build_debrief_prompt(
    prompt_path: str,
    sortie_results: dict[str, SortieResult],
    tree_sha: str,
    branch: str,
) -> str:
    """Build a debrief prompt by populating a template with sortie outputs.

    Reads the prompt template at *prompt_path* and substitutes:
    - ``{n}`` -- number of models
    - ``{sortie_outputs}`` -- labeled YAML blocks, one per model
    - ``{tree_sha}`` -- the git tree SHA
    - ``{branch}`` -- the worker branch name

    Each model's block is formatted as::

        ### <model_name>
        <yaml dump of SortieResult fields>

    Args:
        prompt_path: Path to the debrief prompt template file.
        sortie_results: Mapping of model name -> SortieResult.
        tree_sha: Git tree SHA for the reviewed commit.
        branch: Worker branch name.

    Returns:
        The populated prompt string.
    """
    with open(prompt_path) as f:
        template = f.read()

    blocks: list[str] = []
    for model_name, result in sortie_results.items():
        data = {
            "model": result.model,
            "verdict": result.verdict,
            "findings": result.findings,
            "tokens": result.tokens,
            "wall_time_ms": result.wall_time_ms,
            "raw_output": result.raw_output,
            "error": result.error,
        }
        block = f"### {model_name}\n{yaml.dump(data, default_flow_style=False).rstrip()}"
        blocks.append(block)

    sortie_outputs = "\n\n".join(blocks)

    return (
        template
        .replace("{n}", str(len(sortie_results)))
        .replace("{sortie_outputs}", sortie_outputs)
        .replace("{tree_sha}", tree_sha)
        .replace("{branch}", branch)
    )


def write_verdict(run_path: str, verdict_data: dict) -> str:
    """Write *verdict_data* as ``verdict.yaml`` inside *run_path*.

    Args:
        run_path: Directory where the verdict file will be written.
        verdict_data: Dict to serialise as YAML.

    Returns:
        Absolute path to the written ``verdict.yaml`` file.
    """
    out_path = os.path.join(run_path, "verdict.yaml")
    with open(out_path, "w") as f:
        yaml.dump(verdict_data, f, default_flow_style=False)
    return out_path


def load_sortie_outputs(run_path: str) -> dict[str, dict]:
    """Load all ``sortie-*.yaml`` files from *run_path*.

    Files that do not match the ``sortie-`` prefix (e.g. ``verdict.yaml``) are
    ignored.

    Args:
        run_path: Directory to scan for sortie output files.

    Returns:
        Mapping of model name (derived from filename) to parsed YAML dict.
        For example ``sortie-gpt-4o.yaml`` -> key ``"gpt-4o"``.
    """
    pattern = os.path.join(run_path, "sortie-*.yaml")
    results: dict[str, dict] = {}

    for file_path in glob.glob(pattern):
        filename = os.path.basename(file_path)
        # Strip "sortie-" prefix and ".yaml" suffix
        model_name = filename[len("sortie-"):-len(".yaml")]
        with open(file_path) as f:
            results[model_name] = yaml.safe_load(f)

    return results
