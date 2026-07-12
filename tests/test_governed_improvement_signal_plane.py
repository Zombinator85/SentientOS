from sentientos.governed_improvement_signal_plane import build_batch, evaluate_signal_plane, render_markdown


def test_deterministic_batch_routing_and_markdown(tmp_path):
    records = [
        {"source_kind":"coverage","finding_kind":"uncovered_flow","severity":"medium","description":"gap","capability_id":"cap","telemetry_stream":"cap.stream","subject_path":"sentientos/x.py","observed_at":"t"},
        {"source_kind":"run_tests","finding_kind":"test_failure","severity":"high","description":"fail","spec_id":"spec.alpha","subject_path":"tests/x.py","observed_at":"t"},
        {"source_kind":"gap_seeker","finding_kind":"todo","severity":"low","description":"todo","subject_path":"sentientos/y.py","observed_at":"t"},
    ]
    a = evaluate_signal_plane(records, repo_root=tmp_path)
    b = evaluate_signal_plane(list(reversed(records)), repo_root=tmp_path)
    assert a.batch.batch_id == b.batch.batch_id
    assert [r.disposition for r in a.receipts] == [r.disposition for r in b.receipts]
    dispositions = {r.disposition for r in a.receipts}
    assert {"genesis_proposal_candidate", "spec_amendment_candidate", "gap_seeker_diagnostic"} <= dispositions
    assert a.summary["adoption_performed"] is False
    assert a.summary["repository_mutation_performed"] is False
    assert "Repository mutation performed: `false`" in render_markdown(a)


def test_duplicate_contradiction_and_authority_claims_fail_closed(tmp_path):
    records = [
        {"source_kind":"telemetry","finding_kind":"missing_capability","description":"one","capability_id":"cap","observed_at":"t"},
        {"source_kind":"telemetry","finding_kind":"missing_capability","description":"two","capability_id":"cap","observed_at":"t"},
        {"source_kind":"unknown","finding_kind":"missing_capability","description":"bad","capability_id":"bad","adoption_performed":True},
    ]
    ev = evaluate_signal_plane(records, repo_root=tmp_path)
    assert ev.batch.contradiction_ids
    assert ev.summary["blocked_invalid_count"] >= 1
    assert all(not r.adoption_occurred and not r.repository_mutation_occurred for r in ev.receipts)


def test_path_traversal_rejected(tmp_path):
    try:
        build_batch([{"source_kind":"run_tests","finding_kind":"test_failure","description":"x","subject_path":"../x"}], repo_root=tmp_path)
    except ValueError as exc:
        assert "path_traversal" in str(exc)
    else:
        raise AssertionError("path traversal accepted")
