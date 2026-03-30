# Eval 002: Rate Limiter Service (2026-03-30)

Second sortie eval. Rate limiter with fixed window, sliding log, and token bucket algorithms. Tests sortie v2 (output sanitization, temp file delivery, token extraction) against concurrency + time-handling bug classes.

## Test Subject

**Project:** Rate limiter service (TypeScript, 3 algorithms, in-memory store)
**Complexity:** 4 workers, ~8 source files, 96 tests, 224 assertions
**Duration:** ~25 minutes wall clock
**Sortie version:** v2 (with output sanitization, temp file delivery)

## Swarm Structure

| Worker | Scope | Commits |
|---|---|---|
| Worker A | Types, store, factory, index | 1 feat |
| Worker B | Fixed window + tests | 1 feat |
| Worker C | Sliding window log + tests | 1 feat |
| Worker D | Token bucket + tests | 1 feat |

## Sortie Runs

6 sortie run directories, 3 captured in ledger (some used pre-enrichment schema).

| Run | Branch | Verdict | Findings | Convergent | Divergent |
|---|---|---|---|---|---|
| 1 | worker-a (core types) | PASS_WITH_FINDINGS | 4 | 0 | 4 |
| 2 | worker-a (cycle 3) | PASS_WITH_FINDINGS | 3 | 0 | 3 |
| 3 | worker-b + cycle 5 | PASS_WITH_FINDINGS | 3 | 0 | 3 |
| **Total** | | | **10** | **0 (0%)** | **10 (100%)** |

## Findings

| Severity | Count | Examples |
|---|---|---|
| Major | 5 | NaN/Infinity corrupts window reset; factory dispatches to nonexistent modules; token bucket resetAt incorrect; unbounded memory growth |
| Minor | 5 | MAX_SAFE_INTEGER overflow; tight-loop cleanup; in-place mutation; type cast bypass; overly broad config type |

All 10 findings were divergent (single model). Zero convergent findings.

### Key Findings

1. **`fixed-window.ts:45` -- NaN/Infinity windowMs corrupts reset logic** (major, divergent). `windowMs` and `maxRequests` are not validated. `NaN` propagates through arithmetic silently.

2. **`token-bucket.ts:71` -- resetAt incorrect after bucket drain** (major, divergent). After allowing a request that drains the bucket, `resetAt` should reflect the next refill time, but it returns the current window boundary.

3. **`token-bucket.ts:41` -- disabled store cleanup allows unbounded growth** (major, divergent). Token bucket creates store entries per key but never cleans expired ones.

4. **`factory.ts:19` -- factory dispatches to modules that don't exist on this branch** (major, divergent). Worker A's factory references worker B/C/D modules that haven't been merged yet -- would fail at runtime.

## Model Reliability (v2 vs v1)

| Model | Eval 001 (v1) | Eval 002 (v2) | Change |
|---|---|---|---|
| Claude | 67% (4/6) | **100% (4/4)** | +33pp |
| Codex | 20% (1/5) | **50% (2/4)** | +30pp |
| Gemini | 17% (1/6) | **0% (0/4)** | -17pp |

### Analysis

**Claude: 67% -> 100%.** The output sanitization (stripping markdown fences) fixed Claude's YAML parse failures. Claude was the most reliable reviewer in both evals and produced the most findings (6 in eval 002).

**Codex: 20% -> 50%.** Improved but still failing half the time. The YAML parse errors persist -- Codex wraps output in terminal formatting that the sanitizer doesn't fully strip. Need to examine the raw output to find new noise patterns.

**Gemini: 17% -> 0%.** Worse. The temp file delivery (`< tmpfile`) doesn't work with the current Gemini invocation. The env var prefix (`GEMINI_API_KEY=... gemini -p`) combined with file redirect may be hitting a shell parsing issue. Need to investigate -- possibly the env var assignment prevents the redirect from being parsed correctly.

## Convergence Analysis

**Zero convergent findings.** This is explained by model reliability: with Codex at 50% and Gemini at 0%, most runs had only Claude producing findings. Convergence requires 2+ models to independently find the same issue, which is mechanically impossible when only 1 model works.

In the one run where both Claude and Codex succeeded (cycle 5), they found different issues -- Claude caught the config type width problem, Codex found the memory growth and resetAt bugs. This is actually the intended behavior: different models finding different things. But sortie's current triage treats all divergent findings as advisory-only, which means real bugs found by only one working model are never blocking.

**Implication:** The convergence-only-blocks triage rule may need revisiting. When model reliability is low, requiring convergence for blocking means most real findings are advisory. A possible refinement: if only 1 model succeeded, treat its findings as if convergent (since there's no second opinion to converge with).

## Comparison with Eval 001

| Metric | Eval 001 | Eval 002 |
|---|---|---|
| Sortie runs | 6 | 6 (3 in ledger) |
| Total findings | 26 | 10 |
| Convergent rate | 23% | 0% |
| Critical findings | 1 | 0 |
| Fix commits triggered | 6 | 0 |
| Remediation cycles | 2 | 0 |
| Tests passing | 99 | 96 |
| Models working | Claude only (mostly) | Claude + Codex (partially) |

Eval 002 produced fewer findings overall (10 vs 26) and no blocking verdicts. All runs passed with advisory findings. This could mean:
1. The rate limiter code is cleaner than the carrier integration (fewer bugs to find)
2. Lower model reliability suppressed convergence, preventing blocking
3. The concurrency/time-handling bug classes are harder for models to catch by inspection

The third explanation is most likely -- the research (CodeJudgeBench, 2025) shows models are weakest on bugs that require reasoning about runtime behavior (races, timing) vs. structural bugs (missing validation, type mismatches).

## What Worked

1. **Claude at 100% reliability.** The v2 sanitization fix completely resolved Claude's parse failures.
2. **Codex improved.** 20% -> 50% success rate. When it worked, it found real bugs (memory growth, resetAt).
3. **Real findings.** The NaN/Infinity validation gap and unbounded memory growth are genuine defects.
4. **Wall time captured.** 281.4s total across 3 ledger runs (~94s average per run).

## What Needs Fixing

1. **Gemini invocation.** 0% success in eval 002. The `GEMINI_API_KEY=... gemini -p < tmpfile` shell command isn't working. Need to debug the exact shell parsing issue.
2. **Codex output sanitization.** 50% isn't enough. Need to capture and examine the raw Codex output that still fails parsing.
3. **Single-model triage rule.** When only 1 model succeeds, convergence is impossible. Should sortie treat single-model findings differently when the other models errored (vs. when they returned clean)?
4. **Disposition workflow.** Still 0 dispositions. The lead didn't call dispose-bulk.

## Final State

- 96 tests passing (224 assertions)
- 7 commits on main
- 6 sortie runs, 10 total findings, 0 fix commits
- Zero blocking verdicts (all PASS_WITH_FINDINGS)
