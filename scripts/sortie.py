#!/usr/bin/env python3
"""Sortie CLI -- pipeline, status, and dispose subcommands."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

import yaml

# ---------------------------------------------------------------------------
# Ensure the project root is on the path so `scripts.*` imports work when
# the script is run directly (not via `python -m`).
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.config import load_config, resolve_mode  # noqa: E402
from scripts.identity import get_tree_sha, next_cycle, run_id, run_dir  # noqa: E402
from scripts.attestation import write_attestation  # noqa: E402
from scripts.invoker import invoke_all, invoke_cli, parse_sortie_output, sanitize_output, _invoke_single, SortieResult  # noqa: E402
from scripts.debrief import build_debrief_prompt, write_verdict  # noqa: E402
from scripts.triage import triage_verdict  # noqa: E402
from scripts.ledger import Ledger  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sortie_base_dir(cfg: dict, fallback: str) -> str:
    """Derive the base .sortie directory from deposition.dir config.

    The deposition.dir may contain template tokens like ``{tree_sha}-{cycle}``.
    We extract the literal prefix before the first ``{`` to get the base dir.
    If it's a relative path, it's resolved relative to the config file's
    directory (or ``fallback``).
    """
    raw: str = cfg.get("deposition", {}).get("dir", ".sortie/")
    # Strip template portion
    base = raw.split("{")[0].rstrip("/")
    if not base:
        base = ".sortie"
    if not os.path.isabs(base):
        base = os.path.join(fallback, base)
    return base


def _git_diff(branch: str, cwd: str) -> str:
    """Return git diff of branch against main (three-dot diff)."""
    try:
        result = subprocess.run(
            ["git", "diff", f"main...{branch}"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError as exc:
        # Fall back to empty diff on error (e.g. no git repo in tests)
        return ""


def _git_diff_stats(branch: str, cwd: str) -> str:
    """Return git diff --stat --numstat of branch against main."""
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", "--numstat", f"main...{branch}"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return ""


def _aggregate_fallback(
    sortie_results: dict[str, SortieResult],
) -> dict:
    """Build a fallback verdict by aggregating individual sortie findings."""
    all_findings: list[dict] = []
    for result in sortie_results.values():
        all_findings.extend(result.findings or [])

    return {
        "verdict": "fail" if all_findings else "pass",
        "convergence": "divergent",
        "findings": all_findings,
    }


# ---------------------------------------------------------------------------
# Subcommand: pipeline
# ---------------------------------------------------------------------------

def cmd_pipeline(args: argparse.Namespace, cfg: dict, config_dir: str) -> int:
    """Run the full sortie pipeline."""
    mode_cfg = resolve_mode(cfg, args.mode)
    branch = args.branch
    cwd = os.getcwd()

    # 1. Diff
    diff = _git_diff(branch, cwd)
    diff_stats = _git_diff_stats(branch, cwd)

    # 2. Identity
    try:
        tree_sha = get_tree_sha(cwd)
    except Exception as exc:
        print(f"Warning: could not get tree SHA: {exc}", file=sys.stderr)
        tree_sha = "0" * 40

    sortie_dir = _sortie_base_dir(cfg, config_dir)
    cycle = next_cycle(sortie_dir, tree_sha)
    rid = run_id(tree_sha, cycle)
    rdir = run_dir(sortie_dir, tree_sha, cycle)

    # 3. Create run and attestations directories
    os.makedirs(os.path.join(rdir, "attestations"), exist_ok=True)

    # 4. Build roster
    roster_names = mode_cfg.get("roster_names")
    full_roster: list[dict] = cfg.get("roster", [])
    if roster_names is not None:
        roster = [e for e in full_roster if e["name"] in roster_names]
    else:
        roster = full_roster

    prompt_path = mode_cfg["prompt"]
    if not os.path.isabs(prompt_path):
        prompt_path = os.path.join(config_dir, prompt_path)

    # 5. Invoke all roster models in parallel
    sortie_results = invoke_all(
        roster=roster,
        diff=diff,
        prompt_path=prompt_path,
        branch=branch,
        cwd=cwd,
    )

    # 6. Write individual sortie outputs and attestations
    for model_name, result in sortie_results.items():
        out_path = os.path.join(rdir, f"sortie-{model_name}.yaml")
        data = {
            "model": result.model,
            "verdict": result.verdict,
            "findings": result.findings,
            "tokens": result.tokens,
            "wall_time_ms": result.wall_time_ms,
            "error": result.error,
        }
        with open(out_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)

        write_attestation(
            run_path=rdir,
            step=f"sortie-{model_name}",
            tree_sha=tree_sha,
            cycle=cycle,
            verdict=result.verdict or "error",
            findings_count=len(result.findings or []),
            tokens=sum((result.tokens or {}).values()),
            wall_time_ms=result.wall_time_ms,
        )

    # 7. Debrief
    debrief_cfg = cfg.get("debrief", {})
    debrief_prompt_path = debrief_cfg.get("prompt", "")
    if debrief_prompt_path and not os.path.isabs(debrief_prompt_path):
        debrief_prompt_path = os.path.join(config_dir, debrief_prompt_path)

    debrief_verdict: dict | None = None
    debrief_result: SortieResult | None = None

    try:
        if debrief_prompt_path and os.path.exists(debrief_prompt_path):
            debrief_prompt = build_debrief_prompt(
                prompt_path=debrief_prompt_path,
                sortie_results=sortie_results,
                tree_sha=tree_sha,
                branch=branch,
            )
            debrief_entry = dict(debrief_cfg)
            debrief_entry.setdefault("name", debrief_entry.get("model", "debrief"))
            # Invoke debrief directly -- the prompt is already assembled
            if debrief_entry.get("invoke") == "cli":
                import time as _time
                _db_start = _time.monotonic()
                cli_result = invoke_cli(
                    command=debrief_entry.get("command", ""),
                    stdin_text=debrief_prompt,
                    timeout=debrief_entry.get("timeout", 120),
                    cwd=cwd,
                )
                _db_elapsed = int((_time.monotonic() - _db_start) * 1000)
                parsed = parse_sortie_output(sanitize_output(cli_result.stdout))
                debrief_result = SortieResult(
                    model=debrief_entry.get("name", "debrief"),
                    verdict=parsed.verdict,
                    findings=parsed.findings,
                    wall_time_ms=_db_elapsed,
                    raw_output=cli_result.stdout,
                    error=parsed.error,
                )
            else:
                # hook-agent or other -- will return error, fall through to fallback
                debrief_result = _invoke_single(
                    entry=debrief_entry,
                    diff=debrief_prompt,
                    prompt_path=None,
                    branch=branch,
                    cwd=cwd,
                )

            if debrief_result and debrief_result.error is None:
                debrief_verdict = {
                    "verdict": debrief_result.verdict,
                    "convergence": "convergent",
                    "findings": debrief_result.findings or [],
                }
    except Exception as exc:
        print(f"Warning: debrief invocation failed: {exc}", file=sys.stderr)

    if debrief_verdict is None:
        debrief_verdict = _aggregate_fallback(sortie_results)

    # 8. Write verdict.yaml
    verdict_data = {
        **debrief_verdict,
        "tree_sha": tree_sha,
        "cycle": cycle,
        "run_id": rid,
        "branch": branch,
        "mode": args.mode,
        "diff_stats": diff_stats,
    }
    write_verdict(rdir, verdict_data)

    # 9. Write debrief attestation
    debrief_tokens = 0
    debrief_wall_ms = 0
    if debrief_result:
        debrief_tokens = sum((debrief_result.tokens or {}).values())
        debrief_wall_ms = debrief_result.wall_time_ms

    write_attestation(
        run_path=rdir,
        step="debrief",
        tree_sha=tree_sha,
        cycle=cycle,
        verdict=verdict_data.get("verdict", "error"),
        findings_count=len(verdict_data.get("findings", [])),
        tokens=debrief_tokens,
        wall_time_ms=debrief_wall_ms,
    )

    # 10. Triage
    triage_cfg = mode_cfg.get("triage", cfg.get("triage", {}))
    triage_result = triage_verdict(verdict_data, triage_cfg)

    # 11. Append to ledger
    ledger_path = cfg.get("ledger", {}).get("path", ".sortie/ledger.yaml")
    if not os.path.isabs(ledger_path):
        ledger_path = os.path.join(config_dir, ledger_path)
    ledger = Ledger(ledger_path)
    ledger.append({
        "run_id": rid,
        "tree_sha": tree_sha,
        "cycle": cycle,
        "branch": branch,
        "mode": args.mode,
        "verdict": verdict_data.get("verdict", ""),
        "convergence": verdict_data.get("convergence", ""),
        "findings": verdict_data.get("findings", []),
        "worker_branch": branch,
        "diff_stats": diff_stats,
    })

    # 12. Print summary
    findings = verdict_data.get("findings", [])
    print(f"Run ID:   {rid}")
    print(f"Branch:   {branch}")
    print(f"Mode:     {args.mode}")
    print(f"Verdict:  {verdict_data.get('verdict', 'unknown')}")
    print(f"Findings: {len(findings)}")
    print(f"Action:   {triage_result.action}")
    if triage_result.blocking_findings:
        print(f"Blocking: {len(triage_result.blocking_findings)} finding(s)")

    if triage_result.all_clear_warning:
        print(f"Warning: {triage_result.all_clear_warning}")

    return triage_result.exit_code


# ---------------------------------------------------------------------------
# Subcommand: status
# ---------------------------------------------------------------------------

def cmd_status(args: argparse.Namespace, cfg: dict, config_dir: str) -> int:
    """Show recent runs from the ledger."""
    ledger_path = cfg.get("ledger", {}).get("path", ".sortie/ledger.yaml")
    if not os.path.isabs(ledger_path):
        ledger_path = os.path.join(config_dir, ledger_path)

    ledger = Ledger(ledger_path)
    data = ledger.load()
    runs = data.get("runs", [])

    if not runs:
        print("No runs found.")
        return 0

    recent = runs[-10:]
    print(f"Recent runs ({len(recent)} of {len(runs)} total):")
    print()
    header = f"{'RUN ID':<45} {'MODE':<10} {'VERDICT':<20} {'BRANCH':<30} {'FINDINGS'}"
    print(header)
    print("-" * len(header))
    for run in recent:
        rid = run.get("run_id") or f"{run.get('tree_sha', '?')}-{run.get('cycle', '?')}"
        mode = run.get("mode", "?")
        verdict = run.get("verdict", "?")
        branch = run.get("worker_branch") or run.get("branch", "?")
        findings_count = len(run.get("findings", []))
        print(f"{rid:<45} {mode:<10} {verdict:<20} {branch:<30} {findings_count}")

    return 0


# ---------------------------------------------------------------------------
# Subcommand: dispose
# ---------------------------------------------------------------------------

VALID_DISPOSITIONS = {"fixed", "false-positive", "deferred", "disagree"}


def cmd_dispose(args: argparse.Namespace, cfg: dict, config_dir: str) -> int:
    """Update the disposition of a finding."""
    disposition = args.disposition
    if disposition not in VALID_DISPOSITIONS:
        print(
            f"Error: invalid disposition {disposition!r}. "
            f"Must be one of: {', '.join(sorted(VALID_DISPOSITIONS))}",
            file=sys.stderr,
        )
        return 1

    run_id_str: str = args.run_id
    finding_id: str = args.finding_id

    # Parse run_id into tree_sha and cycle: split on last "-"
    try:
        last_dash = run_id_str.rfind("-")
        if last_dash == -1:
            raise ValueError("no '-' found")
        tree_sha = run_id_str[:last_dash]
        cycle = int(run_id_str[last_dash + 1:])
    except (ValueError, IndexError) as exc:
        print(f"Error: cannot parse run_id {run_id_str!r}: {exc}", file=sys.stderr)
        return 1

    # Locate run directory to update verdict.yaml
    sortie_dir = _sortie_base_dir(cfg, config_dir)
    rdir = run_dir(sortie_dir, tree_sha, cycle)
    verdict_path = os.path.join(rdir, "verdict.yaml")

    if not os.path.isfile(verdict_path):
        print(f"Error: verdict.yaml not found at {verdict_path}", file=sys.stderr)
        return 1

    # Update verdict.yaml
    with open(verdict_path, "r") as f:
        verdict_data = yaml.safe_load(f)

    updated = False
    for finding in verdict_data.get("findings", []):
        if finding.get("id") == finding_id:
            finding["disposition"] = disposition
            updated = True

    if not updated:
        print(
            f"Warning: finding {finding_id!r} not found in verdict.yaml",
            file=sys.stderr,
        )

    with open(verdict_path, "w") as f:
        yaml.dump(verdict_data, f, default_flow_style=False)

    # Update ledger
    ledger_path = cfg.get("ledger", {}).get("path", ".sortie/ledger.yaml")
    if not os.path.isabs(ledger_path):
        ledger_path = os.path.join(config_dir, ledger_path)

    ledger = Ledger(ledger_path)
    try:
        ledger.update_disposition(tree_sha, cycle, finding_id, disposition)
    except ValueError as exc:
        print(f"Warning: ledger update failed: {exc}", file=sys.stderr)

    print(f"Disposed finding {finding_id!r} as {disposition!r} in run {run_id_str}")
    return 0


# ---------------------------------------------------------------------------
# Subcommand: dispose-bulk
# ---------------------------------------------------------------------------

def cmd_dispose_bulk(args: argparse.Namespace, cfg: dict, config_dir: str) -> int:
    """Update the disposition of all findings in a run."""
    disposition = args.disposition
    if disposition not in VALID_DISPOSITIONS:
        print(
            f"Error: invalid disposition {disposition!r}. "
            f"Must be one of: {', '.join(sorted(VALID_DISPOSITIONS))}",
            file=sys.stderr,
        )
        return 1

    run_id_str: str = args.run_id

    # Parse run_id into tree_sha and cycle: split on last "-"
    try:
        last_dash = run_id_str.rfind("-")
        if last_dash == -1:
            raise ValueError("no '-' found")
        tree_sha = run_id_str[:last_dash]
        cycle = int(run_id_str[last_dash + 1:])
    except (ValueError, IndexError) as exc:
        print(f"Error: cannot parse run_id {run_id_str!r}: {exc}", file=sys.stderr)
        return 1

    # Locate run directory to update verdict.yaml
    sortie_dir = _sortie_base_dir(cfg, config_dir)
    rdir = run_dir(sortie_dir, tree_sha, cycle)
    verdict_path = os.path.join(rdir, "verdict.yaml")

    if not os.path.isfile(verdict_path):
        print(f"Error: verdict.yaml not found at {verdict_path}", file=sys.stderr)
        return 1

    # Update verdict.yaml -- all findings
    with open(verdict_path, "r") as f:
        verdict_data = yaml.safe_load(f)

    count = 0
    for finding in verdict_data.get("findings", []):
        finding["disposition"] = disposition
        count += 1

    with open(verdict_path, "w") as f:
        yaml.dump(verdict_data, f, default_flow_style=False)

    # Update ledger
    ledger_path = cfg.get("ledger", {}).get("path", ".sortie/ledger.yaml")
    if not os.path.isabs(ledger_path):
        ledger_path = os.path.join(config_dir, ledger_path)

    ledger = Ledger(ledger_path)
    try:
        ledger.bulk_dispose(tree_sha, cycle, disposition)
    except ValueError as exc:
        print(f"Warning: ledger update failed: {exc}", file=sys.stderr)

    print(f"Disposed {count} finding(s) as {disposition!r} in run {run_id_str}")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sortie",
        description="Sortie -- multi-model code review orchestrator",
    )
    parser.add_argument(
        "--config",
        default="sortie.yaml",
        help="Path to sortie config file (default: sortie.yaml)",
    )

    sub = parser.add_subparsers(dest="subcommand", metavar="subcommand")
    sub.required = True

    # pipeline
    p_pipeline = sub.add_parser("pipeline", help="Run the full sortie pipeline")
    p_pipeline.add_argument("branch", help="Worker branch to review")
    p_pipeline.add_argument(
        "--mode",
        default="code",
        help="Sortie mode (default: code)",
    )

    # status
    sub.add_parser("status", help="Show recent sortie runs")

    # dispose
    p_dispose = sub.add_parser("dispose", help="Update a finding disposition")
    p_dispose.add_argument("run_id", help="Run identifier (tree_sha-cycle)")
    p_dispose.add_argument("finding_id", help="Finding ID (e.g. F001)")
    p_dispose.add_argument(
        "disposition",
        help="One of: fixed, false-positive, deferred, disagree",
    )

    # dispose-bulk
    p_dispose_bulk = sub.add_parser("dispose-bulk", help="Mark all findings in a run with same disposition")
    p_dispose_bulk.add_argument("run_id", help="Run identifier (tree_sha-cycle)")
    p_dispose_bulk.add_argument("disposition", help="One of: fixed, false-positive, deferred, disagree")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    config_path = args.config
    if not os.path.isabs(config_path):
        config_path = os.path.join(os.getcwd(), config_path)

    config_dir = os.path.dirname(config_path)

    try:
        cfg = load_config(config_path)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 1

    dispatch = {
        "pipeline": cmd_pipeline,
        "status": cmd_status,
        "dispose": cmd_dispose,
        "dispose-bulk": cmd_dispose_bulk,
    }

    handler = dispatch.get(args.subcommand)
    if handler is None:
        print(f"Unknown subcommand: {args.subcommand}", file=sys.stderr)
        return 1

    return handler(args, cfg, config_dir)


if __name__ == "__main__":
    sys.exit(main())
