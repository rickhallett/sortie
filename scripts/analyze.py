"""Sortie ledger analysis -- extract eval metrics from run data."""

from __future__ import annotations

import os
import sys
from collections import Counter

import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def load_ledger(path: str) -> list[dict]:
    """Load runs from a ledger file."""
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return (data or {}).get("runs", [])


def summary(runs: list[dict]) -> dict:
    """Compute aggregate metrics across all runs."""
    total_findings = 0
    convergent = 0
    divergent = 0
    by_severity = Counter()
    by_category = Counter()
    by_verdict = Counter()
    by_model_success = Counter()
    by_model_total = Counter()
    by_model_findings = Counter()
    dispositions = Counter()
    total_wall_ms = 0
    total_tokens = 0
    projects = set()

    for run in runs:
        by_verdict[run.get("verdict", "unknown")] += 1
        total_wall_ms += run.get("wall_time_ms", 0)
        total_tokens += run.get("tokens", {}).get("total", 0)
        projects.add(run.get("project", "unknown"))

        findings = run.get("findings", [])
        total_findings += len(findings)

        for f in findings:
            sev = f.get("severity", "unknown")
            by_severity[sev] += 1
            cat = f.get("category", "unknown")
            by_category[cat] += 1
            conv = f.get("convergence", "unknown")
            if conv == "convergent":
                convergent += 1
            elif conv == "divergent":
                divergent += 1
            disp = f.get("disposition")
            if disp:
                dispositions[disp] += 1

        # Model status
        model_status = run.get("model_status", {})
        for model, status in model_status.items():
            by_model_total[model] += 1
            if status.get("error") is None and status.get("verdict") != "error":
                by_model_success[model] += 1
            by_model_findings[model] += status.get("findings_count", 0)

    return {
        "total_runs": len(runs),
        "projects": sorted(projects),
        "total_findings": total_findings,
        "convergent": convergent,
        "divergent": divergent,
        "convergent_rate": f"{100 * convergent / total_findings:.0f}%" if total_findings else "n/a",
        "by_severity": dict(by_severity.most_common()),
        "by_category": dict(by_category.most_common()),
        "by_verdict": dict(by_verdict.most_common()),
        "dispositions": dict(dispositions.most_common()) if dispositions else "none captured",
        "precision": _precision(dispositions) if dispositions else "n/a (no dispositions)",
        "model_reliability": {
            model: {
                "runs": by_model_total[model],
                "successes": by_model_success[model],
                "rate": f"{100 * by_model_success[model] / by_model_total[model]:.0f}%",
                "findings_produced": by_model_findings[model],
            }
            for model in sorted(by_model_total)
        },
        "total_wall_time_s": round(total_wall_ms / 1000, 1),
        "total_tokens": total_tokens,
        "cost_per_finding": round(total_tokens / total_findings) if total_findings else "n/a",
    }


def _precision(dispositions: Counter) -> str:
    """Calculate precision: findings fixed / (fixed + false-positive)."""
    fixed = dispositions.get("fixed", 0)
    false_pos = dispositions.get("false-positive", 0)
    total = fixed + false_pos
    if total == 0:
        return "n/a (no fixed or false-positive dispositions)"
    return f"{100 * fixed / total:.0f}% ({fixed}/{total})"


def print_summary(metrics: dict) -> None:
    """Print a human-readable summary to stdout."""
    print("SORTIE ANALYSIS")
    print("=" * 60)
    print(f"Runs:            {metrics['total_runs']}")
    print(f"Projects:        {', '.join(metrics['projects'])}")
    print(f"Total findings:  {metrics['total_findings']}")
    print(f"Convergent:      {metrics['convergent']} ({metrics['convergent_rate']})")
    print(f"Divergent:       {metrics['divergent']}")
    print(f"Precision:       {metrics['precision']}")
    print(f"Wall time:       {metrics['total_wall_time_s']}s")
    print(f"Total tokens:    {metrics['total_tokens']}")
    print(f"Tokens/finding:  {metrics['cost_per_finding']}")
    print()

    print("VERDICTS")
    for v, c in metrics["by_verdict"].items():
        print(f"  {v:25s}: {c}")
    print()

    print("SEVERITY")
    for s, c in metrics["by_severity"].items():
        print(f"  {s:25s}: {c}")
    print()

    print("CATEGORIES")
    for cat, c in metrics["by_category"].items():
        print(f"  {cat:25s}: {c}")
    print()

    if metrics["dispositions"] != "none captured":
        print("DISPOSITIONS")
        for d, c in metrics["dispositions"].items():
            print(f"  {d:25s}: {c}")
        print()

    print("MODEL RELIABILITY")
    for model, stats in metrics["model_reliability"].items():
        print(f"  {model:15s}: {stats['rate']} success ({stats['successes']}/{stats['runs']}), {stats['findings_produced']} findings")
    print()


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="sortie-analyze",
        description="Analyze sortie ledger data",
    )
    parser.add_argument(
        "ledger",
        nargs="+",
        help="Path(s) to ledger.yaml file(s). Multiple files are merged for cross-eval analysis.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as YAML (machine-readable)",
    )

    args = parser.parse_args()

    all_runs = []
    for path in args.ledger:
        if not os.path.exists(path):
            print(f"Warning: {path} not found, skipping", file=sys.stderr)
            continue
        all_runs.extend(load_ledger(path))

    if not all_runs:
        print("No runs found in any ledger file.", file=sys.stderr)
        return 1

    metrics = summary(all_runs)

    if args.json:
        yaml.dump(metrics, sys.stdout, default_flow_style=False, sort_keys=False)
    else:
        print_summary(metrics)

    return 0


if __name__ == "__main__":
    sys.exit(main())
