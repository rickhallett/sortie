# Sortie v2: Reliability and Eval Iteration

**Date:** 2026-03-30
**Status:** Design approved, pending implementation
**Driven by:** Eval 001 findings (`docs/eval-001-pidgeon-swarm.md`)

---

## Problem

Eval 001 showed sortie works end-to-end but has reliability and observability gaps:

- Claude 67%, Codex 20%, Gemini 17% success rate (parsing/invocation failures)
- 0/26 findings disposed (disposition workflow not triggered)
- No wall time or token data in ledger entries
- No detection of suspicious all-clear results

## Changes

### 1. Output Sanitization

Add `sanitize_output(raw: str) -> str` in `scripts/invoker.py`, called before `parse_sortie_output`:

1. Strip leading/trailing whitespace
2. Strip markdown code fences: `` ```yaml ... ``` ``, `` ```YAML ... ``` ``, bare `` ``` ... ``` ``
3. Strip lines matching CLI noise: `^mcp startup:`, `^codex$`, `^tokens used$`, `^\d+,?\d*$`, `^OpenAI Codex v`, `^---+$` at start/end
4. If empty after stripping, return original

### 2. Temp File Prompt Delivery

Replace stdin piping with temp file redirect in `scripts/invoker.py`:

- Write assembled prompt to `tempfile.NamedTemporaryFile(suffix='.md')`
- Invoke CLI with `< {tmp_path}` shell redirect
- Clean up temp file in `finally` block
- Eliminates `$(cat)` subshell pattern for Gemini
- Handles any diff size

Gemini config simplifies from `bash -c 'gemini -p "$(cat)"'` to `gemini -p`.

### 3. Disposition Bulk Command

**`scripts/ledger.py`:** Add `bulk_dispose(tree_sha, cycle, disposition)` -- marks all findings in a run with the same disposition.

**`scripts/sortie.py`:** Add `dispose-bulk <run_id> <disposition>` subcommand. Calls `ledger.bulk_dispose()` and updates all findings in `verdict.yaml`.

**Justfile:** Add `sortie-dispose-bulk` target.

### 4. Wall Time and Token Capture

**Wall time:** `cmd_pipeline` already has timing around `invoke_all`. Thread the elapsed ms into the ledger entry write.

**Tokens:** Add `extract_token_counts(stdout: str, stderr: str, model: str) -> dict[str, int]` in `scripts/invoker.py`:

- Claude: parse stderr for token stats
- Codex: parse "tokens used\nN,NNN" from stdout (before sanitization strips it)
- Gemini: not available in text mode, return empty dict
- Returns `{"prompt": N, "completion": M}` or `{}`

Token extraction runs before `sanitize_output` (which strips these lines). Best-effort: missing data acceptable, incorrect data is not.

Populate `SortieResult.tokens` from extraction. Pipeline threads per-model tokens into ledger entry.

### 5. Anti-Rubber-Stamp Check

In `scripts/triage.py`, within `triage_verdict`:

- If all roster models returned successfully (no errors) AND total findings across all models is 0
- Set `triage_result.all_clear_warning = "All models returned zero findings. Consider manual review."`
- Does not block. Advisory only.
- Surfaces in verdict.yaml and stdout.

## Files Modified

| File | Changes |
|---|---|
| `scripts/invoker.py` | `sanitize_output()`, `extract_token_counts()`, temp file delivery |
| `scripts/sortie.py` | `dispose-bulk` subcommand, wall_time/tokens in ledger write |
| `scripts/ledger.py` | `bulk_dispose()` method |
| `scripts/triage.py` | `all_clear_warning` field in TriageResult |
| `justfile` | `sortie-dispose-bulk` target |
| `tests/test_invoker.py` | Tests for sanitize, extract_tokens, temp file |
| `tests/test_ledger.py` | Tests for bulk_dispose |
| `tests/test_triage.py` | Test for all_clear_warning |
| `tests/test_sortie_cli.py` | Test for dispose-bulk subcommand |

## Not in Scope

- API-level token tracking (would require provider SDKs, not CLIs)
- Automatic disposition (lead must still decide)
- Retry on parse failure (fix the parsing, don't retry)
- New models or roster changes
