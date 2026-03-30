# Sortie v3: Pi SDK Invoker

**Date:** 2026-03-30
**Status:** Design draft
**Dependency:** `@mariozechner/pi-coding-agent` (v0.64.0+, github.com/badlogic/pi-mono)

---

## The Problem

Sortie v1/v2 invokes models via flat text: `claude -p < prompt.md`. The model reads a diff and returns YAML findings. It cannot:

- Read the full file being changed (only sees the diff)
- Read imported modules, interfaces, or types referenced in the diff
- Run `tsc --noEmit` to check if the code actually compiles
- Run tests to see if they pass
- Look at git blame or history for context
- Navigate the codebase to understand architectural intent

This is the difference between "review this diff" and "review this change in the context of the full codebase." Every human reviewer does the latter. Sortie v1/v2 does the former.

## The Fix

Replace CLI text invocation with Pi SDK agent sessions. Each sortie reviewer becomes a Pi agent with read-only tool access to the full repository.

## Architecture

```
sortie pipeline <branch>
    |
    +-- spawn Pi session (claude) ----+
    +-- spawn Pi session (gemini) ----+-- parallel, each with:
    +-- spawn Pi session (codex) -----+   - read-only tools (read, grep, find, ls)
                                          - full repo access via cwd
                                          - review prompt as system prompt
                                          - diff injected as initial message
                                          - structured output via session.state.messages
    |
    v
    collect findings from each session
    |
    v
    debrief (Pi session or CLI, configurable)
    |
    v
    triage -> verdict -> ledger (unchanged)
```

## Pi SDK Integration

### Session Creation

```typescript
import { createAgentSession, readOnlyTools, SessionManager } from "@mariozechner/pi-coding-agent";
import { getModel } from "@mariozechner/pi-ai";

const { session } = await createAgentSession({
  cwd: "/path/to/project",
  model: getModel("anthropic", "claude-sonnet-4-20250514"),
  tools: readOnlyTools,  // [read, grep, find, ls] -- no write, no edit, no bash
  sessionManager: SessionManager.inMemory(),
  resourceLoader: new DefaultResourceLoader({
    systemPromptOverride: () => sortieCodePrompt,
  }),
});
```

### Model Selection per Roster Entry

```yaml
# sortie.yaml
roster:
  - name: claude
    invoke: pi-sdk
    provider: anthropic
    model: claude-sonnet-4-20250514
    tools: [read, grep, find, ls]
    timeout: 180

  - name: gemini
    invoke: pi-sdk
    provider: google
    model: gemini-2.5-pro
    tools: [read, grep, find, ls]
    timeout: 180

  - name: codex
    invoke: pi-sdk
    provider: openai
    model: gpt-4o
    tools: [read, grep, find, ls]
    timeout: 180
```

A new `invoke: pi-sdk` method alongside the existing `cli` and `hook-agent`.

### Review Flow per Session

1. Create session with read-only tools + system prompt (the sortie review prompt)
2. Send initial message: the diff + instruction to produce YAML findings
3. The model can use tools to explore:
   - `read` files referenced in the diff
   - `grep` for usages of changed functions
   - `find` related test files
   - `ls` directory structure
4. Model produces findings after exploration
5. Extract findings from `session.state.messages` (last assistant message)
6. Parse YAML from the response using existing `sanitize_output` + `parse_sortie_output`

### Concurrency

Three `createAgentSession()` calls in parallel via `Promise.all()`. Each session is independent (in-memory session manager, own model instance, own tool set). No shared mutable state.

### Output Capture

```typescript
await session.prompt(diffMessage);
const messages = session.state.messages;
const lastAssistant = messages.filter(m => m.role === "assistant").pop();
const rawYaml = lastAssistant?.content || "";
const result = parseSortieOutput(sanitizeOutput(rawYaml));
```

### Token Tracking

Pi's `AgentSession` tracks token usage per model call. Available via:

```typescript
session.subscribe((event) => {
  if (event.type === "usage_update") {
    // event.inputTokens, event.outputTokens
  }
});
```

