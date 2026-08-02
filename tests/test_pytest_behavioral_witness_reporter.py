from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from scripts.pytest_collection_reporter import PytestCollectionReporter

NODE = "tests/example.py::test_example"
pytestmark = pytest.mark.no_legacy_skip

def _active(reporter): reporter._active_call_node = NODE

def test_call_phase_fixture_records_canonical_witness(tmp_path, behavioral_witness):
    behavioral_witness.record("reporter_contract", "sentientos.reporter_proof:v1", {"observed": True})
    reporter = PytestCollectionReporter(tmp_path/"r.json", "sha", "run"); _active(reporter)
    reporter.record_witness(NODE, "contract", "sentientos.proof:v1", {"observed": True})
    assert next(iter(reporter._witnesses.values()))["facts_digest"].startswith("sha256:")
def test_recorded_facts_are_frozen(tmp_path):
    reporter = PytestCollectionReporter(tmp_path/"r.json", "sha", "run"); _active(reporter); facts={"items":[1]}
    reporter.record_witness(NODE,"contract","kind",facts); facts["items"].append(2)
    assert next(iter(reporter._witnesses.values()))["facts"] == {"items":[1]}
def test_conflicting_witness_fails_test(tmp_path):
    reporter=PytestCollectionReporter(tmp_path/"r.json"); _active(reporter); reporter.record_witness(NODE,"c","k",{"x":1})
    with pytest.raises(ValueError): reporter.record_witness(NODE,"c","k",{"x":2})
def test_witness_bounds_fail_closed(tmp_path):
    reporter=PytestCollectionReporter(tmp_path/"r.json"); _active(reporter)
    with pytest.raises(ValueError): reporter.record_witness(NODE,"c","k",{"x":"x"*4097})
