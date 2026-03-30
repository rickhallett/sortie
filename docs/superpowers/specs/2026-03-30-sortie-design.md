# Sortie: Async Adversarial Review for Swarm Workflows

**Date:** 2026-03-30
**Status:** Design approved, pending implementation
**Lineage:** Reimplements thepit's gauntlet protocols for async Claude Code Teams swarm context

---

## Why this exists

There are many AI demos and many AI wrappers.
There are far fewer systems that visibly answer the operational questions:

- How is agent intent specified?
- How is output evaluated?
- What happens when agents fail?
- What is the trust boundary?
- What context is loaded and why?
- What does this cost and is it worth it?

Sortie is an instrumented environment where the quality of agentic work is measurable. The repo matters less as "an AI tool" and more as a proving ground for making AI work legibly, reliably, and operationally.

### Design principles

- Legibility over magic
- Auditability over novelty
- Evaluation over vibes
- Constrained autonomy over theatrical autonomy
- Composable tools over monoliths
- Explicit context over accidental context
- Narrow tools over sprawling abstractions
- Real traces over retrospective storytelling

### Evaluation surface

At portfolio level, sortie demonstrates end-to-end agentic engineering:

- Specification precision
- Evaluation and quality judgment
- Decomposition and orchestration
- Failure diagnosis
- Trust and guardrail design
- Context architecture
- Token/cost economics

---

## System overview

Sortie is an async adversarial review system for Claude Code Teams swarm workflows. It runs a configurable roster of language models against a worker's diff at merge boundary, synthesizes findings through a debrief invocation, triages by severity, and either blocks merge or creates remediation tasks. All findings, dispositions, and cost data are captured in a structured ledger for operational evaluation.

```
Worker finishes --> Lead prepares merge --> just sortie-all <worktree-branch>
                                                 |
                                 +---------------+---------------+
                                 |               |               |
                           sortie-claude    sortie-codex    sortie-gemini
                           (parallel)       (parallel)       (parallel)
                                 |               |               |
                                 +---------------+---------------+
                                                 |
                                        just debrief
                                       (4th invocation)
                                                 |
                                          verdict.yaml
                                                 |
                                 +---------------+---------------+
                                 |               |               |
                              PASS        PASS w/MINOR         FAIL
                              merge       merge + tasks    block + bounce
```

Critical and major findings block merge by default. Configurable via `sortie.yaml`.

**Scope:** Tightly coupled to Claude Code Teams swarm workflows. Not a general-purpose tool.

**Lineage:** Reimplements thepit's gauntlet protocols (tree hash identity, convergence analysis, severity-gated triage, attestation model) for async swarm context. Clean-room implementation informed by proven patterns, not a fork.

---

## Configuration

All configuration lives in `sortie.yaml` at repo root. Single file.

```yaml
roster:
  - name: claude
    invoke: hook-agent
    prompt: prompts/sortie-code.md
    timeout: 180

  - name: codex
    invoke: cli
    command: "codex exec review --uncommitted"
    timeout: 180

  - name: gemini
    invoke: cli
    command: "gemini -p"
    prompt: prompts/sortie-code.md
    output_format: json
    timeout: 180

debrief:
  model: claude
  invoke: hook-agent
  prompt: prompts/debrief.md
  timeout: 120

triage:
  block_on:
    - critical
    - major
  max_remediation_cycles: 2
  convergence_threshold: 2

modes:
  code:
    prompt: prompts/sortie-code.md
    trigger: merge
    roster: [claude, codex, gemini]
    triage:
      block_on: [critical, major]

  tests:
    prompt: prompts/sortie-tests.md
    trigger: milestone
    roster: [claude, gemini]
    triage:
      block_on: [critical]

  docs:
    prompt: prompts/sortie-docs.md
    trigger: milestone
    roster: [claude]
    triage:
      block_on: []

ledger:
  path: .sortie/ledger.yaml
  capture:
    - findings
    - convergence
    - tokens
    - wall_time
    - diff_stats
    - disposition

deposition:
  dir: .sortie/{tree_sha}-{cycle}/
  keep_individual: true
```

### Configuration decisions

