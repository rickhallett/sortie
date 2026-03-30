# Multi-Team Agentic Coding Harness

**Date:** 2026-03-30
**Status:** Design draft
**Runtime:** Pi coding agent (`@mariozechner/pi-coding-agent`)
**Repo:** To be created (working name: `sortie` repo expands, or new repo)

---

## System Overview

A configuration-driven multi-team coding architecture built on the Pi agent harness. Three tiers of agents (orchestrator, leads, workers) collaborate through a shared JSONL conversation log, with domain-locked file permissions and self-updating mental models.

The Validation Team (sortie) is an integrated, togglable team that runs adversarial multi-model review at merge boundaries.

## Three-Tier Architecture

```
ORCHESTRATOR (Opus, delegate-only, zero file writes)
│
├── PLANNING LEAD (Opus, read-only + delegate)
│   └── Planning workers (spec writing, task decomposition)
│
├── ENGINEERING LEAD (Opus, read-only + delegate)
│   ├── Frontend Worker (Sonnet, domain: src/frontend/)
│   ├── Backend Worker (Sonnet, domain: src/backend/)
│   ├── Database Worker (Sonnet, domain: src/db/)
│   └── ...
│
├── VALIDATION LEAD (Opus, read-only + delegate) [TOGGLABLE]
│   ├── Reviewer: Claude (Sonnet, read-only, full codebase)
│   ├── Reviewer: Gemini (read-only, full codebase)
│   ├── Reviewer: Codex (read-only, full codebase)
│   └── Debrief + Triage (uses sortie tooling)
│
└── SHARED STATE
    ├── session/conversation.jsonl   (all-agent chat log)
    ├── session/tool-calls.jsonl     (audit trail)
    ├── session/system-prompts/      (per-agent boot prompts)
    ├── .sortie/                     (verdicts, attestations, ledger)
    └── mental-models/               (per-agent expertise files)
```

## Configuration

Single YAML file drives the entire system.

```yaml
# harness.yaml

project:
  name: "carrier-integration-service"
  cwd: /path/to/project
  session_dir: .harness/session/

orchestrator:
  model: anthropic/claude-opus-4
  skills: [zero-micromanagement, conversational-response, mental-model-tracker]
  domain:
    read: ["**"]
    write: ["mental-models/orchestrator.md"]
  mental_model: mental-models/orchestrator.md
  mental_model_max_lines: 10000

teams:
  planning:
    enabled: true
    lead:
      name: planning-lead
      model: anthropic/claude-opus-4
      skills: [active-listener, conversational-response, mental-model-tracker, zero-micromanagement]
      domain:
        read: ["**"]
        write: ["mental-models/planning-lead.md"]
      mental_model: mental-models/planning-lead.md
    workers:
      - name: spec-writer
        model: anthropic/claude-sonnet-4
        skills: [active-listener]
        domain:
          read: ["**"]
          write: ["docs/**"]

  engineering:
    enabled: true
    lead:
      name: engineering-lead
      model: anthropic/claude-opus-4
      skills: [active-listener, conversational-response, mental-model-tracker, zero-micromanagement]
      domain:
        read: ["**"]
        write: ["mental-models/engineering-lead.md"]
      mental_model: mental-models/engineering-lead.md
    workers:
      - name: backend-dev
        model: anthropic/claude-sonnet-4
        skills: [active-listener]
        domain:
          read: ["**"]
          write: ["src/**", "tests/**"]
      - name: frontend-dev
        model: anthropic/claude-sonnet-4
        skills: [active-listener]
        domain:
          read: ["**"]
          write: ["src/frontend/**", "tests/**"]

  validation:
    enabled: true    # <-- TOGGLE: set false to skip review, save tokens
    lead:
      name: validation-lead
      model: anthropic/claude-opus-4
      skills: [active-listener, conversational-response, mental-model-tracker]
      domain:
        read: ["**"]
        write: ["mental-models/validation-lead.md", ".sortie/**"]
      mental_model: mental-models/validation-lead.md
    workers:
      - name: reviewer-claude
        model: anthropic/claude-sonnet-4
        skills: [active-listener]
        domain:
          read: ["**"]
          write: []
        expertise: prompts/sortie-code.md
      - name: reviewer-gemini
        model: google/gemini-2.5-pro
        skills: [active-listener]
        domain:
          read: ["**"]
          write: []
        expertise: prompts/sortie-code.md
      - name: reviewer-codex
        model: openai/gpt-4o
        skills: [active-listener]
        domain:
          read: ["**"]
          write: []
        expertise: prompts/sortie-code.md
    triage:
      block_on: [critical, major]
      max_remediation_cycles: 2
      convergence_threshold: 2

# API keys loaded from environment (ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY)
```

