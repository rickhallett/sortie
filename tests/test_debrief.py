"""Tests for the Debrief module."""

from __future__ import annotations

import os
import yaml
import pytest

from scripts.invoker import SortieResult
from scripts.debrief import build_debrief_prompt, write_verdict, load_sortie_outputs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_result(model: str, verdict: str = "pass", findings: list[dict] | None = None) -> SortieResult:
    return SortieResult(
        model=model,
        verdict=verdict,
        findings=findings or [],
        tokens={"input": 100, "output": 50},
        wall_time_ms=1234,
        raw_output="some output",
        error=None,
    )


# ---------------------------------------------------------------------------
# TestBuildDebriefPrompt
# ---------------------------------------------------------------------------

class TestBuildDebriefPrompt:
    def test_includes_all_sortie_outputs(self, tmp_path):
        """All model names appear as labeled blocks in the prompt."""
        prompt_file = tmp_path / "debrief.md"
        prompt_file.write_text(
            "n={n}\n{sortie_outputs}\ntree={tree_sha}\nbranch={branch}"
        )

        results = {
            "gpt-4o": make_result("gpt-4o", verdict="pass"),
            "claude-3-5-sonnet": make_result("claude-3-5-sonnet", verdict="fail", findings=[
                {"id": "f-001", "severity": "critical", "summary": "Bad thing"}
            ]),
        }

        prompt = build_debrief_prompt(
            str(prompt_file), results, tree_sha="abc123", branch="feature/x"
        )

        assert "### gpt-4o" in prompt
        assert "### claude-3-5-sonnet" in prompt
        # Both model outputs should be YAML-dumped inline
        assert "verdict: pass" in prompt
        assert "verdict: fail" in prompt

    def test_substitutes_n(self, tmp_path):
        """{n} is replaced with the number of models."""
        prompt_file = tmp_path / "debrief.md"
        prompt_file.write_text("models: {n}")

        results = {
            "model-a": make_result("model-a"),
            "model-b": make_result("model-b"),
            "model-c": make_result("model-c"),
        }

        prompt = build_debrief_prompt(
            str(prompt_file), results, tree_sha="sha1", branch="main"
        )

        assert "models: 3" in prompt

    def test_substitutes_tree_sha_and_branch(self, tmp_path):
        """{tree_sha} and {branch} are substituted."""
        prompt_file = tmp_path / "debrief.md"
        prompt_file.write_text("sha={tree_sha} br={branch} {sortie_outputs} {n}")

        results = {"m": make_result("m")}

        prompt = build_debrief_prompt(
            str(prompt_file), results, tree_sha="deadbeef", branch="my-branch"
        )

        assert "sha=deadbeef" in prompt
        assert "br=my-branch" in prompt

    def test_sortie_outputs_are_valid_yaml_blocks(self, tmp_path):
        """Each model block must be parseable as YAML."""
        prompt_file = tmp_path / "debrief.md"
        prompt_file.write_text("{sortie_outputs}")

        findings = [{"id": "f-001", "severity": "major", "summary": "oops"}]
        results = {
            "model-x": make_result("model-x", verdict="pass_with_findings", findings=findings),
        }

        prompt = build_debrief_prompt(
            str(prompt_file), results, tree_sha="s", branch="b"
        )

        # Strip the header line and parse the remaining block
        lines = prompt.strip().splitlines()
        assert lines[0] == "### model-x"
        yaml_text = "\n".join(lines[1:])
        parsed = yaml.safe_load(yaml_text)
        assert parsed["verdict"] == "pass_with_findings"
        assert parsed["findings"][0]["severity"] == "major"

    def test_single_model(self, tmp_path):
        """Works correctly with a single model."""
        prompt_file = tmp_path / "debrief.md"
        prompt_file.write_text("{n} {sortie_outputs}")

        results = {"only-model": make_result("only-model")}
        prompt = build_debrief_prompt(
            str(prompt_file), results, tree_sha="x", branch="y"
        )

        assert "1" in prompt
        assert "### only-model" in prompt


# ---------------------------------------------------------------------------
# TestWriteVerdict
# ---------------------------------------------------------------------------

