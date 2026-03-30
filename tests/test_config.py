"""Tests for the config module."""

import pytest
import yaml
from scripts.config import load_config, resolve_mode


MINIMAL_CONFIG = {
    "roster": [
        {"name": "claude", "invoke": "hook-agent", "prompt": "prompts/sortie-code.md"},
        {"name": "gemini", "invoke": "cli", "prompt": "prompts/sortie-code.md"},
    ],
    "debrief": {
        "model": "claude",
        "invoke": "hook-agent",
        "prompt": "prompts/debrief.md",
    },
    "triage": {
        "block_on": ["critical", "major"],
        "max_remediation_cycles": 2,
        "convergence_threshold": 2,
    },
    "modes": {
        "code": {
            "prompt": "prompts/sortie-code.md",
            "trigger": "merge",
            "roster": ["claude", "gemini"],
            "triage": {"block_on": ["critical", "major"]},
        },
        "tests": {
            "prompt": "prompts/sortie-tests.md",
            "trigger": "milestone",
            "roster": ["claude"],
            "triage": {"block_on": ["critical"]},
        },
        "minimal": {
            "prompt": "prompts/sortie-minimal.md",
            # no roster, no triage, no trigger -- to test inheritance/defaults
        },
    },
    "ledger": {"path": ".sortie/ledger.yaml"},
    "deposition": {"dir": ".sortie/{tree_sha}-{cycle}/"},
}


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "sortie.yaml"
    path.write_text(yaml.dump(MINIMAL_CONFIG))
    return str(path)


class TestLoadConfig:
    def test_loads_valid_config(self, config_file):
        cfg = load_config(config_file)
        assert "roster" in cfg
        assert "debrief" in cfg
        assert "triage" in cfg
        assert "modes" in cfg
        assert "ledger" in cfg
        assert "deposition" in cfg

    def test_missing_file_raises(self, tmp_path):
        missing = str(tmp_path / "nonexistent.yaml")
        with pytest.raises(FileNotFoundError):
            load_config(missing)

    def test_missing_required_key_raises(self, tmp_path):
        incomplete = {k: v for k, v in MINIMAL_CONFIG.items() if k != "triage"}
        path = tmp_path / "sortie.yaml"
        path.write_text(yaml.dump(incomplete))
        with pytest.raises(ValueError, match="triage"):
            load_config(str(path))

    def test_all_required_keys_present(self, config_file):
        cfg = load_config(config_file)
        for key in ("roster", "debrief", "triage", "modes", "ledger", "deposition"):
            assert key in cfg


class TestResolveMode:
    def test_resolved_has_prompt(self, config_file):
        cfg = load_config(config_file)
        result = resolve_mode(cfg, "code")
        assert result["prompt"] == "prompts/sortie-code.md"

    def test_resolved_has_trigger(self, config_file):
        cfg = load_config(config_file)
        result = resolve_mode(cfg, "code")
        assert result["trigger"] == "merge"

    def test_trigger_defaults_to_milestone(self, config_file):
        cfg = load_config(config_file)
        result = resolve_mode(cfg, "minimal")
        assert result["trigger"] == "milestone"

    def test_inherits_triage_defaults(self, config_file):
        cfg = load_config(config_file)
        # "minimal" mode has no triage -- should inherit top-level
        result = resolve_mode(cfg, "minimal")
        assert result["triage"] == MINIMAL_CONFIG["triage"]

    def test_mode_triage_overrides_top_level(self, config_file):
        cfg = load_config(config_file)
        # "tests" mode only blocks on "critical"
        result = resolve_mode(cfg, "tests")
        assert result["triage"]["block_on"] == ["critical"]

    def test_roster_names_from_mode(self, config_file):
        cfg = load_config(config_file)
        result = resolve_mode(cfg, "code")
        assert result["roster_names"] == ["claude", "gemini"]

    def test_mode_without_roster_returns_none(self, config_file):
        cfg = load_config(config_file)
        result = resolve_mode(cfg, "minimal")
        assert result["roster_names"] is None

    def test_unknown_mode_raises(self, config_file):
        cfg = load_config(config_file)
        with pytest.raises(ValueError, match="unknown mode"):
            resolve_mode(cfg, "nonexistent")