### Validation Toggle

When `validation.enabled: false`:
- Validation team is not spawned
- Merges proceed without review
- No sortie runs, no ledger entries, no token spend on review
- Engineering lead merges directly

When `validation.enabled: true`:
- Validation lead receives merge requests from engineering lead via JSONL log
- Spawns reviewer workers (one per model, read-only tools)
- Runs debrief + triage
- Gates merge on verdict

Toggle granularity options for future:

```yaml
validation:
  enabled: true
  modes:
    code: true       # review code changes
    tests: false     # skip test review (save tokens)
    docs: false      # skip doc review
  lite: false        # when true: single model review (cheapest), no debrief
```

## Tier Constraints

| Tier | Can Delegate | Can Write Files | Can Execute Bash | Model Tier |
|---|---|---|---|---|
| Orchestrator | Yes (to leads) | No (except own mental model) | No | Opus |
| Leads | Yes (to workers) | No (except own mental model + domain) | No | Opus |
| Workers | No | Yes (domain-locked) | Yes (domain-locked) | Sonnet |
| Reviewers | No | No | No | Sonnet/mixed |

### Domain Locking

Each agent has explicit `read` and `write` glob patterns. The Pi harness enforces these via `beforeToolCall` hooks:

```typescript
agent.beforeToolCall = async ({ toolCall, args }) => {
  if (toolCall.name === "write" || toolCall.name === "edit") {
    const path = args.path;
    if (!matchesGlobs(path, agent.config.domain.write)) {
      return { block: true, reason: `Write to ${path} blocked: outside domain` };
    }
  }
};
```

## Communication: JSONL Conversation Log

All agents read and write to a single JSONL file. Each line:

```json
{
  "timestamp": "2026-03-30T14:22:03Z",
  "from": "engineering-lead",
  "to": "backend-dev",
  "type": "task",
  "content": "Implement OAuth token caching in src/carriers/ups/auth.ts",
  "metadata": { "priority": "high", "files": ["src/carriers/ups/auth.ts"] }
}
```

Message types: `task`, `result`, `question`, `answer`, `merge-request`, `verdict`, `finding`, `status`.

**Active Listener skill** forces agents to read the conversation log before generating any response. This gives every agent full context on what's happening across all teams.

### Merge Request Flow

```
1. Engineering worker completes task
2. Engineering worker -> JSONL: { type: "result", content: "Done. Files: [...]" }
3. Engineering lead -> JSONL: { type: "merge-request", to: "validation-lead", content: "Review worker-b branch" }
4. If validation.enabled:
     Validation lead spawns reviewers
     Reviewers read conversation log + code
     Debrief produces verdict
     Validation lead -> JSONL: { type: "verdict", content: "PASS" or "FAIL + findings" }
5. If validation.enabled == false:
     Engineering lead merges directly
6. If FAIL:
     Engineering lead -> JSONL: { type: "finding", to: "backend-dev", content: "Fix: token expiry not checked" }
     Worker fixes, goto step 2
```

## Mental Models

Each agent maintains a personal expertise file (e.g., `mental-models/engineering-lead.md`). Updated autonomously via the **Mental Model Tracker** skill.

Contents:
- Key risks identified during work
- Missing infrastructure or patterns
- Codebase patterns learned
- Previous findings and their dispositions
- Cross-team context (what other teams are doing)

