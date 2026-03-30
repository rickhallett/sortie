# Sortie v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix CLI output parsing reliability (67/20/17% → target 90%+), add bulk disposition, capture wall time and tokens, detect suspicious all-clear results.

**Architecture:** All changes are in existing files. No new modules. Output sanitization and token extraction are added to `scripts/invoker.py`. Temp file delivery replaces stdin piping in the same file. Bulk dispose is a new subcommand in `scripts/sortie.py` backed by a new method in `scripts/ledger.py`. Anti-rubber-stamp is 5 lines in `scripts/triage.py`.

**Tech Stack:** Python 3.11+, PyYAML, pytest. Same as v1.

**Spec:** `docs/superpowers/specs/2026-03-30-sortie-v2-design.md`

---

## File Map

| File | Changes | Task |
|---|---|---|
| `scripts/invoker.py` | Add `sanitize_output()`, `extract_token_counts()`, temp file delivery | Tasks 1, 2, 3 |
| `scripts/ledger.py` | Add `bulk_dispose()` method | Task 4 |
| `scripts/sortie.py` | Add `dispose-bulk` subcommand, wire wall_time/tokens to ledger | Tasks 4, 5 |
| `scripts/triage.py` | Add `all_clear_warning` field to TriageResult | Task 6 |
| `justfile` | Add `sortie-dispose-bulk` target | Task 4 |
| `tests/test_invoker.py` | Tests for sanitize, extract_tokens, temp file | Tasks 1, 2, 3 |
| `tests/test_ledger.py` | Tests for bulk_dispose | Task 4 |
| `tests/test_triage.py` | Test for all_clear_warning | Task 6 |
| `tests/test_sortie_cli.py` | Test for dispose-bulk subcommand | Task 4 |

---

### Task 1: Output Sanitization

**Files:**
- Modify: `scripts/invoker.py`
- Modify: `tests/test_invoker.py`

- [ ] **Step 1: Write failing tests for sanitize_output**

Add to `tests/test_invoker.py`:

```python
from scripts.invoker import sanitize_output


class TestSanitizeOutput:
    def test_strips_markdown_yaml_fence(self):
        raw = '```yaml\nfindings: []\nverdict: pass\n```'
        assert sanitize_output(raw) == 'findings: []\nverdict: pass'

    def test_strips_markdown_bare_fence(self):
        raw = '```\nfindings: []\nverdict: pass\n```'
        assert sanitize_output(raw) == 'findings: []\nverdict: pass'

    def test_strips_uppercase_yaml_fence(self):
        raw = '```YAML\nfindings: []\nverdict: pass\n```'
        assert sanitize_output(raw) == 'findings: []\nverdict: pass'

    def test_strips_codex_status_lines(self):
        raw = (
            'mcp startup: no servers\n'
            'codex\n'
            'findings: []\nverdict: pass\n'
            'tokens used\n'
            '2,079'
        )
        result = sanitize_output(raw)
        assert 'findings: []' in result
        assert 'verdict: pass' in result
        assert 'mcp startup' not in result
        assert 'tokens used' not in result
        assert '2,079' not in result

    def test_strips_codex_version_line(self):
        raw = 'OpenAI Codex v0.116.0\nfindings: []\nverdict: pass'
        result = sanitize_output(raw)
        assert 'OpenAI Codex' not in result
        assert 'findings: []' in result

    def test_strips_leading_trailing_whitespace(self):
        raw = '  \n\nfindings: []\nverdict: pass\n\n  '
        result = sanitize_output(raw)
        assert result == 'findings: []\nverdict: pass'

    def test_passthrough_clean_yaml(self):
        raw = 'findings:\n  - id: f-001\n    severity: major\nverdict: fail'
        assert sanitize_output(raw) == raw

    def test_empty_after_strip_returns_original(self):
        raw = '```yaml\n```'
        result = sanitize_output(raw)
        assert result == raw  # don't make it worse

    def test_multiple_fences_strips_outer(self):
        raw = 'Some text\n```yaml\nfindings: []\nverdict: pass\n```\nMore text'
        result = sanitize_output(raw)
        assert 'findings: []' in result
        assert 'verdict: pass' in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mrkai/code/sortie && uv run pytest tests/test_invoker.py::TestSanitizeOutput -v`
