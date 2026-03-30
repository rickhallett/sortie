"""Tests for the invoker module."""

import time
import pytest
import yaml
from scripts.invoker import (
    CliResult,
    SortieResult,
    build_prompt,
    parse_sortie_output,
    sanitize_output,
    invoke_cli,
    invoke_all,
)


class TestBuildPrompt:
    def test_appends_diff_with_separator(self, tmp_path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("Review the changes.")
        diff = "diff --git a/foo.py b/foo.py\n+added line"

        result = build_prompt(str(prompt_file), diff)

        assert "Review the changes." in result
        assert "\n---\n" in result
        assert "```diff" in result
        assert diff in result
        assert "```" in result

    def test_substitutes_branch(self, tmp_path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("Branch: {branch}")

        result = build_prompt(str(prompt_file), "some diff", branch="feature/abc")

        assert "Branch: feature/abc" in result
        assert "{branch}" not in result

    def test_empty_branch_substitution(self, tmp_path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("Branch: {branch}")

        result = build_prompt(str(prompt_file), "some diff")

        assert "Branch: " in result
        assert "{branch}" not in result

    def test_diff_wrapped_in_code_fence(self, tmp_path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("Prompt text")
        diff = "+new line\n-removed line"

        result = build_prompt(str(prompt_file), diff)

        assert "```diff\n" in result
        assert diff in result
        assert result.endswith("```") or result.endswith("```\n")


class TestParseSortieOutput:
    def test_parses_valid_yaml(self):
        raw = yaml.dump({
            "model": "claude-3-5-sonnet",
            "verdict": "pass",
            "findings": [{"severity": "minor", "message": "unused import"}],
            "tokens": {"input": 100, "output": 50},
            "wall_time_ms": 1200,
        })

        result = parse_sortie_output(raw)

        assert result.model == "claude-3-5-sonnet"
        assert result.verdict == "pass"
        assert len(result.findings) == 1
        assert result.findings[0]["severity"] == "minor"
        assert result.tokens == {"input": 100, "output": 50}
        assert result.wall_time_ms == 1200

    def test_handles_empty_findings(self):
        raw = yaml.dump({
            "model": "gemini",
            "verdict": "pass",
            "findings": [],
        })

        result = parse_sortie_output(raw)

        assert result.findings == []
        assert result.verdict == "pass"

    def test_handles_malformed_yaml(self):
        raw = "this: is: not: valid: yaml: ]["

        result = parse_sortie_output(raw)

        assert result.verdict == "error"
        assert result.error is not None
        assert len(result.error) > 0

    def test_handles_non_dict_yaml(self):
        raw = yaml.dump(["list", "not", "dict"])

        result = parse_sortie_output(raw)

        assert result.verdict == "error"
        assert result.error is not None

    def test_raw_output_preserved(self):
        raw = yaml.dump({"model": "m", "verdict": "pass"})

        result = parse_sortie_output(raw)

        assert result.raw_output == raw

    def test_missing_optional_fields_use_defaults(self):
        raw = yaml.dump({"model": "m", "verdict": "block"})

        result = parse_sortie_output(raw)

        assert result.findings == []
        assert result.tokens == {}
        assert result.wall_time_ms == 0
        assert result.error is None


class TestInvokeCli:
    def test_captures_stdout(self):
        result = invoke_cli("echo hello", stdin_text=None, timeout=5, cwd="/tmp")

        assert result.stdout.strip() == "hello"
        assert result.returncode == 0
        assert result.timed_out is False

    def test_captures_stderr(self):
        result = invoke_cli(
            "python3 -c \"import sys; sys.stderr.write('err\\n')\"",
            stdin_text=None,
            timeout=5,
            cwd="/tmp",
        )

        assert "err" in result.stderr

    def test_passes_stdin(self):
        result = invoke_cli(
            "cat",
            stdin_text="hello from stdin",
            timeout=5,
            cwd="/tmp",
        )

        assert "hello from stdin" in result.stdout

    def test_timeout_returns_timed_out(self):
        result = invoke_cli("sleep 10", stdin_text=None, timeout=1, cwd="/tmp")

        assert result.timed_out is True
        assert result.returncode != 0

    def test_non_zero_exit_captured(self):
        result = invoke_cli("exit 42", stdin_text=None, timeout=5, cwd="/tmp")

        assert result.returncode == 42

    def test_cwd_respected(self, tmp_path):
        result = invoke_cli("pwd", stdin_text=None, timeout=5, cwd=str(tmp_path))

        assert str(tmp_path) in result.stdout


class TestInvokeAll:
    def test_returns_results_for_all_entries(self, tmp_path):
        roster = [
            {"name": "model-a", "invoke": "cli", "command": "echo result-a"},
            {"name": "model-b", "invoke": "cli", "command": "echo result-b"},
        ]

        results = invoke_all(
            roster=roster,
            diff="some diff",
            prompt_path=None,
            branch="main",
            cwd="/tmp",
        )

        assert "model-a" in results
        assert "model-b" in results

    def test_cli_without_prompt_runs_command(self, tmp_path):
        roster = [
            {"name": "echoer", "invoke": "cli", "command": "echo sortie-output"},
        ]

        results = invoke_all(
            roster=roster,
            diff="diff text",
            prompt_path=None,
            branch="",
            cwd="/tmp",
        )

        assert "echoer" in results
        # raw_output should contain the echo output
        assert "sortie-output" in results["echoer"].raw_output

    def test_cli_with_prompt_pipes_stdin(self, tmp_path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("Analyze branch: {branch}")

        roster = [
            {"name": "reader", "invoke": "cli", "command": "cat", "prompt": str(prompt_file)},
        ]

        results = invoke_all(
            roster=roster,
            diff="my diff",
            prompt_path=str(prompt_file),
            branch="feat/test",
            cwd="/tmp",
        )

        assert "reader" in results
        assert "feat/test" in results["reader"].raw_output

    def test_hook_agent_returns_error(self):
        roster = [
            {"name": "claude", "invoke": "hook-agent", "prompt": "prompts/sortie.md"},
        ]

        results = invoke_all(
            roster=roster,
            diff="diff",
            prompt_path=None,
            branch="",
            cwd="/tmp",
        )

        assert "claude" in results
        assert results["claude"].error is not None
        assert "hook-agent" in results["claude"].error

    def test_runs_in_parallel(self, tmp_path):
        # Two entries each sleep 1s -- parallel execution should finish in ~1s not ~2s
        roster = [
            {"name": "slow-a", "invoke": "cli", "command": "sleep 1 && echo done-a"},
            {"name": "slow-b", "invoke": "cli", "command": "sleep 1 && echo done-b"},
        ]

        start = time.monotonic()
        results = invoke_all(
            roster=roster,
            diff="",
            prompt_path=None,
            branch="",
            cwd="/tmp",
        )
        elapsed = time.monotonic() - start

        assert "slow-a" in results
        assert "slow-b" in results
        assert elapsed < 1.8, f"Expected parallel execution, took {elapsed:.2f}s"

    def test_wall_time_recorded(self):
        roster = [
            {"name": "timed", "invoke": "cli", "command": "echo hi"},
        ]

        results = invoke_all(
            roster=roster,
            diff="",
            prompt_path=None,
            branch="",
            cwd="/tmp",
        )

        assert results["timed"].wall_time_ms >= 0


class TestSanitizeOutput:
    def test_strips_markdown_yaml_fence(self):
        raw = "```yaml\nverdict: pass\nfindings: []\n```"
        result = sanitize_output(raw)
        assert result.strip() == "verdict: pass\nfindings: []"

    def test_strips_bare_markdown_fence(self):
        raw = "```\nverdict: pass\nfindings: []\n```"
        result = sanitize_output(raw)
        assert result.strip() == "verdict: pass\nfindings: []"

    def test_strips_uppercase_yaml_fence(self):
        raw = "```YAML\nverdict: pass\nfindings: []\n```"
        result = sanitize_output(raw)
        assert result.strip() == "verdict: pass\nfindings: []"

    def test_strips_codex_status_lines(self):
        raw = (
            "mcp startup: initialized\n"
            "codex\n"
            "tokens used\n"
            "1,234\n"
            "verdict: pass\n"
            "findings: []\n"
        )
        result = sanitize_output(raw)
        assert "mcp startup" not in result
        assert "tokens used" not in result
        assert "1,234" not in result
        assert "verdict: pass" in result

    def test_strips_codex_version_line(self):
        raw = "OpenAI Codex v1.2.3\nverdict: pass\nfindings: []\n"
        result = sanitize_output(raw)
        assert "OpenAI Codex" not in result
        assert "verdict: pass" in result

    def test_strips_leading_trailing_whitespace(self):
        raw = "  \n\nverdict: pass\nfindings: []\n\n  "
        result = sanitize_output(raw)
        assert result == result.strip()

    def test_passthrough_clean_yaml_unchanged(self):
        raw = "verdict: pass\nfindings: []\n"
        result = sanitize_output(raw)
        assert "verdict: pass" in result
        assert "findings: []" in result

    def test_empty_after_strip_returns_original(self):
        raw = "```yaml\n```"
        result = sanitize_output(raw)
        # Content inside fence is empty; should return original rather than empty string
        assert result == raw

    def test_extracts_yaml_from_mixed_content_with_fences(self):
        raw = (
            "Here is my analysis:\n"
            "```yaml\n"
            "verdict: fail\n"
            "findings:\n"
            "  - severity: critical\n"
            "    message: SQL injection\n"
            "```\n"
            "Let me know if you need more details.\n"
        )
        result = sanitize_output(raw)
        assert "verdict: fail" in result
        assert "SQL injection" in result
        assert "Here is my analysis" not in result
        assert "Let me know" not in result