The orchestrator's mental model is capped at configurable max lines to prevent context bloat.

For hyper-specialized roles, read-only memory arrays can be injected:

```yaml
workers:
  - name: db-migration-worker
    model: anthropic/claude-sonnet-4
    expertise:
      - prompts/db-migration-rules.md    # read-only, agent cannot overwrite
      - prompts/sql-safety-checklist.md   # read-only
    mental_model: mental-models/db-migration-worker.md  # agent-writable
```

## Skills

Stored in `skills/` directory. Key skills:

| Skill | Used By | Purpose |
|---|---|---|
| `zero-micromanagement` | Orchestrator, leads | Delegate-only protocol. Never write code or execute commands directly. |
| `active-listener` | All agents | Read conversation log before responding. |
| `conversational-response` | Orchestrator, leads | Summarize concisely for humans and other leads. |
| `mental-model-tracker` | Orchestrator, leads | Maintain and update expertise file autonomously. |
| `tdd-worker` | Engineering workers | Test-driven development protocol. |
| `sortie-reviewer` | Validation workers | Adversarial code review with structured YAML output. |

Workers explicitly lack `conversational-response` -- they stay verbose and detailed.

## Session State

```
.harness/
  session/
    conversation.jsonl          # all-agent chat log
    tool-calls.jsonl            # every tool invocation, every agent
    system-prompts/
      orchestrator.md           # boot prompt (after variable injection)
      engineering-lead.md
      backend-dev.md
      ...
  mental-models/
    orchestrator.md
    engineering-lead.md
    validation-lead.md
    ...
  .sortie/                      # validation team artifacts
    ledger.yaml
    {tree_sha}-{cycle}/
      verdict.yaml
      sortie-{model}.yaml
      attestations/
```

## Bootstrapping

```bash
# Start the harness
pi-harness start --config harness.yaml

# Or with validation disabled (fast iteration mode)
pi-harness start --config harness.yaml --no-validation

# Or with lite validation (single model, no debrief)
pi-harness start --config harness.yaml --validation-lite
```

The harness:
1. Reads `harness.yaml`
2. Creates session directory
3. Spawns orchestrator Pi session with injected system prompt
4. Orchestrator reads user task, creates plan
5. Orchestrator delegates to leads via `delegate` tool
6. Leads spawn workers via `delegate` tool
7. Workers execute in domain-locked worktrees
8. On completion: merge-request -> validation (if enabled) -> merge

## What Sortie Becomes

Sortie's existing Python modules become tools available to the Validation Lead:

| Current Script | Becomes |
|---|---|
| `scripts/triage.py` | Pi tool: `sortie-triage` |
| `scripts/ledger.py` | Pi tool: `sortie-ledger` |
| `scripts/attestation.py` | Pi tool: `sortie-attest` |
| `scripts/analyze.py` | Pi tool: `sortie-analyze` |
| `scripts/identity.py` | Pi tool: `sortie-identity` |
| `prompts/*.md` | Reviewer expertise files |
| `sortie.yaml` | Absorbed into `harness.yaml` validation section |

The invoker (`scripts/invoker.py`) is replaced entirely -- Pi handles model invocation natively via `createAgentSession()`.

## Implementation Phases

### Phase 1: Pi-based sortie review (current)
- Replace CLI invocation with Pi CLI (`pi --provider X --model Y --tools read,grep,find,ls -p`)
- Prove tool-augmented review produces richer findings
- Run evals 003-010

### Phase 2: Harness skeleton
- Create `pi-harness` CLI that reads `harness.yaml`
- Spawn orchestrator + leads + workers via Pi SDK
- JSONL conversation log
- Domain locking via beforeToolCall hooks
- Validation toggle

### Phase 3: Full integration
- Mental models with autonomous updates
- Skills framework
- Overstory worktree management
- Cross-team context via active listener
- Sortie tools registered in Pi

### Phase 4: Production hardening
- Token budget tracking per team
- Graceful degradation when a model is unavailable
- Session resumption
- Parallel team execution (engineering + planning simultaneously)