Expected: FAIL -- `ImportError: cannot import name 'sanitize_output'`

- [ ] **Step 3: Implement sanitize_output**

Add to `scripts/invoker.py` after the imports, before `build_prompt`:

```python
import re


# Patterns for CLI noise lines to strip
_CLI_NOISE_PATTERNS = [
    re.compile(r'^mcp startup:.*$', re.MULTILINE),
    re.compile(r'^codex$', re.MULTILINE),
    re.compile(r'^tokens used$', re.MULTILINE),
    re.compile(r'^\d[\d,]*$', re.MULTILINE),
    re.compile(r'^OpenAI Codex v.*$', re.MULTILINE),
    re.compile(r'^Skill ".*" from ".*" is overriding.*$', re.MULTILINE),
]

# Markdown fence pattern: ```yaml ... ``` or ```YAML ... ``` or ``` ... ```
_FENCE_RE = re.compile(
    r'```(?:yaml|YAML)?\s*\n(.*?)\n```',
    re.DOTALL,
)


def sanitize_output(raw: str) -> str:
    """Strip markdown fences and CLI noise from model output before YAML parsing.

    If the result is empty after stripping, returns the original to avoid
    making a bad situation worse.
    """
    text = raw.strip()

    # Try to extract content from markdown fences
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()

    # Strip CLI noise lines
    for pattern in _CLI_NOISE_PATTERNS:
        text = pattern.sub('', text)

    # Clean up blank lines left by stripping
    text = re.sub(r'\n{3,}', '\n\n', text).strip()

    # If we stripped everything, return original
    if not text:
        return raw

    return text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/mrkai/code/sortie && uv run pytest tests/test_invoker.py::TestSanitizeOutput -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Wire sanitize_output into the parse path**

In `scripts/invoker.py`, modify `_run_entry` inside `invoke_all` (line 229):

Change:
```python
            raw = cli_result.stdout
            result = parse_sortie_output(raw)
```

To:
```python
            raw = cli_result.stdout
            result = parse_sortie_output(sanitize_output(raw))
```

Also modify `cmd_pipeline` in `scripts/sortie.py` where the debrief output is parsed (line 204):

Change:
```python
                parsed = parse_sortie_output(cli_result.stdout)
```

To:
```python
                parsed = parse_sortie_output(sanitize_output(cli_result.stdout))
```

Add the import at the top of `scripts/sortie.py` (line 25):

Change:
```python
from scripts.invoker import invoke_all, invoke_cli, parse_sortie_output, _invoke_single, SortieResult  # noqa: E402
```

To:
```python
from scripts.invoker import invoke_all, invoke_cli, parse_sortie_output, sanitize_output, _invoke_single, SortieResult  # noqa: E402
```

- [ ] **Step 6: Run full test suite**

Run: `cd /Users/mrkai/code/sortie && uv run pytest tests/ -v`
Expected: All tests PASS (106 existing + 9 new = 115)

- [ ] **Step 7: Commit**

```bash
cd /Users/mrkai/code/sortie
git add scripts/invoker.py scripts/sortie.py tests/test_invoker.py
git commit -m "feat: output sanitization -- strip markdown fences and CLI noise before YAML parse"
```

---

### Task 2: Token Extraction

**Files:**
- Modify: `scripts/invoker.py`
- Modify: `tests/test_invoker.py`

- [ ] **Step 1: Write failing tests for extract_token_counts**

Add to `tests/test_invoker.py`:

```python
from scripts.invoker import extract_token_counts


