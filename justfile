# justfile -- Sortie orchestration targets

# Full pipeline: parallel sorties + debrief + triage
sortie-all branch mode='code':
    uv run python scripts/sortie.py pipeline {{branch}} --mode {{mode}}

# Show current sortie state
sortie-status:
    uv run python scripts/sortie.py status

# Annotate finding disposition
sortie-dispose run_id finding_id disposition:
    uv run python scripts/sortie.py dispose {{run_id}} {{finding_id}} {{disposition}}

# Run all tests
test:
    uv run pytest tests/ -v

# Run a single test file
test-one file:
    uv run pytest {{file}} -v
