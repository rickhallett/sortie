# Eval 001: Sortie on pidgeon-swarm (2026-03-30)

First end-to-end test of sortie integrated with a Claude Code Teams swarm build. Human out of the loop -- the lead orchestrator ran sortie autonomously, bounced findings to workers, and merged only after passing review.

## Test Subject

**Project:** Carrier Integration Service (TypeScript, UPS Rating API wrapper)
**Source:** Design spec from Cybership take-home assessment
**Complexity:** 4 workers, ~20 source files, 99 tests, 229 assertions
**Duration:** ~30 minutes wall clock (scaffold to final merge)

## Swarm Structure

| Worker | Scope | Commits | Fix Commits |
|---|---|---|---|
| Worker A | Domain types, errors, validation, config | 1 feat | 2 fixes (sortie cycle 1 + cycle 2) |
| Worker B | UPS OAuth auth, HTTP client, API types | 3 feats | 1 fix |
| Worker C | UPS mapper, carrier implementation | 2 feats | 1 fix |
| Worker D | Service facade, registry, test fixtures | 3 feats | 1 fix |
| Lead | Final integration | 1 feat | 1 fix |

## Sortie Runs

| Run | Branch | Verdict | Findings | Convergent | Divergent |
|---|---|---|---|---|---|
| 1 | worker-a/domain | **FAIL** | 4 | 2 | 2 |
| 2 | worker-a/domain (cycle 2) | PASS_WITH_FINDINGS | 4 | 2 | 2 |
| 3 | worker-b/ups-auth-client | PASS_WITH_FINDINGS | 4 | 1 | 3 |
| 4 | worker-d/service-registry | PASS_WITH_FINDINGS | 4 | 0 | 4 |
| 5 | worker-c/ups-mapper-carrier | PASS_WITH_FINDINGS | 5 | 1 | 4 |
| 6 | final (tests mode) | PASS_WITH_FINDINGS | 5 | 0 | 5 |
| **Total** | | | **26** | **6 (23%)** | **20 (77%)** |

## Findings by Severity

| Severity | Count | Examples |
|---|---|---|
| Critical | 1 | Hardcoded Gemini API key committed to repo in cleartext |
| Major | 15 | Token response cast without runtime validation; 5xx errors marked non-retryable; account number omitted from rate requests; country code accepts arbitrary 2-char strings |
| Minor | 10 | NaN silently converted to 0; negative cache duration; btoa may throw on non-ASCII |

## Findings by Category

| Category | Count |
|---|---|
| correctness | 9 |
| interface | 8 |
| security | 4 |
| error-handling | 4 |
| type-safety | 1 |

## Model Reliability

| Model | Runs | Errors | Success Rate | Findings Produced |
|---|---|---|---|---|
| Claude | 6 | 2 | 67% | 15 |
| Codex | 5 | 4 | 20% | 1 |
| Gemini | 6 | 5 | 17% | 3 |

### Failure Modes

- **Codex:** YAML parse failures in 4/5 runs. Codex CLI wraps output in status lines and formatting that breaks YAML parsing. The `codex exec -` invocation captures the full terminal output, not just the model response.
- **Gemini:** NoneType in 5/6 runs. The `bash -c 'gemini -p "$(cat)"'` pattern hits argument length limits when the prompt+diff exceeds shell arg max. When Gemini did work (run 1), it found 3 findings including the critical API key leak.
- **Claude:** Most reliable at 67%. The 2 failures were YAML parse errors when Claude wrapped responses in markdown code fences despite the prompt saying not to.

### Implication

The triad concept is validated by the research (ReConcile, ACL 2024; verification payoff paper). But CLI invocation reliability is the bottleneck -- not model quality. Codex and Gemini both found real issues when they worked. The invoker needs better output sanitization: strip markdown fences, status lines, and terminal formatting before parsing.

## Sortie-Triggered Fixes

6 fix commits directly caused by sortie findings:

| Commit | Branch | Fixes Applied |
|---|---|---|
| `7d21f1d` | worker-a | Remove hardcoded API key, fix hook paths, add validation error paths, make state optional |
| `e976c40` | worker-a (cycle 2) | State truly optional, ISO 3166 country validation, NaN timeout guard, street array cap |
| `8d3cab1` | worker-b | Auth fetch try-catch, runtime token validation, expiry buffer clamp, 5xx retryable |
| `5f28baa` | worker-d | String carrier code acceptance with validation |
| `fd36965` | worker-c | Account number threading, NaN parseFloat guard, HTTPS enforcement, RatedShipment check |
| `ba57172` | final | Derive carrier codes from const, domain allowlist, NaN throw instead of silent 0 |

## Remediation Flow

Worker A was the only branch that required a second sortie cycle:

1. **Cycle 1 (FAIL):** Critical finding -- API key in sortie.yaml. 2 convergent + 2 divergent findings.
2. Worker A fixed 4 findings (credential leak, paths, validation, state optionality)
3. **Cycle 2 (PASS_WITH_FINDINGS):** Remaining findings were major/minor, all convergent. Worker A addressed state/country/NaN/street issues.
4. Merged after cycle 2.

All other workers passed on first sortie (PASS_WITH_FINDINGS). Their findings were advisory (no critical/major convergent findings blocking).

## Convergence Analysis

Only 23% of findings were convergent (2+ models agreed). This is lower than expected and is explained by the model reliability data: with Codex at 20% success and Gemini at 17%, most runs had only 1 working model (Claude), making convergence mechanically impossible.

**When multiple models DID produce output** (run 1: Claude + Gemini):
- 2/4 findings were convergent
- Both models independently found the hardcoded API key (critical)
- Both independently flagged validation schema issues (major)

This suggests the convergence rate would be substantially higher with reliable CLI invocation.

## What Worked

1. **Merge gating worked.** Worker A was blocked (FAIL verdict) until findings were addressed. All other branches had sortie run before merge.
2. **Remediation cycle worked.** Worker A fixed findings, lead re-ran sortie, passed on cycle 2.
3. **The lead ran sortie autonomously.** No human intervention for 6 sortie runs + 6 fix cycles.
4. **Real bugs caught.** The API key leak (critical), missing account number in rate requests (major), and 5xx non-retryable error classification (major) are genuine defects that would have shipped.
5. **Ledger captured everything.** 32KB of structured data across 6 runs, queryable retrospectively.

## What Needs Fixing

1. **CLI output parsing.** Codex and Gemini failures are invocation/parsing issues, not model quality. Need: strip markdown fences, strip terminal status lines, extract YAML from mixed output.
2. **Gemini arg length.** The `$(cat)` pattern hits shell limits. Need: write prompt to temp file, pass as `--prompt-file` or pipe differently.
3. **Dispositions not used.** No findings were disposed (fixed/false-positive/deferred/disagree). The lead should annotate dispositions after each fix cycle.
4. **Wall time not captured.** The ledger entries lack wall_time_ms. The pipeline's timing instrumentation needs to propagate to ledger writes.
5. **Token counts not captured.** None of the CLI invocations report token usage. Need to parse CLI output for token stats or use API-level tracking.

## Operational Questions Answered

| Question | Answer |
|---|---|
| How is agent output evaluated? | 3-model triad + debrief synthesis + severity triage |
| What happens when agents fail? | FAIL verdict blocks merge, findings bounced to worker, max 2 cycles |
| What is the trust boundary? | Convergent findings block; divergent are advisory only |
| What does this cost? | ~4 LLM invocations per sortie run (3 roster + 1 debrief). Token data not yet captured. |
| Did multi-model add value? | Yes when models worked -- the only critical finding (API key) was convergent across Claude + Gemini |

## Final State

- 99 tests passing (229 assertions)
- 20 commits on swarm-sortie-test branch
- 6 sortie runs, 26 total findings, 6 fix commits
- Zero human intervention from scaffold to final merge