- **Roster is ordered but execution is parallel.** Order only matters for display/logging.
- **`invoke` is the extensibility point.** Three methods: `hook-agent` (Claude Code native), `cli` (shell out), `api` (future, for direct HTTP calls to model APIs).
- **`block_on` is the triage knob.** Default `[critical, major]`. Loosen to `[critical]` if operations are too slow, tighten to `[critical, major, minor]` for maximum correctness. Optimise for correctness first; speed is a given.
- **`max_remediation_cycles: 2`** prevents infinite loops. After 2 cycles, remaining findings are logged and escalated to lead for manual decision.
- **Modes** select which prompt, roster, and triage config to use. No separate code paths -- the core pipeline is mode-agnostic.
- **Top-level `roster` and `triage` are defaults.** Mode-level keys override them. A mode with its own `roster` ignores the top-level roster; a mode without one inherits it. Same for `triage`.

### Invocation methods and diff/prompt delivery

Each `invoke` method receives the diff and prompt differently:

- **`hook-agent`**: The prompt file is read and the diff is appended. The combined text is passed as the agent hook's instruction. Output is captured from stdout.
- **`cli` with `prompt`**: The prompt file is read, diff appended, and piped to the CLI command's stdin (e.g., `cat combined.md | gemini -p --output-format json`). Output is captured from stdout.
- **`cli` without `prompt`**: The CLI uses its own built-in review logic (e.g., `codex exec review`). The diff is provided via git state (the branch is checked out). Output is captured from stdout. The orchestrator parses the CLI's native output format into the sortie finding schema.

---

## Core protocols

Ported from thepit's gauntlet. Same design principles, new implementation.

### Tree hash identity

`git write-tree` captures the exact staged content before a commit exists. All sortie artifacts are keyed by tree SHA. Attestations are tied to content, not to a commit that doesn't exist yet. If staged content changes, attestations go stale.

### Run identity

Directory key is `{tree_sha}-{cycle}` where cycle is the remediation attempt number (1, 2, 3...). Cycle is determined mechanically by counting existing directories for that tree SHA -- no LLM in the loop.

If the tree SHA changes between cycles (worker actually fixed something), it's a new tree SHA, cycle 1. The link between "abc123ef failed, worker fixed, def456ab passed" lives in the ledger entries which share the same `worker_branch` value, not in the directory name.

### Attestation model

Each sortie step writes a YAML attestation to `.sortie/{tree_sha}-{cycle}/attestations/`:

```yaml
step: sortie-claude
tree_sha: abc123ef
cycle: 1
timestamp: 2026-03-30T14:22:03Z
verdict: pass_with_findings
findings_count: { critical: 0, major: 1, minor: 2 }
tokens: { prompt: 3420, completion: 890 }
wall_time_ms: 12400
```

The debrief writes its own attestation with the consolidated verdict. A verification step checks all required attestations exist and are current before merge proceeds.

### Convergence analysis

The debrief prompt receives all individual sortie outputs and performs:

1. **Mapping** -- identify when different models describe the same issue (same file, same concern, possibly different wording or line numbers)
2. **Scoring** -- findings from N+ models (configurable via `convergence_threshold`, default 2) = convergent (high confidence). Single-model findings = divergent (investigate).
3. **Verdict** -- PASS / PASS WITH FINDINGS / FAIL based on highest severity of convergent findings

### Severity-gated triage

| Verdict | Highest convergent severity | Action |
|---|---|---|
| PASS | none | Merge proceeds |
| PASS WITH FINDINGS | minor only | Merge proceeds, findings logged, remediation tasks optional |
| FAIL | major or critical | Merge blocked, findings bounced to worker |

Divergent findings (single-model) are always logged but never block. They are valuable for evaluating model priors over time but are not trustworthy enough to gate on alone.

### Remediation cycle

On FAIL: worker receives findings, fixes, lead re-runs `just sortie-all` against the updated worktree. Max 2 cycles (from config). After 2 failures, escalate to lead with full sortie history for manual decision.

---

## Review modes

Three modes with different prompts, rosters, triggers, and triage rules.

| Mode | Trigger | Roster | Blocks on | Reviews for |
|---|---|---|---|---|
| **code** | Every worktree merge | Full triad | critical, major | Correctness, security, interface contracts, error handling, type safety |
| **tests** | Milestone (manual) | claude, gemini | critical | Coverage gaps, false greens, stub fidelity, assertion quality, missing edge cases |
| **docs** | Milestone (manual) | claude | never blocks | Accuracy vs. code, missing steps, stale references, contradictions |

### Trigger types

- **`merge`** -- automatic, fires on every worktree merge (code mode default)
- **`milestone`** -- manual, lead invokes with `just sortie-all <branch> --mode tests`. Natural points: after all workers have merged, before PR creation, before delivery.

Deposition and ledger format are identical across modes. The `mode` field in ledger entries allows filtering by review type.

---

