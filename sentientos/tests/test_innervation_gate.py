import pytest

from sentientos.innervation import (
    ColdPathViolation,
    ConstraintContextMissingError,
    InnervatedAction,
    InnervationContext,
    InnervationViolation,
    MissingInnervationError,
    ProvenanceMissingError,
    build_innervation,
    innervated_action,
)

class _DemoActor(InnervatedAction):
    @innervated_action()
    def perform(self) -> str:
        return "ok"


def test_missing_innervation_rejected():
    class NoInnervation:
        @innervated_action()
        def run(self):
            return "noop"

    actor = NoInnervation()
    with pytest.raises(MissingInnervationError):
        actor.run()


def test_constraint_registration_gate_blocks_placeholders():
    with pytest.raises(ConstraintContextMissingError):
        build_innervation(
            "demo",
            "act",
            justification="temporary placeholder",
            telemetry_channel="audit",
        )


def test_pressure_guard_requires_provenance():
    ctx = build_innervation(
        "demo",
        "pressure",
        justification="pressure requires provenance",
        telemetry_channel="audit",
    )
    ctx.sensor_provenance = None  # simulate missing provenance after construction
    with pytest.raises(ProvenanceMissingError):
        ctx.guard("performed", reason="missing-provenance")


def test_cold_path_detection_requires_annotation():
    ctx = InnervationContext(
        module="demo",
        action="cold",
        constraint_justification="cold-path check",
        telemetry_channel=None,
        require_telemetry=False,
    )
    with pytest.raises(ColdPathViolation):
        ctx.validate(allow_cold_path=False)
    ctx.cold_path_annotation = "manual audit will be attached"
    # now permitted when explicitly annotated
    ctx.validate(allow_cold_path=True)


def test_guard_enforces_causal_explanation_and_hooks():
    ctx = build_innervation(
        "demo",
        "perform",
        justification="demo actors must be innervated",
        telemetry_channel="audit",
    )
    actor = _DemoActor(ctx)
    assert actor.perform() == "ok"
    explanation = actor.innervation.require_explanation()
    assert explanation["constraint_id"] == ctx.constraint_id
    assert explanation["schema_version"]


def test_pressure_hooks_bypass_blocked():
    ctx = build_innervation(
        "demo",
        "hooks",
        justification="pressure hook must be present",
        telemetry_channel="audit",
    )
    ctx.pressure_hooks = ("explain_pressure",)  # drop record_signal to simulate bypass
    actor = _DemoActor(ctx)
    with pytest.raises(InnervationViolation):
        actor.perform()
