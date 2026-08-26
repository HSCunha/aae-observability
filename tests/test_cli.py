"""Tests for the CLI."""

from pathlib import Path

from aae_observability.cli import main


def test_version_command(capsys: object) -> None:
    assert main(["version"]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert captured.out.strip() == "0.6.3"


def test_help_when_no_command(capsys: object) -> None:
    assert main([]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "usage: aae-observability" in captured.out


def test_config_validate_success(tmp_path: Path, capsys: object) -> None:
    path = tmp_path / "aae.observability.toml"
    path.write_text('[telemetry]\nservice_name = "cli-agent"\n')
    assert main(["config", "validate", str(path)]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "Configuration is valid" in captured.out


def test_config_validate_shows_redacted_effective_config(tmp_path: Path, capsys: object) -> None:
    path = tmp_path / "aae.observability.toml"
    path.write_text(
        '[telemetry]\nauth_mode = "connection_string"\n'
        'connection_string = "Endpoint=sb://example/;SharedAccessKey=secret"\n'
    )
    assert main(["config", "validate", str(path), "--show-effective"]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "**********" in captured.out
    assert "SharedAccessKey=secret" not in captured.out


def test_config_validate_failure(tmp_path: Path, capsys: object) -> None:
    path = tmp_path / "invalid.toml"
    path.write_text("[telemetry]\nsampling_ratio = 2.0\n")
    assert main(["config", "validate", str(path)]) == 2
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "Configuration validation failed" in captured.err


def test_policy_validate_success(tmp_path: Path, capsys: object) -> None:
    path = tmp_path / "policy.yaml"
    path.write_text(
        "apiVersion: aae-observability/v1\nkind: Policy\ndefault_action: deny\nrules: []\n"
    )
    assert main(["policy", "validate", str(path)]) == 0
    assert "Policy is valid" in capsys.readouterr().out  # type: ignore[attr-defined]


def test_policy_validate_failure(tmp_path: Path, capsys: object) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("apiVersion: bad\nkind: Policy\n")
    assert main(["policy", "validate", str(path)]) == 2
    assert "Policy validation failed" in capsys.readouterr().err  # type: ignore[attr-defined]