class TestExtractTokenCounts:
    def test_codex_stdout_tokens(self):
        stdout = 'findings: []\nverdict: pass\ntokens used\n2,079'
        result = extract_token_counts(stdout, '', 'codex')
        assert result.get('total') == 2079

    def test_codex_stdout_no_commas(self):
        stdout = 'findings: []\nverdict: pass\ntokens used\n500'
        result = extract_token_counts(stdout, '', 'codex')
        assert result.get('total') == 500

    def test_claude_stderr_tokens(self):
        stderr = 'Input tokens: 1500\nOutput tokens: 300'
        result = extract_token_counts('', stderr, 'claude')
        assert result.get('prompt', 0) > 0 or result.get('total', 0) > 0

    def test_no_tokens_returns_empty(self):
        result = extract_token_counts('findings: []\nverdict: pass', '', 'gemini')
        assert result == {}

    def test_malformed_tokens_returns_empty(self):
        result = extract_token_counts('tokens used\nnot-a-number', '', 'codex')
        assert result == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mrkai/code/sortie && uv run pytest tests/test_invoker.py::TestExtractTokenCounts -v`
Expected: FAIL -- `ImportError`

- [ ] **Step 3: Implement extract_token_counts**

Add to `scripts/invoker.py` after `sanitize_output`:

```python
_CODEX_TOKENS_RE = re.compile(r'tokens used\s*\n([\d,]+)', re.IGNORECASE)
_CLAUDE_INPUT_RE = re.compile(r'[Ii]nput tokens?:\s*([\d,]+)')
_CLAUDE_OUTPUT_RE = re.compile(r'[Oo]utput tokens?:\s*([\d,]+)')


def extract_token_counts(stdout: str, stderr: str, model: str) -> dict[str, int]:
    """Best-effort extraction of token counts from CLI output.

    Parses known formats for Codex (stdout) and Claude (stderr).
    Returns empty dict if nothing parseable is found.
    """
    combined = stdout + '\n' + stderr

    # Codex: "tokens used\nN,NNN" in stdout
    codex_match = _CODEX_TOKENS_RE.search(stdout)
    if codex_match:
        try:
            total = int(codex_match.group(1).replace(',', ''))
            return {'total': total}
        except ValueError:
            pass

    # Claude: "Input tokens: N" and "Output tokens: N" in stderr
    input_match = _CLAUDE_INPUT_RE.search(combined)
    output_match = _CLAUDE_OUTPUT_RE.search(combined)
    if input_match or output_match:
        result = {}
        if input_match:
            try:
                result['prompt'] = int(input_match.group(1).replace(',', ''))
            except ValueError:
                pass
        if output_match:
            try:
                result['completion'] = int(output_match.group(1).replace(',', ''))
            except ValueError:
                pass
        if result:
            result['total'] = result.get('prompt', 0) + result.get('completion', 0)
            return result

    return {}
```

- [ ] **Step 4: Wire token extraction into _run_entry**

In `scripts/invoker.py`, in `_run_entry` inside `invoke_all`, after the `cli_result` is obtained and before `parse_sortie_output` (around line 229):

Change:
```python
            raw = cli_result.stdout
            result = parse_sortie_output(sanitize_output(raw))
            result.model = result.model or name
            result.wall_time_ms = elapsed_ms
            result.raw_output = raw
            return name, result
```

To:
```python
            raw = cli_result.stdout
            tokens = extract_token_counts(cli_result.stdout, cli_result.stderr, name)
            result = parse_sortie_output(sanitize_output(raw))
            result.model = result.model or name
            result.wall_time_ms = elapsed_ms
            result.raw_output = raw
            if tokens:
                result.tokens = tokens
            return name, result
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/mrkai/code/sortie && uv run pytest tests/test_invoker.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/mrkai/code/sortie
git add scripts/invoker.py tests/test_invoker.py
git commit -m "feat: token extraction -- best-effort parse from CLI stdout/stderr"
```

---

### Task 3: Temp File Prompt Delivery

**Files:**
- Modify: `scripts/invoker.py`
- Modify: `tests/test_invoker.py`

- [ ] **Step 1: Write failing test for temp file delivery**

Add to `tests/test_invoker.py`:

```python
import os


class TestTempFileDelivery:
    def test_large_prompt_delivered_via_file(self, tmp_path):
        """A prompt larger than typical shell arg limits should still work."""
        from scripts.invoker import invoke_all

        # Create a prompt file
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("Review {branch}:\n")

        # Large diff that would break $(cat) subshell
        large_diff = "+" * 300000  # 300KB

        roster = [
            {
                "name": "echo-stub",
                "invoke": "cli",
                "command": "head -c 20",  # just read first 20 bytes to prove delivery
                "prompt": str(prompt_file),
                "timeout": 10,
            },
        ]
        results = invoke_all(
            roster=roster,
            diff=large_diff,
            prompt_path=None,
            branch="test-branch",
            cwd=str(tmp_path),
        )
        # The command received input (head read something)
        result = results["echo-stub"]
        assert result.raw_output != ""

    def test_no_temp_file_leaked(self, tmp_path):
        """Temp files should be cleaned up after invocation."""
        from scripts.invoker import invoke_all
        import glob

        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("Review {branch}:\n")

        roster = [
            {
                "name": "echo-stub",
                "invoke": "cli",
                "command": "cat",
                "prompt": str(prompt_file),
                "timeout": 10,
            },
        ]

        before = set(glob.glob("/tmp/sortie-prompt-*"))
        invoke_all(
            roster=roster,
            diff="small diff",
            prompt_path=None,
            branch="test",
            cwd=str(tmp_path),
        )
        after = set(glob.glob("/tmp/sortie-prompt-*"))
        assert after == before  # no leaked files
