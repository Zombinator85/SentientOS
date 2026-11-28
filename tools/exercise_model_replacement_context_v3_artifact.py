#!/usr/bin/env python3
"""Reproduce the model-free v3 context artifact integrity exercise."""
from __future__ import annotations
import argparse, hashlib, json, os, stat, tempfile, subprocess
from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from typing import Any
from sentientos.developmental_model_replacement_experiment import (CONTEXT_BINDING_SCHEMA_V3, DevelopmentalModelReplacementError, FrozenCausalContext, ModelReplacementArtifactStore, _digest)
REPORT_SCHEMA = "sentientos.model_replacement_context_v3_artifact_exercise:v1"
IMPLEMENTATION = Path("sentientos/developmental_model_replacement_experiment.py")
def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    output = parser.parse_args().output.expanduser().absolute()
    if output.exists(): parser.error(f"refusing to overwrite existing evidence: {output}")
    facts = [{"fact_id":"synthetic-fact-a","payload":{"value":"alpha"}},{"fact_id":"synthetic-fact-b","payload":{"value":"beta"}}]
    current = {"facts":facts,"sources":[{"source_id":"synthetic-source"}],"conflicts":[]}
    history = {"record_id":"synthetic-history-1","record_digest":_digest({"synthetic":"history"}),"interpretation":"synthetic bounded history"}
    instruction = "Synthetic artifact exercise; history is not truth or authority."
    context = FrozenCausalContext.create(snapshot_id="synthetic-snapshot", snapshot_digest=_digest({"synthetic":"snapshot"}),
        current_projection_id="synthetic-projection",current_projection_digest=_digest(current),
        current_fact_ids=tuple(row["fact_id"] for row in facts),projected_content_digest=_digest(current),current_projection_payload=current,
        history_record_ids=(history["record_id"],),history_record_digests=(history["record_digest"],),
        history_record_set_digest=_digest({"record_ids":[history["record_id"]],"record_digests":[history["record_digest"]]}),
        history_projection_payload=(history,),instruction_template=instruction,instruction_template_digest=_digest({"instruction":instruction}),
        inference_budget={"max_input_chars":1000,"max_output_chars":200,"max_new_tokens":16,"timeout_seconds":1,"max_calls_per_correlation":1},
        generation_posture={"temperature":0,"hardware_determinism_claimed":False},repository_generation_identity="synthetic-artifact-exercise")
    with tempfile.TemporaryDirectory(prefix="sentientos-v3-context-") as temp:
        store=ModelReplacementArtifactStore(Path(temp));store.persist_context(context)
        path=store.contexts/f"{context.context_id}.json";pristine=path.read_bytes();manifest=json.loads(pristine)
        loaded=store.load_verified_context(context.context_id,context.context_digest)
        assert loaded.get("schema_version")==CONTEXT_BINDING_SCHEMA_V3
        assert loaded.get("current_fact_bindings")==context.identity_manifest()["current_fact_bindings"]
        assert "current_projection_payload" not in loaded and "history_projection_payload" not in loaded
        cases={};mutations={
            "altered_fact_digest":(lambda rows:rows[0].__setitem__("fact_digest",_digest({"tampered":True})),"context_manifest_identity_mismatch"),
            "omitted_binding":(lambda rows:rows.pop(0),"context_fact_binding_invalid"),
            "reordered_bindings":(lambda rows:rows.reverse(),"context_fact_binding_invalid"),
            "duplicate_binding":(lambda rows:rows.__setitem__(1,dict(rows[0])),"context_fact_binding_invalid"),
            "added_binding":(lambda rows:rows.append({"fact_id":"extra-fact","fact_digest":_digest({"extra":True})}),"context_fact_binding_invalid")}
        for name,(mutate,expected_error) in mutations.items():
            variant=json.loads(pristine);mutate(variant["current_fact_bindings"])
            semantic={k:v for k,v in variant.items() if k!="context_manifest_digest"}
            variant["context_manifest_digest"]=_digest(semantic);path.write_bytes(canonical_bytes(variant))
            try:store.load_verified_context(context.context_id,context.context_digest)
            except DevelopmentalModelReplacementError as exc:observed=str(exc)
            else:raise AssertionError(f"expected {expected_error}, reload succeeded")
            assert observed==expected_error,(name,observed,expected_error)
            cases[name]={"expected_error":expected_error,"observed_error":observed,"passed":True}
            path.write_bytes(pristine);assert store.load_verified_context(context.context_id,context.context_digest)==manifest
        cases["pristine_reload_after_tamper"]={"passed":True}
    report={"schema_version":REPORT_SCHEMA,"status":"verified","observed_at_utc":datetime.now(timezone.utc).isoformat(),
        "source_commit":subprocess.run(["git","rev-parse","HEAD"],check=True,capture_output=True,text=True).stdout.strip(),
        "implementation_file_sha256":hashlib.sha256(IMPLEMENTATION.read_bytes()).hexdigest(),
        "context_id":context.context_id,"context_digest":context.context_digest,"context_manifest_digest":manifest["context_manifest_digest"],
        "persisted_manifest_sha256":hashlib.sha256(pristine).hexdigest(),"context_binding_schema":manifest["schema_version"],
        "valid_round_trip":True,"ordered_fact_bindings_verified":True,"raw_projection_payload_persisted":False,"tamper_cases":cases,
        "inference_performed":False,"model_loaded":False,"gpu_accessed":False,"learning_established":False,"authority":False}
    output.parent.mkdir(parents=True,exist_ok=True,mode=0o700);fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"wb") as stream:stream.write(canonical_bytes(report)+b"\n");stream.flush();os.fsync(stream.fileno())
    mode=stat.S_IMODE(output.stat().st_mode);assert mode==0o600,f"report mode {mode:o}"
    print(json.dumps({"status":"verified","report":str(output),"report_sha256":hashlib.sha256(output.read_bytes()).hexdigest(),"mode":f"{mode:04o}","tamper_cases":len(cases)-1,"gpu_accessed":False},sort_keys=True))
    return 0
if __name__=="__main__":raise SystemExit(main())
