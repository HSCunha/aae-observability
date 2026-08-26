from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import aae_observability


def write_config(path: Path, name: str, *, enabled: bool = True) -> None:
    path.write_text(
        json.dumps(
            {
                "telemetry": {"service_name": name},
                "governance": {
                    "hot_reload_enabled": enabled,
                    "hot_reload_interval_ms": 100,
                },
            }
        )
    )


def test_manual_reload_success_and_immutable_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "aae.observability.json"
    write_config(path, "one")
    active = {"value": aae_observability.load_config(path)}
    events: list[aae_observability.ReloadEvent] = []
    reloader = aae_observability.build_layered_reloader(
        path, lambda candidate: active.update(value=candidate), event_sink=events.append
    )
    time.sleep(0.002)
    write_config(path, "two")
    assert reloader.check_now()
    assert active["value"].telemetry.service_name == "two"
    snapshot = reloader.snapshot()
    assert snapshot.generation == 1
    assert snapshot.successful_reloads == 1
    assert events[0].outcome == "success"
    assert events[0].error_type is None


def test_invalid_update_rolls_back_and_reports_safe_error(tmp_path: Path) -> None:
    path = tmp_path / "aae.observability.json"
    write_config(path, "stable")
    active = {"value": aae_observability.load_config(path)}
    events: list[aae_observability.ReloadEvent] = []
    reloader = aae_observability.build_layered_reloader(
        path, lambda candidate: active.update(value=candidate), event_sink=events.append
    )
    time.sleep(0.002)
    path.write_text('{"telemetry":{"sampling_ratio":7,"connection_string":"secret"}}')
    assert not reloader.check_now()
    assert active["value"].telemetry.service_name == "stable"
    snapshot = reloader.snapshot()
    assert snapshot.generation == 0
    assert snapshot.failed_reloads == 1
    assert events[0].outcome == "failure"
    assert events[0].error_type is not None
    assert "secret" not in repr(events[0])


def test_callback_failure_does_not_publish_generation(tmp_path: Path) -> None:
    path = tmp_path / "aae.observability.json"
    write_config(path, "one")
    reloader = aae_observability.build_layered_reloader(
        path, lambda candidate: (_ for _ in ()).throw(RuntimeError("private"))
    )
    time.sleep(0.002)
    write_config(path, "two")
    assert not reloader.check_now()
    assert reloader.snapshot().generation == 0
    assert reloader.snapshot().last_event.error_type == "RuntimeError"  # type: ignore[union-attr]


def test_background_watcher_and_idempotent_lifecycle(tmp_path: Path) -> None:
    path = tmp_path / "aae.observability.json"
    write_config(path, "one")
    changed = threading.Event()
    active: list[str] = []

    def apply(candidate: aae_observability.AaeObservabilityConfig) -> None:
        active.append(candidate.telemetry.service_name)
        changed.set()

    reloader = aae_observability.build_layered_reloader(path, apply, interval_ms=100)
    reloader.start()
    reloader.start()
    time.sleep(0.02)
    write_config(path, "two")
    assert changed.wait(2)
    reloader.stop()
    reloader.stop()
    assert active[-1] == "two"


def test_configure_integrates_reloader_and_shutdown(tmp_path: Path) -> None:
    path = tmp_path / "aae.observability.json"
    write_config(path, "one")
    aae_observability.configure(config_file=str(path), environ={})
    reloader = aae_observability.get_config_reloader()
    assert reloader is not None
    time.sleep(0.002)
    write_config(path, "two")
    assert reloader.check_now()
    from aae_observability.api import _STATE

    assert _STATE.telemetry is not None
    assert _STATE.telemetry.service_name == "two"
    aae_observability.shutdown()
    assert aae_observability.get_config_reloader() is None


def test_policy_source_is_watched_and_atomically_reloaded(tmp_path: Path) -> None:
    config_path = tmp_path / "aae.observability.json"
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        "apiVersion: aae-observability/v1\nkind: Policy\ndefault_action: allow\nrules: []\n"
    )
    config_path.write_text(
        json.dumps(
            {
                "governance": {
                    "policy_source": str(policy_path),
                    "hot_reload_enabled": True,
                    "hot_reload_interval_ms": 100,
                }
            }
        )
    )
    aae_observability.configure(config_file=str(config_path), environ={})
    reloader = aae_observability.get_config_reloader()
    assert reloader is not None
    time.sleep(0.002)
    policy_path.write_text(
        "apiVersion: aae-observability/v1\nkind: Policy\ndefault_action: deny\nrules: []\n"
    )
    assert reloader.check_now()

    @aae_observability.instrument
    def blocked() -> str:
        return "should not run"

    try:
        blocked()
        raise AssertionError("reloaded deny policy was not applied")
    except aae_observability.GovernanceDeniedError:
        pass
    finally:
        aae_observability.shutdown()