Or after completion: `session.state.usage` (if exposed -- need to verify).

## What Changes in Sortie

### New

| Component | Description |
|---|---|
| `scripts/pi_invoker.ts` | TypeScript module: spawn Pi sessions, collect findings |
| `package.json` | Add `@mariozechner/pi-coding-agent` and `@mariozechner/pi-ai` deps |

### Modified

| Component | Change |
|---|---|
| `scripts/invoker.py` | Add `invoke: pi-sdk` handler that shells out to a Node script |
| `sortie.yaml` | New roster entries with `invoke: pi-sdk`, `provider`, `model`, `tools` fields |

### Unchanged

Everything downstream of the invoker: `sanitize_output`, `parse_sortie_output`, `debrief`, `triage`, `ledger`, `attestation`, `identity`, `hook`. The Pi invoker produces the same `SortieResult` dataclass. The pipeline doesn't know or care how findings were produced.

## Language Bridge

Sortie's core is Python. Pi SDK is TypeScript/Node. Two integration approaches:

### A) Node subprocess (simpler)

`pi_invoker.ts` is a standalone Node script. Python's `invoker.py` shells out to it:

```python
# When invoke == "pi-sdk":
result = subprocess.run(
    ["node", "scripts/pi_invoker.js", "--provider", entry["provider"],
     "--model", entry["model"], "--cwd", cwd, "--diff-file", diff_path],
    capture_output=True, text=True, timeout=timeout,
)
```

The Node script outputs YAML to stdout (same contract as CLI invocation). Python parses it with existing `sanitize_output` + `parse_sortie_output`.

### B) Pi CLI with tools (even simpler)

Use Pi's own CLI in print mode with tool restrictions:

```bash
pi --provider anthropic --model claude-sonnet-4-20250514 --tools read,grep,find,ls -p "$(cat prompt.md)"
```

This is a one-line change in `sortie.yaml` -- no new TypeScript needed:

```yaml
roster:
  - name: claude
    invoke: cli
    command: "pi --provider anthropic --model claude-sonnet-4-20250514 --tools read,grep,find,ls -p"
    prompt: prompts/sortie-code.md
    timeout: 180
```

The Pi CLI handles model selection, tool restriction, and output formatting. Sortie just pipes the prompt and reads YAML from stdout.

## Recommendation

**Start with approach B (Pi CLI).** It requires zero new code -- just new `sortie.yaml` entries. It immediately gives reviewers tool access. If we need more control (custom hooks, token tracking, event streaming), upgrade to approach A.

The key config change:

```yaml
# Before (flat text review)
- name: claude
  invoke: cli
  command: "claude -p"
  prompt: prompts/sortie-code.md

# After (Pi-powered review with tool access)
- name: claude
  invoke: cli
  command: "pi --provider anthropic --model claude-sonnet-4-20250514 --tools read,grep,find,ls -p"
  prompt: prompts/sortie-code.md
```

Same pipeline. Same debrief. Same triage. Same ledger. The reviewer is just smarter now.

## What Reviewers Can Do With Tools

| Tool | Review Capability | Example |
|---|---|---|
| `read` | Read full files, not just diffs | Read the interface a changed function implements |
| `grep` | Search for usages | Find all callers of a function that changed signature |
| `find` | Discover related files | Locate test files for the changed module |
| `ls` | Understand structure | Check if a new file follows existing naming conventions |

## What Reviewers Cannot Do (by design)

| Blocked | Why |
|---|---|
| `write` | Reviewers observe, they don't modify |
| `edit` | Same -- no code changes during review |
| `bash` | No arbitrary command execution. Prevents reviewers from running tests (that's the worker's job) or modifying state. If we want type-checking, add a dedicated `tsc` tool later. |

## Not in Scope

- Custom Pi extensions for sortie (v3.1)
- Pi SDK direct integration replacing subprocess (v3.1)
- Overstory integration for multi-harness orchestration (v3.2)
- Token tracking via Pi's usage API (v3.1)
- Bash tool for type-checking (needs careful sandboxing)
