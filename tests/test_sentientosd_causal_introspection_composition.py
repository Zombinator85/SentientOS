from sentientosd import _causal_introspection_world_state_records


def test_optional_introspection_recovery_failure_is_visible_and_bounded():
    class BrokenIntrospection:
        def reconstruct(self):
            raise RuntimeError("private path detail")

    records = _causal_introspection_world_state_records(
        BrokenIntrospection(), tick_id="2026-10-11T12:00:00+00:00")

    assert len(records) == 1
    record = records[0]
    assert record["source_kind"] == "owner_introspection"
    assert record["subject_kind"] == "causal_introspection_recovery"
    assert record["disposition"] == "incomplete"
    assert record["observed_at"] is None
    assert record["retrieved_at"] == "2026-10-11T12:00:00+00:00"
    assert record["staleness"] == "unknown"
    assert record["payload"]["error_class"] == "RuntimeError"
    assert "private path detail" not in repr(record)


def test_optional_introspection_prior_generation_is_composed_without_mutation():
    projected = [{"source_kind": "owner_introspection", "source_id": "prior-projection"}]

    class ExistingIntrospection:
        def __init__(self):
            self.requested_before_generation = None

        def reconstruct(self):
            return (object(), object())

        def world_state_records(self, *, before_generation):
            self.requested_before_generation = before_generation
            return projected

    runtime = ExistingIntrospection()
    assert _causal_introspection_world_state_records(
        runtime, tick_id="2026-10-11T12:00:00+00:00") == projected
    assert runtime.requested_before_generation == 3