## Deposition and ledger

### Per-run deposition

```
.sortie/
  abc123ef-1/                          # tree SHA + cycle
    sortie-claude.yaml                 # raw findings from claude
    sortie-codex.yaml                  # raw findings from codex
    sortie-gemini.yaml                 # raw findings from gemini
    verdict.yaml                       # debrief output (consolidated, triaged)
    attestations/
      sortie-claude.yaml
      sortie-codex.yaml
      sortie-gemini.yaml
      debrief.yaml
  def456ab-1/                          # next run
    ...
  ledger.yaml                         # append-only, tracked in git
```

### Individual sortie output format

What each model produces:

```yaml
model: claude
tree_sha: abc123ef
worker_branch: worktree/worker-b
findings:
  - id: f-001
    severity: major
    file: src/carriers/ups/auth.ts
    line: 42
    category: security
    summary: "Token cached without expiry validation"
    detail: "OAuth token is stored but expiry timestamp is not checked before reuse..."
  - id: f-002
    severity: minor
    file: src/domain/validation.ts
    line: 18
    category: quality
    summary: "Zod schema allows empty string for city"
    detail: "..."
```

### Verdict format

What workers and lead actually read:

```yaml
tree_sha: abc123ef
cycle: 1
worker_branch: worktree/worker-b
mode: code
verdict: fail
debrief_model: claude
findings:
  - id: v-001
    severity: major
    convergence: convergent
    sources: [f-001, gf-003]
    file: src/carriers/ups/auth.ts
    line: 42
    category: security
    summary: "Token cached without expiry validation"
    detail: "..."
    disposition: null
  - id: v-002
    severity: minor
    convergence: divergent
    sources: [f-002]
    file: src/domain/validation.ts
    line: 18
    category: quality
    summary: "Zod schema allows empty string for city"
    disposition: null
```

Dispositions are annotated post-remediation via `just sortie-dispose`:
- `fixed` -- worker addressed the finding
- `false-positive` -- finding was incorrect
- `deferred` -- acknowledged but not fixing now
- `disagree` -- worker disputes the finding

### Ledger format

Append-only, one entry per run. Tracked in git. The eval artifact.

```yaml
runs:
  - tree_sha: abc123ef
    cycle: 1
    timestamp: 2026-03-30T14:22:03Z
    mode: code
    worker_branch: worktree/worker-b
    verdict: fail
    roster: [claude, codex, gemini]
    debrief_model: claude
    findings_total: 5
    findings_convergent: 2
    findings_divergent: 3
    by_severity: { critical: 0, major: 1, minor: 4 }
    tokens: { total: 12840, by_model: { claude: 4310, codex: 3920, gemini: 4610 } }
    wall_time_ms: 18400
    diff_stats: { files: 4, insertions: 127, deletions: 23 }
    remediation_cycle: 1
    dispositions: {}
```

The ledger answers every operational question without analysis tooling:
- **Sortie precision:** What % of findings were `fixed` vs `false-positive`?
- **Model comparison:** Which models produce the most convergent findings?
- **Cost economics:** Tokens per finding, cost per run, cost per verified fix
- **Swarm quality:** Defect rate by worker, by mode, by diff size
- **Convergence value:** Do convergent findings have higher fix rates than divergent?

---

## Invocation

### Justfile targets

```makefile
# Full pipeline: parallel sorties + debrief + triage
sortie-all branch mode='code':
    python3 scripts/sortie.py pipeline {{branch}} --mode {{mode}}

# Individual sortie run (all models)
sortie branch mode='code':
    python3 scripts/sortie.py run {{branch}} --mode {{mode}}

# Debrief only (after individual run)
debrief run_id:
    python3 scripts/sortie.py debrief {{run_id}}

# Show current sortie state
sortie-status:
    python3 scripts/sortie.py status

# Annotate finding disposition
sortie-dispose run_id finding_id disposition:
    python3 scripts/sortie.py dispose {{run_id}} {{finding_id}} {{disposition}}
```

### scripts/sortie.py

Core orchestrator, ~300-400 lines. Subcommands:

- **`run <branch> --mode <mode>`** -- diffs branch against main, reads roster from config for the given mode, fans out to models in parallel (subprocess per CLI model, agent hook for Claude), collects outputs, writes per-model YAML + attestations
- **`debrief <run_id>`** -- feeds all sortie outputs to debrief model, writes verdict.yaml + attestation
- **`pipeline <branch> --mode <mode>`** -- `run` + `debrief` + triage in one call. Prints verdict to stdout. Exit code: 0 = pass, 1 = fail, 2 = pass with findings
- **`status`** -- shows current sortie state for all recent runs
- **`dispose <run_id> <finding_id> <disposition>`** -- annotates finding disposition in verdict.yaml and ledger

