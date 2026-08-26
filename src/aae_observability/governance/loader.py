"""YAML/JSON policy loading and validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from aae_observability.governance.models import PolicyDocument


class PolicyFileError(ValueError):
    pass


def load_policy(path: str | Path) -> PolicyDocument:
    policy_path = Path(path)
    if not policy_path.is_file():
        raise PolicyFileError(f"policy file not found: {policy_path}")
    try:
        text = policy_path.read_text(encoding="utf-8")
        if policy_path.suffix.lower() in {".yaml", ".yml"}:
            payload: Any = yaml.safe_load(text)
        elif policy_path.suffix.lower() == ".json":
            payload = json.loads(text)
        else:
            raise PolicyFileError("policy file must use .yaml, .yml, or .json")
    except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise PolicyFileError(f"unable to parse policy file: {exc}") from exc
    if not isinstance(payload, dict):
        raise PolicyFileError("policy document must contain a top-level object")
    try:
        return PolicyDocument.model_validate(payload)
    except ValidationError:
        raise