```

- [ ] **Step 2: Run tests to verify current behavior**

Run: `cd /Users/mrkai/code/sortie && uv run pytest tests/test_invoker.py::TestTempFileDelivery -v`
Expected: Tests may pass or fail depending on current stdin behavior -- the goal is to establish the baseline.

- [ ] **Step 3: Implement temp file delivery**

In `scripts/invoker.py`, add `import tempfile` to the imports. Then modify the `_run_entry` function inside `invoke_all`. Replace the CLI invocation block (the `if invoke == "cli":` section):

Change the stdin delivery portion (lines 199-217):

```python
        if invoke == "cli":
            command = entry.get("command", "")
            entry_prompt = entry.get("prompt")

            if entry_prompt:
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
```

To:

```python
        if invoke == "cli":
            command = entry.get("command", "")
            entry_prompt = entry.get("prompt")

            if entry_prompt:
                resolved_prompt_path = entry_prompt
                stdin_text = build_prompt(resolved_prompt_path, diff, branch=branch)
            elif prompt_path is not None:
                stdin_text = build_prompt(prompt_path, diff, branch=branch)
            else:
                stdin_text = None

            # Deliver via temp file redirect to avoid shell arg length limits
            if stdin_text is not None:
                tmp_fd, tmp_path = tempfile.mkstemp(
                    prefix='sortie-prompt-', suffix='.md'
                )
                try:
                    with os.fdopen(tmp_fd, 'w') as tmp_f:
                        tmp_f.write(stdin_text)
                    cli_result = invoke_cli(
                        command=f"{command} < {tmp_path}",
                        stdin_text=None,
                        timeout=entry.get("timeout", 120),
                        cwd=cwd,
                    )
                finally:
                    os.unlink(tmp_path)
            else:
                cli_result = invoke_cli(
                    command=command,
                    stdin_text=None,
                    timeout=entry.get("timeout", 120),
                    cwd=cwd,
                )
```

Also add `import os` if not already present (it's not currently imported -- add it at the top).

Apply the same pattern in `cmd_pipeline` in `scripts/sortie.py` where the debrief is invoked (around line 197):

Change:
```python
                cli_result = invoke_cli(
                    command=debrief_entry.get("command", ""),
                    stdin_text=debrief_prompt,
                    timeout=debrief_entry.get("timeout", 120),
                    cwd=cwd,
                )
```

To:
```python
                tmp_fd, tmp_path = tempfile.mkstemp(
                    prefix='sortie-debrief-', suffix='.md'
                )
                try:
                    with os.fdopen(tmp_fd, 'w') as tmp_f:
                        tmp_f.write(debrief_prompt)
                    cli_result = invoke_cli(
                        command=f"{debrief_entry.get('command', '')} < {tmp_path}",
                        stdin_text=None,
                        timeout=debrief_entry.get("timeout", 120),
                        cwd=cwd,
                    )
                finally:
                    os.unlink(tmp_path)
