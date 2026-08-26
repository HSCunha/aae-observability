"""Configuration file loading and validation."""

import json
from pathlib import Path
from typing import Any

import tomllib
from pydantic import ValidationError

from aae_observability.config.models import AaeObservabilityConfig


class ConfigFileError(ValueError):
    """Raised when a configuration file cannot be read or parsed."""


def load_config(path: str | Path) -> AaeObservabilityConfig:
    """Load and validate an aae_observability JSON or TOML configuration document."""
    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigFileError(f"configuration file not found: {config_path}")

    try:
        raw = config_path.read_bytes()
        suffix = config_path.suffix.lower()
        if suffix == ".toml":
            payload: Any = tomllib.loads(raw.decode("utf-8"))
        elif suffix == ".json":
            payload = json.loads(raw.decode("utf-8"))
        else:
            raise ConfigFileError("configuration file must use .toml or .json")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigFileError(f"unable to parse configuration file: {exc}") from exc

    if not isinstance(payload, dict):
        raise ConfigFileError("configuration document must contain a top-level object")

    try:
        return AaeObservabilityConfig.model_validate(payload)
    except ValidationError:
        raise