class TestWriteVerdict:
    def test_writes_verdict_yaml(self, tmp_path):
        """verdict.yaml is created with the correct content."""
        verdict_data = {
            "tree_sha": "abc123",
            "worker_branch": "feature/foo",
            "verdict": "pass",
            "findings": [],
        }

        returned_path = write_verdict(str(tmp_path), verdict_data)

        expected_path = str(tmp_path / "verdict.yaml")
        assert returned_path == expected_path
        assert os.path.exists(expected_path)

        with open(expected_path) as f:
            loaded = yaml.safe_load(f)

        assert loaded["verdict"] == "pass"
        assert loaded["tree_sha"] == "abc123"
        assert loaded["worker_branch"] == "feature/foo"

    def test_returns_correct_path(self, tmp_path):
        """Return value is the full path to verdict.yaml."""
        path = write_verdict(str(tmp_path), {"verdict": "fail"})
        assert path.endswith("verdict.yaml")
        assert os.path.isabs(path)

    def test_overwrites_existing_verdict(self, tmp_path):
        """Calling write_verdict twice overwrites the first verdict."""
        write_verdict(str(tmp_path), {"verdict": "pass"})
        write_verdict(str(tmp_path), {"verdict": "fail"})

        with open(tmp_path / "verdict.yaml") as f:
            loaded = yaml.safe_load(f)

        assert loaded["verdict"] == "fail"

    def test_verdict_with_findings(self, tmp_path):
        """Findings list is preserved correctly in the YAML file."""
        verdict_data = {
            "verdict": "fail",
            "findings": [
                {"id": "f-001", "severity": "critical", "summary": "Uh oh"},
            ],
        }

        write_verdict(str(tmp_path), verdict_data)

        with open(tmp_path / "verdict.yaml") as f:
            loaded = yaml.safe_load(f)

        assert len(loaded["findings"]) == 1
        assert loaded["findings"][0]["id"] == "f-001"


# ---------------------------------------------------------------------------
# TestLoadSortieOutputs
# ---------------------------------------------------------------------------

class TestLoadSortieOutputs:
    def _write_yaml(self, path, data):
        with open(path, "w") as f:
            yaml.dump(data, f)

    def test_loads_sortie_files(self, tmp_path):
        """Loads all sortie-*.yaml files and returns them keyed by model name."""
        self._write_yaml(
            tmp_path / "sortie-gpt-4o.yaml",
            {"model": "gpt-4o", "verdict": "pass", "findings": []},
        )
        self._write_yaml(
            tmp_path / "sortie-claude-3-5-sonnet.yaml",
            {"model": "claude-3-5-sonnet", "verdict": "fail", "findings": []},
        )

        result = load_sortie_outputs(str(tmp_path))

        assert "gpt-4o" in result
        assert "claude-3-5-sonnet" in result
        assert result["gpt-4o"]["verdict"] == "pass"
        assert result["claude-3-5-sonnet"]["verdict"] == "fail"

    def test_ignores_non_sortie_files(self, tmp_path):
        """verdict.yaml and other files are not returned."""
        self._write_yaml(
            tmp_path / "sortie-model-a.yaml",
            {"model": "model-a", "verdict": "pass"},
        )
        self._write_yaml(
            tmp_path / "verdict.yaml",
            {"verdict": "pass", "findings": []},
        )
        (tmp_path / "notes.txt").write_text("some notes")

        result = load_sortie_outputs(str(tmp_path))

        assert "model-a" in result
        assert len(result) == 1

    def test_empty_directory(self, tmp_path):
        """Returns empty dict when no sortie files exist."""
        result = load_sortie_outputs(str(tmp_path))
        assert result == {}

    def test_single_sortie_file(self, tmp_path):
        """Works correctly with a single sortie file."""
        self._write_yaml(
            tmp_path / "sortie-only.yaml",
            {"model": "only", "verdict": "pass_with_findings"},
        )

        result = load_sortie_outputs(str(tmp_path))

        assert "only" in result
        assert result["only"]["verdict"] == "pass_with_findings"

    def test_model_name_derived_from_filename(self, tmp_path):
        """Model name key is the part after 'sortie-' and before '.yaml'."""
        self._write_yaml(
            tmp_path / "sortie-some-long-model-name.yaml",
            {"verdict": "pass"},
        )

        result = load_sortie_outputs(str(tmp_path))

        assert "some-long-model-name" in result