```

Add `import tempfile` to `scripts/sortie.py` imports.

- [ ] **Step 4: Run full test suite**

Run: `cd /Users/mrkai/code/sortie && uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/mrkai/code/sortie
git add scripts/invoker.py scripts/sortie.py tests/test_invoker.py
git commit -m "feat: temp file prompt delivery -- eliminates shell arg length limits"
```

---

### Task 4: Bulk Disposition

**Files:**
- Modify: `scripts/ledger.py`
- Modify: `scripts/sortie.py`
- Modify: `justfile`
- Modify: `tests/test_ledger.py`
- Modify: `tests/test_sortie_cli.py`

- [ ] **Step 1: Write failing test for bulk_dispose in ledger**

Add to `tests/test_ledger.py`:

```python
class TestLedgerBulkDispose:
    def test_bulk_dispose_marks_all_findings(self, tmp_ledger):
        entry = {
            "tree_sha": "abc123ef",
            "cycle": 1,
            "verdict": "fail",
            "findings": [
                {"id": "v-001", "severity": "major", "disposition": None},
                {"id": "v-002", "severity": "minor", "disposition": None},
                {"id": "v-003", "severity": "major", "disposition": None},
            ],
        }
        tmp_ledger.append(entry)
        tmp_ledger.bulk_dispose("abc123ef", 1, "fixed")
        data = tmp_ledger.load()
        for finding in data["runs"][0]["findings"]:
            assert finding["disposition"] == "fixed"

    def test_bulk_dispose_nonexistent_run(self, tmp_ledger):
        with pytest.raises(ValueError, match="not found"):
            tmp_ledger.bulk_dispose("nonexistent", 1, "fixed")

    def test_bulk_dispose_overwrites_existing(self, tmp_ledger):
        entry = {
            "tree_sha": "abc123ef",
            "cycle": 1,
            "verdict": "fail",
            "findings": [
                {"id": "v-001", "severity": "major", "disposition": "deferred"},
                {"id": "v-002", "severity": "minor", "disposition": None},
            ],
        }
        tmp_ledger.append(entry)
        tmp_ledger.bulk_dispose("abc123ef", 1, "fixed")
        data = tmp_ledger.load()
        assert data["runs"][0]["findings"][0]["disposition"] == "fixed"
        assert data["runs"][0]["findings"][1]["disposition"] == "fixed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mrkai/code/sortie && uv run pytest tests/test_ledger.py::TestLedgerBulkDispose -v`
Expected: FAIL -- `AttributeError: 'Ledger' object has no attribute 'bulk_dispose'`

- [ ] **Step 3: Implement bulk_dispose in Ledger**

Add to `scripts/ledger.py` after `update_disposition`:

```python
    def bulk_dispose(
        self, tree_sha: str, cycle: int, disposition: str
    ) -> int:
        """Mark all findings in a run with the same disposition.

        Returns the number of findings updated.

        Raises:
            ValueError: if the run is not found.
        """
        data = self.load()

        target_run: Optional[dict] = None
        for run in data["runs"]:
            if run.get("tree_sha") == tree_sha and run.get("cycle") == cycle:
                target_run = run
                break

        if target_run is None:
            raise ValueError(
                f"Run not found: tree_sha={tree_sha!r} cycle={cycle}"
            )

        count = 0
        for finding in target_run.get("findings", []):
            finding["disposition"] = disposition
            count += 1

        self._write(data)
        return count
```

- [ ] **Step 4: Run ledger tests**

Run: `cd /Users/mrkai/code/sortie && uv run pytest tests/test_ledger.py -v`
Expected: All tests PASS

- [ ] **Step 5: Add dispose-bulk subcommand to CLI**

In `scripts/sortie.py`, add the handler after `cmd_dispose`:

```python
def cmd_dispose_bulk(args: argparse.Namespace, cfg: dict, config_dir: str) -> int:
    """Mark all findings in a run with the same disposition."""
    disposition = args.disposition
    if disposition not in VALID_DISPOSITIONS:
        print(
            f"Error: invalid disposition {disposition!r}. "
            f"Must be one of: {', '.join(sorted(VALID_DISPOSITIONS))}",
            file=sys.stderr,
        )
        return 1

    run_id_str: str = args.run_id

    try:
        last_dash = run_id_str.rfind("-")
        if last_dash == -1:
            raise ValueError("no '-' found")
        tree_sha = run_id_str[:last_dash]
        cycle = int(run_id_str[last_dash + 1:])
    except (ValueError, IndexError) as exc:
        print(f"Error: cannot parse run_id {run_id_str!r}: {exc}", file=sys.stderr)
        return 1

    # Update verdict.yaml
    sortie_dir = _sortie_base_dir(cfg, config_dir)
    rdir = run_dir(sortie_dir, tree_sha, cycle)
    verdict_path = os.path.join(rdir, "verdict.yaml")

    if os.path.isfile(verdict_path):
        with open(verdict_path, "r") as f:
            verdict_data = yaml.safe_load(f)
        for finding in verdict_data.get("findings", []):
            finding["disposition"] = disposition
        with open(verdict_path, "w") as f:
            yaml.dump(verdict_data, f, default_flow_style=False)

    # Update ledger
    ledger_path = cfg.get("ledger", {}).get("path", ".sortie/ledger.yaml")
    if not os.path.isabs(ledger_path):
        ledger_path = os.path.join(config_dir, ledger_path)

    ledger = Ledger(ledger_path)
    try:
        count = ledger.bulk_dispose(tree_sha, cycle, disposition)
        print(f"Disposed {count} finding(s) as {disposition!r} in run {run_id_str}")
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0
```

