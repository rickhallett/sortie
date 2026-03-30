"""Invoker module -- dispatches sortie prompts to models and collects results."""

from __future__ import annotations

import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import yaml

# ---------------------------------------------------------------------------
# Output sanitization patterns
# ---------------------------------------------------------------------------

_CLI_NOISE_PATTERNS: list[re.Pattern] = [
    re.compile(r"^mcp startup:.*$", re.MULTILINE),
    re.compile(r"^codex$", re.MULTILINE),
    re.compile(r"^tokens used$", re.MULTILINE),
    re.compile(r"^\d[\d,]*$", re.MULTILINE),
    re.compile(r"^OpenAI Codex v.*$", re.MULTILINE),
    re.compile(r'^Skill ".*" from ".*" is overriding.*$', re.MULTILINE),
]

_FENCE_RE: re.Pattern = re.compile(
    r"^```(?:yaml|YAML)?\n(.*?)\n?```",
    re.DOTALL | re.MULTILINE,
)


@dataclass
class CliResult:
    """Result of running a shell command.

    Attributes:
        stdout: Captured standard output.
        stderr: Captured standard error.
        returncode: Process exit code.
        timed_out: True if the process was killed due to timeout.
    """

    stdout: str
    stderr: str
    returncode: int
    timed_out: bool = False


@dataclass
class SortieResult:
    """Result of invoking a single sortie model.

    Attributes:
        model: The model identifier (e.g. "claude-3-5-sonnet").
        verdict: The verdict string from the model output.
        findings: List of finding dicts parsed from the model output.
        tokens: Token usage dict (e.g. {"input": 1000, "output": 500}).
        wall_time_ms: Wall-clock time in milliseconds for the invocation.
        raw_output: The raw string output from the model.
        error: Error message if the invocation failed, or None.
    """

    model: str
    verdict: str
    findings: list[dict] = field(default_factory=list)
    tokens: dict[str, int] = field(default_factory=dict)
    wall_time_ms: int = 0
    raw_output: str = ""
    error: str | None = None


def sanitize_output(raw: str) -> str:
    """Strip markdown fences and CLI noise from model output before YAML parsing.

    Args:
        raw: Raw string output from the model CLI invocation.

    Returns:
        Cleaned string suitable for YAML parsing, or the original string if
        stripping would produce an empty result.
    """
    text = raw.strip()

    # Try to extract content from a markdown fence
    match = _FENCE_RE.search(text)
    if match:
        text = match.group(1).strip()

    # Strip CLI noise lines
    for pattern in _CLI_NOISE_PATTERNS:
        text = pattern.sub("", text)

    # Collapse triple+ blank lines into at most one blank line
    text = re.sub(r"\n{3,}", "\n\n", text)

    text = text.strip()

    # If stripping produced empty output, return the original
    if not text:
        return raw

    return text


def build_prompt(prompt_path: str, diff: str, branch: str = "") -> str:
    """Read prompt file, substitute {branch}, and append diff in a code fence.

    The diff is appended after a '\\n---\\n' separator, wrapped in a ```diff
    code fence.

    Args:
        prompt_path: Path to the prompt template file.
        diff: The git diff string to append.
        branch: Branch name to substitute for {branch} placeholder.

    Returns:
        The fully assembled prompt string.
    """
    with open(prompt_path, "r") as f:
        prompt = f.read()

    prompt = prompt.replace("{branch}", branch)

    prompt = prompt + "\n---\n```diff\n" + diff + "\n```"
    return prompt


def parse_sortie_output(raw: str) -> SortieResult:
    """Parse a YAML string into a SortieResult.

    On malformed YAML or unexpected structure, returns a SortieResult with
    verdict="error" and a descriptive error message.

    Args:
        raw: Raw YAML output string from the model.

    Returns:
        A SortieResult populated from the parsed YAML.
    """
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        return SortieResult(
            model="",
            verdict="error",
            raw_output=raw,
            error=f"Failed to parse YAML: {exc}",
        )

    if not isinstance(data, dict):
        return SortieResult(
            model="",
            verdict="error",
            raw_output=raw,
            error=f"Expected YAML mapping, got {type(data).__name__}",
        )

    return SortieResult(
        model=data.get("model", ""),
        verdict=data.get("verdict", ""),
        findings=data.get("findings") or [],
        tokens=data.get("tokens") or {},
        wall_time_ms=data.get("wall_time_ms", 0),
        raw_output=raw,
        error=data.get("error", None),
    )


