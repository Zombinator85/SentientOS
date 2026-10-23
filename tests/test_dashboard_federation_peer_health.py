import io
from datetime import datetime
from types import SimpleNamespace

import pytest

from sentientos.dashboard.console import ConsoleDashboard, DashboardStatus, LogBuffer
from sentientos.dashboard.status_source import make_status_source
from sentientos.runtime.shell import RuntimeShell

pytestmark = pytest.mark.no_legacy_skip


def test_runtime_exposes_peer_health_projection_map_without_local_source():
    shell = object.__new__(RuntimeShell)
    shell._federation_poller = None

    assert shell.get_peer_health_projections() == {}


def test_status_source_projects_bounded_peer_claim_fields_only():
    recovered = SimpleNamespace(
        peer="peer-one",
        outcome="recovered",
        observation=SimpleNamespace(
            peer_reported_status="unavailable",
            sequence=2,
            freshness_state="within_bound",
            endpoint="https://peer.invalid/private",
            signing_key_id="private-key-id",
        ),
        error_code=None,
    )
    omitted = SimpleNamespace(peer="peer-two", outcome="omitted")
    malformed = SimpleNamespace(
        peer="peer-three",
        outcome="recovered",
        observation=SimpleNamespace(peer_reported_status={}, sequence=1, freshness_state="within_bound"),
    )

    class Shell:
        federation_config = SimpleNamespace(enabled=True, node_id=None, peers=[])

        def get_peer_health_projections(self):
            return {"peer-one": recovered, "peer-two": omitted, "peer-three": malformed}

    status = make_status_source(
        shell=Shell(),
        config={"runtime": {"node_name": "local"}, "federation": {"enabled": True}},
    )()

    assert status.federation_peer_health == [
        {
            "peer": "peer-one",
            "outcome": "recovered",
            "status": "unavailable",
            "sequence": 2,
            "freshness": "within_bound",
        },
        {"peer": "peer-two", "outcome": "omitted"},
    ]


def test_status_source_limits_peer_health_projection_count_to_64():
    class Shell:
        federation_config = SimpleNamespace(enabled=True, node_id=None, peers=[])

        def get_peer_health_projections(self):
            return {
                f"peer-{index:03d}": SimpleNamespace(outcome="omitted")
                for index in range(70)
            }

    status = make_status_source(
        shell=Shell(),
        config={"runtime": {"node_name": "local"}, "federation": {"enabled": True}},
    )()

    assert len(status.federation_peer_health) == 64
    assert status.federation_peer_health[0] == {
        "peer": "peer-000",
        "outcome": "omitted",
    }


def test_console_labels_peer_health_as_claims_separate_from_local_health():
    status = DashboardStatus(
        node_name="local",
        model_name="test-model",
        model_status="online",
        persona_enabled=False,
        persona_mood=None,
        last_persona_msg=None,
        experiments_run=0,
        experiments_success=0,
        experiments_failed=0,
        last_experiment_desc=None,
        last_experiment_result=None,
        consensus_mode="single-node",
        last_update_ts=datetime(2026, 10, 23),
        federation_peer_health=[
            {
                "peer": "peer-one",
                "outcome": "recovered",
                "status": "unavailable",
                "sequence": 2,
                "freshness": "within_bound",
            },
            {"peer": "peer-two", "outcome": "omitted"},
        ],
    )
    output = io.StringIO()
    dashboard = ConsoleDashboard(
        lambda: status,
        log_stream_source=lambda: [],
        refresh_interval=1,
        log_buffer=LogBuffer(),
        output_stream=output,
    )

    dashboard.run_once()
    rendered = output.getvalue()

    assert "PEER-REPORTED HEALTH CLAIMS (NOT LOCAL HEALTH)" in rendered
    assert "peer-one: peer-reported unavailable (sequence 2; within_bound)" in rendered
    assert "peer-two: omitted" in rendered
    assert "peer Health projection available" not in rendered