In `build_parser`, add the subcommand after the `dispose` parser:

```python
    # dispose-bulk
    p_dispose_bulk = sub.add_parser("dispose-bulk", help="Mark all findings in a run with same disposition")
    p_dispose_bulk.add_argument("run_id", help="Run identifier (tree_sha-cycle)")
    p_dispose_bulk.add_argument(
        "disposition",
        help="One of: fixed, false-positive, deferred, disagree",
    )
```

In the `dispatch` dict in `main`, add:

```python
        "dispose-bulk": cmd_dispose_bulk,
```

- [ ] **Step 6: Write CLI test for dispose-bulk**

Add to `tests/test_sortie_cli.py`:

```python
class TestSortieDisposeBulk:
    def test_dispose_bulk_marks_all(self, tmp_path):
        sortie_dir = tmp_path / ".sortie"
        run_path = sortie_dir / "abc123ef-1"
        run_path.mkdir(parents=True)

        verdict_data = {
            "tree_sha": "abc123ef",
            "cycle": 1,
            "verdict": "fail",
            "findings": [
                {"id": "v-001", "severity": "major", "disposition": None},
                {"id": "v-002", "severity": "minor", "disposition": None},
            ],
        }
        with open(run_path / "verdict.yaml", "w") as f:
            yaml.dump(verdict_data, f)

        ledger_data = {
            "runs": [
                {
                    "tree_sha": "abc123ef",
                    "cycle": 1,
                    "verdict": "fail",
                    "findings": [
                        {"id": "v-001", "severity": "major", "disposition": None},
                        {"id": "v-002", "severity": "minor", "disposition": None},
                    ],
                },
            ]
        }
        with open(sortie_dir / "ledger.yaml", "w") as f:
            yaml.dump(ledger_data, f)

        cfg_path = tmp_path / "sortie.yaml"
        cfg_path.write_text(yaml.dump({
            "roster": [],
            "debrief": {"model": "claude", "invoke": "hook-agent", "prompt": "p.md", "timeout": 60},
            "triage": {"block_on": [], "max_remediation_cycles": 2, "convergence_threshold": 2},
            "modes": {"code": {"prompt": "p.md", "trigger": "merge"}},
            "ledger": {"path": str(sortie_dir / "ledger.yaml")},
            "deposition": {"dir": str(sortie_dir) + "/{tree_sha}-{cycle}/", "keep_individual": True},
        }))

        result = subprocess.run(
            ["uv", "run", "python", os.path.join(SORTIE_DIR, "scripts", "sortie.py"),
             "dispose-bulk", "abc123ef-1", "fixed",
             "--config", str(cfg_path)],
            capture_output=True, text=True, cwd=SORTIE_DIR,
        )
        assert result.returncode == 0
        assert "2 finding(s)" in result.stdout

        with open(run_path / "verdict.yaml") as f:
            updated = yaml.safe_load(f)
        assert all(f["disposition"] == "fixed" for f in updated["findings"])
```

- [ ] **Step 7: Update justfile**

Add to the `justfile`:

```makefile
# Bulk-dispose all findings in a run
sortie-dispose-bulk run_id disposition:
    uv run python scripts/sortie.py dispose-bulk {{run_id}} {{disposition}}
```

- [ ] **Step 8: Run full test suite**

