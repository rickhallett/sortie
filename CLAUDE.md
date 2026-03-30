# CLAUDE.md

## Project

Sortie -- async adversarial review for Claude Code Teams swarm workflows.
Runs a configurable roster of LLMs against worker diffs at merge boundary,
synthesizes findings through debrief, triages by severity, gates merges.

Full spec: `docs/superpowers/specs/2026-03-30-sortie-design.md`
Implementation plan: `docs/superpowers/plans/2026-03-30-sortie-implementation.md`

## Commands

```bash
# Run all tests
uv run pytest tests/ -v

# Run a single test file
uv run pytest tests/test_ledger.py -v

# Full sortie pipeline
just sortie-all <branch> [mode]

# Show run status
just sortie-status

# Annotate a finding
just sortie-dispose <run_id> <finding_id> <disposition>
```

## Architecture

```
scripts/
  sortie.py          # CLI entry point (pipeline, status, dispose)
  config.py          # Load sortie.yaml, resolve mode overrides
  identity.py        # Tree hash, run ID, cycle counting
  attestation.py     # Write/read/verify attestation YAML
  invoker.py         # Parallel model fan-out (cli, hook-agent)
  debrief.py         # Synthesis prompt building, verdict writing
  triage.py          # Severity-gated verdict evaluation
  ledger.py          # Append-only YAML run data store
  sortie_hook.py     # Claude Code pre-merge hook

prompts/             # Markdown review prompts (code, tests, docs, debrief)
.sortie/             # Runtime artifacts (gitignored except ledger.yaml)
```

## Key concepts

- **Tree hash identity**: `git write-tree` keys artifacts to staged content
- **Run ID**: `{tree_sha_8}-{cycle}` where cycle counts remediation attempts
- **Convergent finding**: 2+ models found the same issue (high confidence)
- **Divergent finding**: 1 model only (logged, never blocks)
- **Triage**: `block_on` in sortie.yaml controls which severities gate merges

## Dependencies

Managed via `uv`. Run `uv sync` to install.

- Python 3.11+ (managed by uv)
- PyYAML
- pytest (dev dependency)
