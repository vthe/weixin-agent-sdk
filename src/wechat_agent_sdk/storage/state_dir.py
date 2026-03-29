"""Storage utilities for state directory resolution."""

import os
import pathlib


def resolve_state_dir() -> str:
    """Resolve the OpenClaw state directory."""
    return (
        os.environ.get("OPENCLAW_STATE_DIR", "").strip() or
        os.environ.get("CLAWDBOT_STATE_DIR", "").strip() or
        os.path.expanduser("~/.openclaw")
    )
