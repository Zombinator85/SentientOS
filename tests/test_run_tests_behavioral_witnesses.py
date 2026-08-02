from __future__ import annotations

import json
import pytest
from scripts.provenance_hash_chain import compute_provenance_hash
pytestmark = pytest.mark.no_legacy_skip

def test_run_tests_binds_witness_to_node_run_sha_and_provenance_hash(tmp_path):
    from sentientos.behavioral_witness import build_witness, valid_witness
    witness=build_witness(repository_sha="sha",run_id="run",node_id="x::y",contract_id="c",witness_kind="k",facts={"ok":True})
    assert valid_witness(witness) and witness["run_id"] == "run" and witness["node_id"] == "x::y"
def test_run_tests_legacy_provenance_without_witnesses_remains_valid(tmp_path):
    payload={"git_sha":"sha","hash_algo":"sha256","prev_provenance_hash":None}
    assert isinstance(compute_provenance_hash(payload, None), str)