Run: `cd /Users/mrkai/code/sortie && uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 9: Commit**

```bash
cd /Users/mrkai/code/sortie
git add scripts/ledger.py scripts/sortie.py justfile tests/test_ledger.py tests/test_sortie_cli.py
git commit -m "feat: dispose-bulk -- mark all findings in a run with one command"
```

---

### Task 5: Wall Time in Ledger

**Files:**
- Modify: `scripts/sortie.py`

- [ ] **Step 1: Add wall time tracking to cmd_pipeline**

In `scripts/sortie.py`, add `import time` to the imports. Then in `cmd_pipeline`, wrap the invoke_all + debrief section with timing:

Before line 141 (`# 5. Invoke all roster models in parallel`), add:

```python
    pipeline_start = time.monotonic()
```

After the triage (around line 268), before the ledger append, compute:

```python
    pipeline_wall_ms = int((time.monotonic() - pipeline_start) * 1000)
```

In the ledger append dict (around line 274), add `wall_time_ms`:

```python
    ledger.append({
        ...existing fields...
        "wall_time_ms": pipeline_wall_ms,
        "tokens": {
            "by_model": {
                name: dict(result.tokens) for name, result in sortie_results.items()
            },
            "total": sum(
                sum(r.tokens.values()) for r in sortie_results.values()
            ),
        },
    })
```

- [ ] **Step 2: Run full test suite**

Run: `cd /Users/mrkai/code/sortie && uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
cd /Users/mrkai/code/sortie
git add scripts/sortie.py
git commit -m "feat: wall time and token data in ledger entries"
```

---

### Task 6: Anti-Rubber-Stamp Check

**Files:**
- Modify: `scripts/triage.py`
- Modify: `tests/test_triage.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_triage.py`:

```python
class TestAntiRubberStamp:
    def test_all_clear_warning_when_no_findings(self):
        verdict = {"verdict": "pass", "findings": []}
        triage_cfg = {"block_on": ["critical", "major"], "convergence_threshold": 2}
        result = triage_verdict(verdict, triage_cfg)
        assert result.all_clear_warning is not None
        assert "zero findings" in result.all_clear_warning.lower()

    def test_no_warning_when_findings_exist(self):
        verdict = {
            "verdict": "pass_with_findings",
            "findings": [
                {"id": "v-001", "severity": "minor", "convergence": "divergent"},
            ],
        }
        triage_cfg = {"block_on": ["critical", "major"], "convergence_threshold": 2}
        result = triage_verdict(verdict, triage_cfg)
        assert result.all_clear_warning is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/mrkai/code/sortie && uv run pytest tests/test_triage.py::TestAntiRubberStamp -v`
Expected: FAIL -- `AttributeError: 'TriageResult' has no attribute 'all_clear_warning'`

- [ ] **Step 3: Add all_clear_warning to TriageResult and triage_verdict**

In `scripts/triage.py`, add the field to `TriageResult`:

```python
@dataclass
class TriageResult:
    action: str
    exit_code: int
    blocking_findings: list[dict] = field(default_factory=list)
    advisory_findings: list[dict] = field(default_factory=list)
    all_clear_warning: str | None = None
```

At the end of `triage_verdict`, before the final return, add:

```python
    if not findings:
        return TriageResult(
            action="merge",
            exit_code=0,
            all_clear_warning="All models returned zero findings. Consider manual review.",
        )
```

Replace the existing `return TriageResult(action="merge", exit_code=0)` at the bottom.

- [ ] **Step 4: Wire warning into pipeline output**

In `scripts/sortie.py` in `cmd_pipeline`, after printing the summary (around line 294), add:

```python
    if triage_result.all_clear_warning:
        print(f"Warning: {triage_result.all_clear_warning}")
```

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/mrkai/code/sortie && uv run pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/mrkai/code/sortie
git add scripts/triage.py scripts/sortie.py tests/test_triage.py
git commit -m "feat: anti-rubber-stamp -- warn when all models return zero findings"
```

---

## Task Dependency Summary

```
Task 1 (sanitize) ──> Task 2 (tokens, depends on sanitize being in place)
                  ──> Task 3 (temp file, modifies same invoke block)
Task 4 (bulk dispose) ── independent
Task 5 (wall time) ── independent (but commit after Task 2 for clean tokens)
Task 6 (anti-rubber-stamp) ── independent
```

Tasks 4 and 6 are fully independent. Tasks 1→2→3 are sequential (same file, same code region). Task 5 depends on Task 2 for token data.

Recommended order: 1 → 2 → 3 → 5 → 4 → 6.
