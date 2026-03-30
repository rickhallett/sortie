"""Config module -- loads and resolves sortie.yaml configuration."""

import yaml

REQUIRED_KEYS = ("roster", "debrief", "triage", "modes", "ledger", "deposition")


def load_config(path: str) -> dict:
    """Load sortie.yaml from path and validate required keys are present.

    Raises:
        FileNotFoundError: if the file does not exist.
        ValueError: if a required key is missing.
    """
    try:
        with open(path, "r") as f:
            cfg = yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Config file not found: {path}")

    for key in REQUIRED_KEYS:
        if key not in cfg:
            raise ValueError(f"Missing required config key: '{key}'")

    return cfg


def resolve_mode(cfg: dict, mode: str) -> dict:
    """Resolve a mode's config by merging with top-level defaults.

    Returns a dict with:
        prompt (str): the prompt file path
        trigger (str): when this mode runs (default "milestone")
        roster_names (list[str] | None): model names from mode config, or None to inherit
        triage (dict): merged triage config (mode overrides top-level)

    Raises:
        ValueError: for unknown mode.
    """
    modes = cfg.get("modes", {})
    if mode not in modes:
        raise ValueError(f"unknown mode: '{mode}'")

    mode_cfg = modes[mode]
    top_triage = cfg.get("triage", {})
    mode_triage = mode_cfg.get("triage")

    if mode_triage is not None:
        triage = {**top_triage, **mode_triage}
    else:
        triage = dict(top_triage)

    roster_names = mode_cfg.get("roster", None)

    return {
        "prompt": mode_cfg["prompt"],
        "trigger": mode_cfg.get("trigger", "milestone"),
        "roster_names": roster_names,
        "triage": triage,
    }
