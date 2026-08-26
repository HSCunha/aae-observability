"""Command-line interface."""

import argparse
import json
import sys
from collections.abc import Sequence

from pydantic import ValidationError

from aae_observability._version import __version__
from aae_observability.config import ConfigFileError, load_config
from aae_observability.governance import LocalPolicyEngine, PolicyFileError, load_policy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aae-observability")
    subs = parser.add_subparsers(dest="command")
    subs.add_parser("version", help="Print the installed version")
    config = subs.add_parser("config", help="Configuration utilities")
    cc = config.add_subparsers(dest="config_command")
    validate = cc.add_parser("validate", help="Validate a config file")
    validate.add_argument("path")
    validate.add_argument("--show-effective", action="store_true")
    policy = subs.add_parser("policy", help="Policy utilities")
    pc = policy.add_subparsers(dest="policy_command")
    pv = pc.add_parser("validate", help="Validate and compile a policy file")
    pv.add_argument("path")
    pv.add_argument("--show-normalized", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "version":
        print(__version__)
        return 0
    if args.command == "config" and args.config_command == "validate":
        try:
            config = load_config(args.path)
        except (ConfigFileError, ValidationError) as exc:
            print(f"Configuration validation failed: {exc}", file=sys.stderr)
            return 2
        print(f"Configuration is valid: {args.path}")
        if args.show_effective:
            print(json.dumps(config.redacted_dict(), indent=2, sort_keys=True))
        return 0
    if args.command == "policy" and args.policy_command == "validate":
        try:
            policy = load_policy(args.path)
            engine = LocalPolicyEngine(policy)
        except (PolicyFileError, ValidationError, ValueError) as exc:
            print(f"Policy validation failed: {exc}", file=sys.stderr)
            return 2
        print(f"Policy is valid: {args.path} ({engine.compiled_rule_count} compiled rules)")
        if args.show_normalized:
            print(json.dumps(policy.model_dump(mode="json"), indent=2, sort_keys=True))
        return 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