def invoke_cli(
    command: str,
    stdin_text: str | None,
    timeout: int,
    cwd: str,
) -> CliResult:
    """Run a shell command via subprocess and return its output.

    Args:
        command: Shell command string to execute.
        stdin_text: Text to pass to the process via stdin, or None.
        timeout: Seconds to wait before killing the process.
        cwd: Working directory for the subprocess.

    Returns:
        A CliResult with captured stdout, stderr, returncode, and timed_out flag.
    """
    stdin_bytes = stdin_text.encode() if stdin_text is not None else None

    try:
        proc = subprocess.run(
            command,
            shell=True,
            input=stdin_bytes,
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
        )
        return CliResult(
            stdout=proc.stdout.decode(errors="replace"),
            stderr=proc.stderr.decode(errors="replace"),
            returncode=proc.returncode,
            timed_out=False,
        )
    except subprocess.TimeoutExpired:
        return CliResult(
            stdout="",
            stderr="",
            returncode=-1,
            timed_out=True,
        )


def invoke_all(
    roster: list[dict],
    diff: str,
    prompt_path: str | None,
    branch: str,
    cwd: str,
) -> dict[str, SortieResult]:
    """Run all roster entries in parallel and collect SortieResults.

    For each entry:
    - invoke == "cli" with a "prompt" field: builds the prompt and pipes it to stdin.
    - invoke == "cli" without a "prompt" field: runs the command directly with no stdin.
    - invoke == "hook-agent": returns a SortieResult with an error message.

    Args:
        roster: List of roster entry dicts (must have "name" and "invoke" keys).
        diff: Git diff string passed to build_prompt when a prompt is used.
        prompt_path: Path to prompt template file (used when entry has no per-entry prompt).
        branch: Branch name substituted into the prompt template.
        cwd: Working directory for subprocesses.

    Returns:
        A dict mapping entry name -> SortieResult.
    """

    def _run_entry(entry: dict) -> tuple[str, SortieResult]:
        name = entry["name"]
        invoke = entry.get("invoke", "cli")
        t_start = time.monotonic()

        if invoke == "hook-agent":
            elapsed_ms = int((time.monotonic() - t_start) * 1000)
            return name, SortieResult(
                model=name,
                verdict="error",
                wall_time_ms=elapsed_ms,
                error="hook-agent invocation requires Claude Code runtime",
            )

        if invoke == "cli":
            command = entry.get("command", "")
            entry_prompt = entry.get("prompt")

            if entry_prompt:
                # Build a full prompt from the entry's prompt file and diff
                resolved_prompt_path = entry_prompt
                stdin_text = build_prompt(resolved_prompt_path, diff, branch=branch)
            elif prompt_path is not None:
                stdin_text = build_prompt(prompt_path, diff, branch=branch)
            else:
                stdin_text = None

            cli_result = invoke_cli(
                command=command,
                stdin_text=stdin_text,
                timeout=entry.get("timeout", 120),
                cwd=cwd,
            )
            elapsed_ms = int((time.monotonic() - t_start) * 1000)

            if cli_result.timed_out:
                return name, SortieResult(
                    model=name,
                    verdict="error",
                    wall_time_ms=elapsed_ms,
                    raw_output="",
                    error=f"Command timed out after {entry.get('timeout', 120)}s",
                )

            raw = cli_result.stdout
            result = parse_sortie_output(sanitize_output(raw))
            result.model = result.model or name
            result.wall_time_ms = elapsed_ms
            result.raw_output = raw
            return name, result

        # Unknown invoke type
        elapsed_ms = int((time.monotonic() - t_start) * 1000)
        return name, SortieResult(
            model=name,
            verdict="error",
            wall_time_ms=elapsed_ms,
            error=f"Unknown invoke type: {invoke!r}",
        )

    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(_run_entry, entry) for entry in roster]
        results = {}
        for future in futures:
            name, sortie_result = future.result()
            results[name] = sortie_result

    return results


def _invoke_single(
    entry: dict,
    diff: str,
    prompt_path: str | None,
    branch: str,
    cwd: str,
) -> SortieResult:
    """Invoke a single roster/debrief entry and return a SortieResult.

    Args:
        entry: Roster entry dict with at least "name" and "invoke" keys.
        diff: Git diff string (passed to build_prompt when prompt is used).
        prompt_path: Path to prompt template file (used if entry has no per-entry prompt).
        branch: Branch name substituted into the prompt template.
        cwd: Working directory for the subprocess.

    Returns:
        A SortieResult for the invocation.
    """
    results = invoke_all(
        roster=[entry],
        diff=diff,
        prompt_path=prompt_path,
        branch=branch,
        cwd=cwd,
    )
    return results[entry["name"]]
