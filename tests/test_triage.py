"""Tests for the Triage module."""

import pytest
from scripts.triage import TriageResult, triage_verdict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_finding(severity: str, convergent: bool) -> dict:
    return {"severity": severity, "convergent": convergent}


def make_verdict(findings: list[dict]) -> dict:
    return {"findings": findings}


BLOCK_ON_CRITICAL_MAJOR = ["critical", "major"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTriageVerdict:
    def test_pass_clean(self):
        """No findings -> merge, exit 0."""
        verdict = make_verdict([])
        result = triage_verdict(verdict, {"block_on": BLOCK_ON_CRITICAL_MAJOR})
        assert result.action == "merge"
        assert result.exit_code == 0
        assert result.blocking_findings == []
        assert result.advisory_findings == []

    def test_fail_on_convergent_major(self):
        """Convergent major with block_on=[critical, major] -> block, exit 1."""
        finding = make_finding("major", convergent=True)
        verdict = make_verdict([finding])
        result = triage_verdict(verdict, {"block_on": BLOCK_ON_CRITICAL_MAJOR})
        assert result.action == "block"
        assert result.exit_code == 1

    def test_pass_with_minor_only(self):
        """Convergent minor with block_on=[critical, major] -> merge_with_findings, exit 2."""
        finding = make_finding("minor", convergent=True)
        verdict = make_verdict([finding])
        result = triage_verdict(verdict, {"block_on": BLOCK_ON_CRITICAL_MAJOR})
        assert result.action == "merge_with_findings"
        assert result.exit_code == 2

    def test_divergent_never_blocks(self):
        """Even critical divergent finding should not block."""
        finding = make_finding("critical", convergent=False)
        verdict = make_verdict([finding])
        result = triage_verdict(verdict, {"block_on": BLOCK_ON_CRITICAL_MAJOR})
        assert result.action == "merge_with_findings"
        assert result.exit_code == 2

    def test_loosened_triage(self):
        """block_on=[critical] only -- major convergent should not block."""
        finding = make_finding("major", convergent=True)
        verdict = make_verdict([finding])
        result = triage_verdict(verdict, {"block_on": ["critical"]})
        assert result.action == "merge_with_findings"
        assert result.exit_code == 2

    def test_empty_block_on_never_blocks(self):
        """block_on=[] means no severity can block -- always advisory."""
        finding = make_finding("critical", convergent=True)
        verdict = make_verdict([finding])
        result = triage_verdict(verdict, {"block_on": []})
        assert result.action == "merge_with_findings"
        assert result.exit_code == 2

    def test_blocking_findings_listed(self):
        """blocking_findings should contain only the convergent blocking ones."""
        blocking = make_finding("critical", convergent=True)
        advisory_convergent = make_finding("minor", convergent=True)
        advisory_divergent = make_finding("critical", convergent=False)
        verdict = make_verdict([blocking, advisory_convergent, advisory_divergent])
        result = triage_verdict(verdict, {"block_on": BLOCK_ON_CRITICAL_MAJOR})
        assert result.action == "block"
        assert result.exit_code == 1
        assert blocking in result.blocking_findings
        assert advisory_convergent not in result.blocking_findings
        assert advisory_divergent not in result.blocking_findings
        # Both non-blocking findings end up as advisory
        assert advisory_convergent in result.advisory_findings
        assert advisory_divergent in result.advisory_findings
