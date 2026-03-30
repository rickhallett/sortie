"""Severity-gated triage verdict evaluation for sortie."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TriageResult:
    """Outcome of evaluating a verdict against a triage configuration.

    Attributes:
        action: One of ``"merge"``, ``"merge_with_findings"``, or ``"block"``.
        exit_code: ``0`` = pass, ``1`` = fail (block), ``2`` = pass with findings.
        blocking_findings: Convergent findings whose severity is in ``block_on``.
        advisory_findings: All remaining findings (non-blocking).
    """

    action: str
    exit_code: int
    blocking_findings: list[dict] = field(default_factory=list)
    advisory_findings: list[dict] = field(default_factory=list)
    all_clear_warning: str | None = None


def triage_verdict(verdict: dict, triage_cfg: dict) -> TriageResult:
    """Apply severity-gated triage logic to *verdict*.

    Rules:
    - Only **convergent** findings can block.  Divergent findings are always
      advisory regardless of severity.
    - ``triage_cfg["block_on"]`` is the list of severities that trigger a block.
    - If any convergent finding's severity is in ``block_on``:
      ``action="block"``, ``exit_code=1``.
    - If findings exist but none block:
      ``action="merge_with_findings"``, ``exit_code=2``.
    - If no findings at all:
      ``action="merge"``, ``exit_code=0``.

    Args:
        verdict: A dict with a ``"findings"`` list.  Each finding must have at
            least ``"severity"`` (str) and ``"convergent"`` (bool) keys.
        triage_cfg: Configuration dict.  Must contain ``"block_on"`` (list of
            severity strings).

    Returns:
        A :class:`TriageResult` describing the triage outcome.
    """
    findings: list[dict] = verdict.get("findings", [])
    block_on: list[str] = triage_cfg.get("block_on", [])

    blocking: list[dict] = []
    advisory: list[dict] = []

    for finding in findings:
        if finding.get("convergent") and finding.get("severity") in block_on:
            blocking.append(finding)
        else:
            advisory.append(finding)

    if blocking:
        return TriageResult(
            action="block",
            exit_code=1,
            blocking_findings=blocking,
            advisory_findings=advisory,
        )

    if findings:
        return TriageResult(
            action="merge_with_findings",
            exit_code=2,
            blocking_findings=[],
            advisory_findings=advisory,
        )

    return TriageResult(
        action="merge",
        exit_code=0,
        all_clear_warning="All models returned zero findings. Consider manual review.",
    )
