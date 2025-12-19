import json

import affective_context as ac
from sentientos.autonomy.audit import AutonomyActionLogger
from sentientos.sensor_provenance import SensorProvenance


def _read_last(path):
    return json.loads(path.read_text(encoding="utf-8").splitlines()[-1])


def _provenance(sensor_id: str = "test-sensor") -> SensorProvenance:
    return SensorProvenance(
        sensor_id=sensor_id,
        origin_class="constraint",
        sensitivity_parameters={"gain": 1.0},
        expected_noise_profile={"variance": 0.1},
        known_failure_modes=("drift",),
        calibration_state="nominal",
    )


def test_log_innervates_actions(tmp_path):
    path = tmp_path / "audit.jsonl"
    logger = AutonomyActionLogger(path=path)
    overlay = ac.capture_affective_context("unit-test", overlay={"focus": 0.4})
    logger.log(
        "browser",
        "open",
        "performed",
        affective_overlay=overlay,
        sensor_provenance=_provenance(),
        environment={"target": "https://example.com"},
        assumptions=("allowlist_enforced",),
    )
    record = _read_last(path)
    assert record["constraint_id"] == "autonomy::browser::open"
    assert record["affective_context"]["reason"] == "unit-test"
    assert 0.0 <= record["uncertainty"] <= 1.0
    assert record["pressure"]["status"] in {"resolved", "transient", "chronic"}
    assert record["sensor_provenance"]["calibration_state"] == "nominal"
    assert record["authority_guard"]["status"] == "isolated"


def test_blocked_actions_accumulate_pressure_and_explain(tmp_path):
    path = tmp_path / "audit.jsonl"
    logger = AutonomyActionLogger(path=path, history_size=25)
    overlay = ac.capture_affective_context("blocked-test", overlay={"blocked": 1.0})
    prov = _provenance("blocked-sensor")
    for _ in range(3):
        logger.log(
            "browser",
            "post",
            "blocked",
            affective_overlay=overlay,
            sensor_provenance=prov,
            environment={"target": "timeline"},
            pressure_reason="quorum_missing",
            assumptions=("quorum_required",),
        )

    record = _read_last(path)
    pressure = record["pressure"]
    assert pressure["blocked_count"] >= 3
    assert pressure["status"] in {"chronic", "transient"}
    explanation = pressure["causal_explanation"]
    assert explanation["schema_version"] == "1.0"
    assert explanation["narrative"]["assumptions"]
    assert "meta_pressure_flags" in explanation
