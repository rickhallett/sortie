# Sortie

Sortie is a multi-model review harness for AI-generated code changes.

It runs independent reviews from Claude, Codex, and Gemini against the same diff, synthesizes their findings, applies severity-based merge gating, and records every result in an auditable ledger.

Sortie exists to answer four production questions:

- How do we evaluate AI-generated changes before merge?
- What happens when reviewers disagree?
- Where is the trust boundary?
- What does verification cost?

## What It Proves

Sortie demonstrates practical AI systems engineering:

- Evaluation harness design
- Cross-model verification
- Failure triage and merge gating
- Traceable audit records
- Token and cost accounting

This is not a chat wrapper. It is a controlled review system for measuring the quality of AI-assisted engineering work.

## Why

Most AI coding workflows have a weak verification story. A model proposes a change, a human skims it, and trust leaks across the boundary.

Sortie makes that boundary explicit.

Each reviewer sees the same diff independently. A debrief step synthesizes the review outputs. Convergent findings raise confidence. Divergent findings are preserved as evidence, but do not block by default. Every run records findings, verdicts, dispositions, and token cost in a structured ledger.

The result is a review pipeline that is measurable, auditable, and fail-closed by design.

### Design principles

- Legibility over magic
- Auditability over novelty
- Evaluation over vibes
- Constrained autonomy over theatrical autonomy
- Real traces over retrospective storytelling

## How it works

```
Worker finishes --> Lead prepares merge --> sortie pipeline <branch>
                                                |
                                +---------------+---------------+
                                |               |               |
                          sortie-claude    sortie-codex    sortie-gemini
                          (parallel)       (parallel)       (parallel)
                                |               |               |
                                +---------------+---------------+
                                                |
                                           debrief
                                      (4th invocation)
                                                |
                                         verdict.yaml
                                                |
                                +---------------+---------------+
                                |               |               |
                             PASS        PASS w/MINOR         FAIL
                             merge       merge + tasks    block + bounce
```

Each model reviews the diff independently. The debrief model triangulates findings:

- **Convergent** (2+ models found it): high confidence, blocks merge if severity warrants
- **Divergent** (1 model only): logged, never blocks, valuable for evaluating model priors over time

## Architecture Decisions

- Independent reviewers do not share context
- Divergent findings are logged, not blocking
- Convergence increases confidence, not truth
- The ledger is append-only and tied to run identity

## Quick start

```bash
# Install
uv sync

# Run all tests
uv run pytest tests/ -v

# Review a branch (full triad + debrief + triage)
uv run python scripts/sortie.py --config sortie.yaml pipeline <branch> --mode code

# Check run status
uv run python scripts/sortie.py --config sortie.yaml status

# Annotate a finding after remediation
uv run python scripts/sortie.py --config sortie.yaml dispose <run_id> <finding_id> fixed
```

## Configuration

All config in `sortie.yaml`:

```yaml
roster:
  - name: claude
    invoke: cli
    command: "claude -p"
    prompt: prompts/sortie-code.md
    timeout: 180
  - name: gemini
    invoke: cli
    command: "gemini -p \"\""
    prompt: prompts/sortie-code.md
    timeout: 180
  - name: codex
    invoke: cli
    command: "codex exec -"
    prompt: prompts/sortie-code.md
    timeout: 180

triage:
  block_on: [critical, major]   # loosen to [critical] if too slow
  max_remediation_cycles: 2
  convergence_threshold: 2

modes:
  code:   { trigger: merge, roster: [claude, codex, gemini] }
  tests:  { trigger: milestone, roster: [claude, gemini] }
  docs:   { trigger: milestone, roster: [claude] }
```

## Review modes

| Mode | Trigger | Roster | Blocks on | Reviews for |
|------|---------|--------|-----------|-------------|
| code | Every merge | Full triad | critical, major | Correctness, security, interface contracts, error handling, type safety |
| tests | Milestone | claude, gemini | critical | False greens, stub fidelity, assertion quality, coverage gaps |
| docs | Milestone | claude | Never | Accuracy vs code, stale references, contradictions |

## Ledger

Every run appends to `.sortie/ledger.yaml` (tracked in git). Captures: findings, convergence, tokens, wall time, diff stats, dispositions. No analysis tooling needed -- the ledger answers every operational question retrospectively:

- Sortie precision (% fixed vs false-positive)
- Model comparison (which models produce convergent findings)
- Cost economics (tokens per finding, cost per run)
- Convergence value (do convergent findings have higher fix rates)

## Core protocols

- **Tree hash identity**: `git write-tree` keys artifacts to staged content, not commit SHA
- **Attestation model**: each step writes YAML attestation, verified before merge
- **Convergence analysis**: debrief maps findings across models, scores by agreement
- **Severity-gated triage**: configurable `block_on` list, divergent findings never block

## Architecture

```
scripts/
  sortie.py          CLI entry point (pipeline, status, dispose)
  config.py          Load sortie.yaml, resolve mode overrides
  identity.py        Tree hash, run ID, cycle counting
  attestation.py     Write/read/verify attestation YAML
  invoker.py         Parallel model fan-out (cli, hook-agent)
  debrief.py         Synthesis prompt building, verdict writing
  triage.py          Severity-gated verdict evaluation
  ledger.py          Append-only YAML run data store
  sortie_hook.py     Claude Code pre-merge hook

prompts/             Markdown review prompts (code, tests, docs, debrief)
.sortie/             Runtime artifacts (gitignored except ledger.yaml)
```

## Dependencies

- Python 3.11+ (managed by uv)
- PyYAML (single runtime dependency)
- pytest (dev)
- Claude CLI, Gemini CLI, Codex CLI (for the respective roster entries)

## Test results

106 tests, all passing. Integration smoke test validates the full pipeline end-to-end with echo-based CLI stubs.

## Evaluations

- [Eval plan](docs/eval-plan.md) -- 10 evals covering auth, concurrency, money, I/O, security, state, time, and distributed systems
- [Eval 001: pidgeon-swarm](docs/eval-001-pidgeon-swarm.md) -- carrier integration service. 6 runs, 26 findings, 6 fix commits, zero human intervention.
- [Eval 002: rate limiter](docs/eval-002-rate-limiter.md) -- concurrency + time handling. Claude 100%, Codex 50%, Gemini 0%. 10 findings, 0 convergent (model reliability bottleneck).

## Design Basis

- [Research: academic papers and empirical findings](docs/research.md) -- 30+ papers on cross-model verification, LLM-as-judge for code, multi-agent debate, and consensus mechanisms
- [Landscape: repos and tools](docs/landscape.md) -- 40+ catalogued tools implementing adversarial or multi-model review patterns

## Lineage

Reimplements the gauntlet verification pipeline from [thepit](https://github.com/rickhallett/thepit). Clean-room implementation of proven protocols, not a fork.