### scripts/ledger.py

Ledger read/write/append, ~100 lines. Handles YAML serialization, append-only semantics, and disposition updates.

### scripts/sortie-hook.py

Claude Code hook glue, ~50 lines. Pre-merge check: is this a worktree branch merge? Does a passing verdict exist for the current tree SHA? Blocks merge if no verdict or failing verdict.

---

## Hooks integration

### Pre-merge gate

The lead orchestrator's `.claude/settings.json` (reference config in `hooks/settings.json`):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 scripts/sortie-hook.py pre-merge",
            "if": "Bash(git merge *)"
          }
        ]
      }
    ]
  }
}
```

Behavior:
- Detects worktree branch merges
- Checks for passing verdict for current tree SHA
- No verdict: prints "Run `just sortie-all <branch>` before merging", exits 2 (blocks)
- Failing verdict: prints findings summary, exits 2 (blocks)
- Passing verdict: exits 0 (proceeds)

The lead cannot accidentally merge unreviewed worktree branches.

### Findings feedback to workers

Lead-driven via Claude Code Teams messaging. Not automated. The lead reads the verdict, decides what to communicate, messages the worker. This is a deliberate trust boundary -- the lead remains in the loop for finding interpretation and remediation assignment.

---

## Prompts

All prompts are Markdown files in `prompts/`. Templated with `{variable}` substitution. The diff is appended after the prompt.

### prompts/sortie-code.md

Adversarial code review. Reviews for: correctness, security, interface contracts, error handling, type safety. Does NOT review for: style, formatting, missing tests, documentation, performance (unless algorithmic).

### prompts/sortie-tests.md

Test quality review. Reviews for: coverage gaps, false greens (tests that pass but don't verify), stub fidelity, assertion quality, missing edge cases. Does NOT review for: implementation quality.

### prompts/sortie-docs.md

Documentation accuracy review. Reviews for: accuracy vs. actual code, missing setup steps, stale references, internal contradictions. Does NOT review for: prose style, formatting.

### prompts/debrief.md

Synthesis prompt. Receives all individual sortie outputs. Tasks: map findings across models, score convergence, assign final severity, produce single verdict. Output matches verdict.yaml schema.

### Output format

All prompts instruct models to return YAML matching the sortie finding schema:

```yaml
findings:
  - id: f-NNN
    severity: critical | major | minor
    file: <path>
    line: <number>
    category: <category>
    summary: <one line>
    detail: <explanation>

verdict: pass | pass_with_findings | fail
```

---

## Repository structure

```
~/code/sortie/
  sortie.yaml                      # all configuration
  justfile                         # orchestration targets
  CLAUDE.md                        # agent instructions
  README.md                        # project overview and design principles
  .gitignore                       # .sortie/ runtime artifacts (except ledger)

  scripts/
    sortie.py                      # core orchestrator (~300-400 lines)
    sortie-hook.py                 # claude code hook glue (~50 lines)
    ledger.py                      # ledger read/write/append (~100 lines)

  prompts/
    sortie-code.md                 # adversarial code review
    sortie-tests.md                # test quality review
    sortie-docs.md                 # documentation accuracy review
    debrief.md                     # synthesis/triangulation

  hooks/
    settings.json                  # reference claude code hook config

  docs/
    superpowers/
      specs/
        2026-03-30-sortie-design.md  # this document

  .sortie/                         # runtime (gitignored except ledger)
    {tree_sha}-{cycle}/            # per-run deposition
      sortie-{model}.yaml
      verdict.yaml
      attestations/
    ledger.yaml                    # append-only, tracked in git
```

### Dependencies

- Python 3.10+ (stdlib)
- PyYAML (single external dependency)
- Gemini CLI (`gemini`) -- for gemini roster entry
- Codex CLI (`codex`) -- for codex roster entry
- Claude Code -- host environment

---

## Not in scope for v1

- Analysis tooling over the ledger (precision/recall dashboards, cost trend charts)
- `commit` trigger mode
- `api` invocation method (direct HTTP to model APIs)
- Automated finding-to-worker routing (lead remains in the loop)
- Pitkeel port (session telemetry)
- Walkthrough/human attestation gate (the lead's review serves this role)
- Multiple simultaneous sortie runs (one run at a time per branch)
