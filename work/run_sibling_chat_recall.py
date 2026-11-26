"""Run the archived sibling-history recall comparison through governed ordinary chat."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import select
import signal
import shutil
import socket
import socketserver
import subprocess
import tempfile
import threading
import time
import urllib.request
from urllib.parse import urlsplit

from sentientos.canonical_memory import CanonicalMemoryStore
from sentientos.chat_service import DevelopmentLocalChatInference, PersistentConversationService
from sentientos.config import GenerationConfig, ModelCandidate, ModelConfig
from sentientos.conversation_session import (
    ConversationSessionStore, ordinary_chat_developmental_history_prompt_block_digest,
)
from sentientos.developmental_companion_bridge import ResidentDevelopmentalCompanionBridge
from sentientos.governed_local_model_invocation import GovernedLocalModelInvoker, validate_receipt
from sentientos.local_model import LocalModel
from sentientos.local_model_authority import build_local_model_authority_map, digest_payload, stream_sha256
from sentientos.rootless_experimental_local_model import _resource_governed_kernel, _rootless_governance_custody
from work.preflight_ordinary_chat_retention import (
    _CapturedRequest, _owner, _read_receipt, _service_request, _source_kinds_from_history,
)
from work.preflight_sibling_chat_histories import CYCLES, QUESTIONS, TARGET, archive, admitted_boundary, read


MODEL = "qwen2.5:1.5b-instruct-q4_K_M"
MANIFEST = "f2b0a490f661d58f20c4b98e5797ecf55e6e96293a88b71e96e7cc389f658f7e"
MODEL_MANIFESTS = {
    MODEL: MANIFEST,
    "qwen3:0.6b": "6f76d4346c34ba89df6e137fb661b4bb4daf322c1151b6ef0dfda981070a851f",
    "sentientos-hermes4:14b-q4km": "f6a766d405cbb73f9ba64a59b8fb29a3418d0da0b6fad15a0ca70687413ce0ce",
}
ADDRESS = "127.0.0.2"
BASE = f"http://{ADDRESS}:11434"
SOURCE_REPORT = Path(__file__).resolve().parents[1] / (
    "artifacts/experiments/ordinary-chat-retention-20261125/sibling_history_after.json")
FORMAT = (' Reply only with a JSON array of rows. Each row is [input, observed answer, outcome]. '
          'Use an integer or null for the observed answer. Use "correct", "incorrect", or "abstained" '
          'for the outcome. If you have no recorded exercise, return an empty array.')
TRIALS = (("right", "wide"), ("left", "low"), ("empty", "wide"), ("parent", "wide"),
          ("left", "wide"), ("right", "low"), ("left", "wide"))
INLINE_REPORT = ('Report inline-example. Input 47. Answer -4. Incorrect. '
                 'Input 52. Abstained. Input 61. Answer 10. Correct.')
INLINE_QUESTION = "Using the report above, what were the recorded inputs and outcomes?"
INLINE_ROWS = [[47, -4, "incorrect"], [52, None, "abstained"], [61, 10, "correct"]]
CITED_FORMAT = (' Cite the containing record_id once. Copy each observed answer exactly as written. '
                'Return one fenced JSON object with "record_id" and "rows", where each row is '
                '[input integer, answer as a JSON integer or null, outcome as one of "correct", '
                '"incorrect", or "abstained"]. Use record_id null and empty rows if there is no report.')
EXPLICIT_ROW_MAPPING = (
    ' Map examples as [probe_input, observed_answer, outcome]; abstained=true→abstained, else '
    'evaluator_correct=true/false→correct/incorrect; keep JSON types.')


def conditions(cited):
    return TRIALS + ((("empty", "inline"),) if cited else ())


def recall_question(scope, cited):
    question = INLINE_QUESTION if scope == "inline" else QUESTIONS["latest_" + scope]
    return question + (CITED_FORMAT if cited else FORMAT)


def _inject_explicit_row_mapping(prompt, linkage):
    """Add the treatment once to rendered guidance, after retrieval and validation."""
    marker = "[DEVELOPMENTAL_HISTORY_GUIDANCE]\n"
    data_marker = "\n[DEVELOPMENTAL_HISTORY_DATA]"
    start = prompt.find(marker)
    if start < 0:
        return prompt, linkage
    boundary = prompt.find(data_marker, start + len(marker))
    if boundary < 0 or EXPLICIT_ROW_MAPPING.strip() in prompt[start:boundary]:
        raise ValueError("explicit row mapping cannot be bound to the rendered history guidance")
    updated = prompt[:boundary] + "\n" + EXPLICIT_ROW_MAPPING.strip() + prompt[boundary:]
    updated_linkage = dict(linkage)
    updated_linkage["ordinary_developmental_history_prompt_block_digest"] = (
        ordinary_chat_developmental_history_prompt_block_digest(updated))
    return updated, updated_linkage


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, data):
    with path.open("x", encoding="utf-8") as out:
        json.dump(data, out, indent=2, sort_keys=True)
        out.write("\n")


def record_failed_trial(root, trial_root, *, index, condition, plan_hash, prompt_hash, error):
    """Bind an interrupted trial to any governed receipt so failures remain auditable."""
    matches = []
    receipts = root / "inference-custody" / "receipts"
    if receipts.exists():
        for path in receipts.glob("*.json"):
            disk = read(path)
            if disk.get("request", {}).get("prompt_digest") == prompt_hash:
                matches.append(disk)
    if len(matches) > 1:
        raise ValueError("failed trial has ambiguous governed receipts") from error
    receipt = matches[0] if matches else None
    save(trial_root / "failure.json", {
        "schema": "sentientos.sibling_chat_recall_trial_failure:v1",
        "plan_sha256": plan_hash, "trial": index, "condition": condition,
        "prompt_sha256": prompt_hash, "exception_type": type(error).__name__,
        "exception": str(error), "model_invoked": receipt is not None,
        "receipt_id": receipt.get("receipt_id") if receipt else None,
        "receipt_digest": receipt.get("receipt_digest") if receipt else None,
        "receipt_status": receipt.get("status") if receipt else None,
        "reason_codes": receipt.get("reason_codes") if receipt else [],
        "latency_ms": receipt.get("latency_ms") if receipt else None,
        "output_size_bytes": receipt.get("output_size_bytes") if receipt else None,
        "fallback_occurred": receipt.get("fallback_occurred") if receipt else None,
    })


def get_api(path):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(BASE + "/api/" + path, timeout=3) as response:
        return json.load(response)


def _prepare_private_model(models, private, model, manifest_digest):
    """Copy or link exactly the manifest-pinned model into a private store."""
    relative = Path("manifests/registry.ollama.ai/library") / model.replace(":", "/")
    manifest = models / relative
    if sha(manifest.read_bytes()) != manifest_digest:
        raise ValueError("unexpected model manifest")
    (private / relative).parent.mkdir(parents=True, exist_ok=True)
    manifest_target = private / relative
    if manifest_target.exists():
        if sha(manifest_target.read_bytes()) != manifest_digest:
            raise ValueError("private model manifest differs from pin")
    else:
        manifest_target.write_bytes(manifest.read_bytes())
    (private / "blobs").mkdir(exist_ok=True)
    manifest_data = read(manifest)
    expected_files = {relative.as_posix()}
    for layer in [manifest_data["config"], *manifest_data["layers"]]:
        digest = layer["digest"].removeprefix("sha256:")
        filename = "sha256-" + digest
        expected_files.add("blobs/" + filename)
        source = models / "blobs" / filename
        if stream_sha256(source) != (digest, layer["size"]):
            raise ValueError("model layer differs from pinned manifest")
        destination = private / "blobs" / filename
        if not destination.exists():
            try:
                os.link(source, destination)
            except OSError:
                shutil.copyfile(source, destination)
        if stream_sha256(destination) != (digest, layer["size"]):
            raise ValueError("private model layer differs from pinned manifest")
    actual_files = {path.relative_to(private).as_posix() for path in private.rglob("*") if path.is_file()}
    if actual_files != expected_files:
        raise ValueError("private model store contains unexpected files")
    return manifest


@contextmanager
def _loopback_api_forwarder(target_host, target_port):
    """Forward the pinned loopback API to a separately isolated model server."""
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            with socket.create_connection((target_host, target_port), timeout=10) as upstream:
                self.request.settimeout(None)
                peers = {self.request: upstream, upstream: self.request}
                active = set(peers)
                while active:
                    readable, _, _ = select.select(active, [], [], 1.0)
                    for source in readable:
                        try:
                            data = source.recv(65536)
                        except OSError:
                            data = b""
                        if not data:
                            active.discard(source)
                            try:
                                peers[source].shutdown(socket.SHUT_WR)
                            except OSError:
                                pass
                            continue
                        peers[source].sendall(data)

    class Server(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    server = Server((ADDRESS, 11434), Handler)
    thread = threading.Thread(target=server.serve_forever, name="model-api-forwarder", daemon=True)
    thread.start()
    try:
        yield
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@contextmanager
def model_server(install, models, root, model, manifest_digest):
    """Bind an isolated Ollama server to one pinned model artifact."""
    external_models = (os.environ.get("SENTIENTOS_OLLAMA_MODELS")
                       or os.environ.get("SENTIENTOS_OLLAMA_CPU_MODELS"))
    if external_models:
        private = Path(external_models)
        private.mkdir(parents=True, exist_ok=True)
        manifest = _prepare_private_model(models, private, model, manifest_digest)
        target = urlsplit(os.environ.get("SENTIENTOS_OLLAMA_CPU_TARGET", ""))
        if target.scheme != "http" or not target.hostname or not target.port:
            raise ValueError("external model server target must be an explicit HTTP host and port")
        with _loopback_api_forwarder(target.hostname, target.port):
            if get_api("ps")["models"]:
                raise ValueError("external CPU server already has a resident model")
            version = get_api("version")["version"]
            tagged, = [item for item in get_api("tags")["models"] if item["name"] == model]
            if tagged["digest"] != manifest_digest:
                raise ValueError("external server did not load the pinned manifest")
            yield manifest, version
        return
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind((ADDRESS, 11434))
    with tempfile.TemporaryDirectory(dir=root, prefix="cpu-runtime-") as temp:
        base = Path(temp)
        binary = base / "bin/ollama"
        binary.parent.mkdir()
        os.link((install / "bin/ollama").resolve(strict=True), binary)
        lib = base / "lib/ollama"
        lib.mkdir(parents=True)
        for f in (install / "lib/ollama").iterdir():
            if f.is_file() and (f.name.startswith(("libggml-cpu-", "libggml.", "libggml-base.",
                    "libgomp.", "libllama.", "libllama-common.", "libllama-server-impl.", "libmtmd."))
                    or f.name == "llama-server"):
                os.link(f.resolve(strict=True), lib / f.name)
        private = base / "models"
        manifest = _prepare_private_model(models, private, model, manifest_digest)
        env = {**os.environ, "CUDA_VISIBLE_DEVICES": "-1", "ROCR_VISIBLE_DEVICES": "-1",
               "OLLAMA_VULKAN": "0", "OLLAMA_HOST": ADDRESS + ":11434", "OLLAMA_MODELS": str(private),
               "OLLAMA_NO_CLOUD": "1", "OLLAMA_NOPRUNE": "1", "OLLAMA_NUM_PARALLEL": "1"}
        with (root / "ollama.log").open("xb") as log:
            process = subprocess.Popen([binary, "serve"], env=env, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                for _ in range(80):
                    if process.poll() is not None:
                        raise RuntimeError("dedicated server stopped during startup")
                    try:
                        version = get_api("version")["version"]
                    except OSError:
                        time.sleep(0.25)
                        continue
                    break
                else:
                    raise RuntimeError("dedicated server did not start")
                if get_api("ps")["models"]:
                    raise ValueError("dedicated server already has a resident model")
                yield manifest, version
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()


def score_answer(text, profiles):
    """Grade the delivered text against every profile without knowing which arm generated it."""
    try:
        rows = json.loads(text)
    except ValueError:
        rows = None
    if not isinstance(rows, list) or any(not isinstance(r, list) or len(r) != 3
            or type(r[0]) is not int or (r[1] is not None and type(r[1]) is not int)
            or r[2] not in ("correct", "incorrect", "abstained")
            or ((r[1] is None) != (r[2] == "abstained")) for r in rows):
        return {"format": "invalid", "exact_profiles": []}
    if len({r[0] for r in rows}) != len(rows):
        return {"format": "duplicate_input", "exact_profiles": []}
    return {"format": "valid", "exact_profiles": [k for k, v in profiles.items() if sorted(v) == sorted(rows)]}


def score_cited_answer(text, profiles):
    """Allow one protocol-approved JSON fence; score rows separately from citation."""
    try:
        stripped = text.strip()
        if stripped.startswith("```json\n") and stripped.endswith("\n```"):
            stripped = stripped[len("```json\n"):-len("\n```")].strip()
        value = json.loads(stripped)
    except ValueError:
        value = None
    return _score_cited_value(value, profiles)


def score_cited_answer_v2_legacy(text, profiles):
    """Reproduce the original v2 scorer when validating its immutable saved scores."""
    try:
        value = json.loads(text.strip())
    except ValueError:
        value = None
    return _score_cited_value(value, profiles)


def _score_cited_value(value, profiles):
    if (not isinstance(value, dict) or set(value) != {"record_id", "rows"}
            or not (value["record_id"] is None or isinstance(value["record_id"], str))):
        return {"format": "invalid", "exact_profiles": [], "cited_record": None}
    if not isinstance(value["rows"], list) or any(
            not isinstance(row, list) or len(row) != 3
            or type(row[0]) is not int or (row[1] is not None and type(row[1]) is not int)
            or not isinstance(row[2], str) for row in value["rows"]):
        return {"format": "invalid", "exact_profiles": [], "cited_record": value["record_id"]}
    parsed = score_answer(json.dumps(value["rows"]), profiles)
    parsed["cited_record"] = value["record_id"]
    return parsed


def source_rows(owner, evidence):
    run = owner.experiments.load_run(evidence["source_run_id"])
    result, = [r["score"] for r in run["objective_scores"] if r["condition_id"] == "history_present"]
    if result["score_digest"] != evidence["source_score_digest"]:
        raise ValueError("oracle differs from source score")
    return [[r["probe_input"], r["observed_answer"], "abstained" if r.get("abstained")
             else "correct" if r["correct"] else "incorrect"] for r in result["probe_results"]]


class VerifiedChat(DevelopmentLocalChatInference):
    capture_only = True
    explicit_row_mapping = False

    def generate(self, **kwargs):
        if self.explicit_row_mapping:
            kwargs = dict(kwargs)
            kwargs["prompt"], kwargs["caller_linkage"] = _inject_explicit_row_mapping(
                kwargs["prompt"], kwargs["caller_linkage"])
        if self.capture_only:
            raise _CapturedRequest(kwargs["prompt"], kwargs["caller_linkage"])
        if sha(kwargs["prompt"].encode()) != self.frozen_hash:
            raise ValueError("ordinary chat prompt differs from preregistration")
        self.receipt = super().generate(**kwargs)
        return self.receipt


def run(cycles, install, models, root, *, cited=False, explicit_row_mapping=False, preflight_only=False,
        model_name=MODEL, diagnostic_condition=None, gpu_layers=0):
    if explicit_row_mapping and not cited:
        raise ValueError("explicit row mapping requires the cited response protocol")
    if diagnostic_condition is not None and (not cited or explicit_row_mapping
            or diagnostic_condition not in {"empty_wide", "empty_inline"}):
        raise ValueError("diagnostic condition must be an empty cited control without treatment")
    if model_name not in MODEL_MANIFESTS:
        raise ValueError("model is not in the pinned recall model registry")
    if type(gpu_layers) is not int or not 0 <= gpu_layers <= 128:
        raise ValueError("GPU layer count must be an integer from 0 through 128")
    if gpu_layers and not (os.environ.get("SENTIENTOS_OLLAMA_MODELS")
                           or os.environ.get("SENTIENTOS_OLLAMA_CPU_MODELS")):
        raise ValueError("GPU inference requires an explicitly isolated external Ollama server")
    manifest_digest = MODEL_MANIFESTS[model_name]
    root.mkdir(parents=True, exist_ok=False)
    baseline = read(SOURCE_REPORT)
    historical_request = _read_receipt(cycles / ("rootless-cognition-cycle-" + TARGET))[1]["request"]
    with model_server(install, models, root, model_name, manifest_digest) as (manifest, version), _rootless_governance_custody(root):
        options = {"api_base": BASE, "model": model_name, "manifest_sha256": manifest_digest,
                   "num_gpu": gpu_layers, "num_thread": 2, "timeout_seconds": 120, "seed": 42,
                   "think": False, "keep_alive": "5m"}
        config = ModelConfig([ModelCandidate(manifest, "ollama", model_name, options)], max_context_tokens=4096,
                             generation=GenerationConfig(max_new_tokens=160, temperature=0.0, top_p=1.0))
        authority = build_local_model_authority_map(config, allowed_roots=[manifest.parent])
        model = LocalModel.load_candidate(0, config=config)
        identity = model.active_identity.to_dict()
        if not authority.record_for_active_identity(model.active_identity, "local_user_chat"):
            raise ValueError("ordinary chat model identity is ineligible")
        inference = VerifiedChat(GovernedLocalModelInvoker(model=model, authority_map=authority,
            kernel=_resource_governed_kernel(root), runtime_root=root / "inference-custody"))
        inference.explicit_row_mapping = explicit_row_mapping
        owners, snapshots, source_owners = {}, {}, {}
        for arm, suffix in CYCLES.items():
            cycle = cycles / ("rootless-cognition-cycle-" + suffix)
            resident = root / arm / "resident-cognition"
            archive(cycle, resident)
            kinds = _source_kinds_from_history(resident / "history")
            owner = _owner(resident, kinds, resident.parent, historical_request)
            if admitted_boundary(owner.writeback.inspect_completed_records()) != baseline["arms"][arm]["admitted_boundary_digest"]:
                raise ValueError("archive differs from sibling comparison")
            owners[arm] = owner
            source_owners[cycle.name] = owner
        owners["empty"] = _owner(root / "empty", kinds, cycle, historical_request)
        profiles, questions, exposure, bases = {"empty": []}, {}, {}, {}
        for arm, scope in dict.fromkeys(conditions(cited)):
            owner = owners[arm]
            snapshots[arm] = owner.ordinary_chat_developmental_history_state_snapshot()
            question = questions[scope] = ((INLINE_REPORT + "\n") if scope == "inline" else "") + recall_question(
                scope, cited)
            base, captured = _service_request(owner, root / "preflight" / arm / scope, identity, question,
                                              bind_invocation=True, capture_adapter=inference,
                                              capture_history_instruction=explicit_row_mapping)
            if bases.setdefault(scope, base) != base:
                raise ValueError("unmatched prompts outside the history block")
            key = arm + "_" + scope
            evidence = captured["prompt_score_evidence"]
            if arm == "empty":
                if evidence or captured["history_block_digest"] is not None:
                    raise ValueError("empty control exposed history")
                if scope == "inline":
                    profiles["inline"] = INLINE_ROWS
            else:
                if len(evidence) != 1:
                    raise ValueError(f"history condition {key} did not expose exactly one scored record")
                actual, = evidence
                prior, = baseline["questions"]["latest_" + scope]["captures"][arm]["prompt_score_evidence"]
                if actual["source_score_digest"] != prior["source_score_digest"] or actual["record_id"] != prior["record_id"]:
                    raise ValueError("question format or target identity changed the source observation")
                profile = "shared_low" if scope == "low" else key
                record = owner.writeback.store.get(prior["record_id"])
                origin = record.correlation_id.split(":", 1)[0]
                if not re.fullmatch(r"rootless-cognition-cycle-[0-9a-f]{20}", origin):
                    raise ValueError("invalid source cycle in admitted record")
                if origin not in source_owners:
                    original = root / "oracles" / origin / "resident-cognition"
                    archive(cycles / origin, original)
                    source_owners[origin] = _owner(original, _source_kinds_from_history(original / "history"),
                                                   original.parent, historical_request)
                source_owner = source_owners[origin]
                if source_owner.writeback.store.get(record.record_id).record_digest != record.record_digest:
                    raise ValueError("inherited record differs from its origin")
                oracle = source_rows(source_owner, prior)
                if profiles.setdefault(profile, oracle) != oracle:
                    raise ValueError("unmatched shared low-range oracle")
            exposure[key] = captured
        protocol = "v5" if explicit_row_mapping else "v3" if cited else "v1"
        plan = {"schema": ("sentientos.sibling_chat_recall_diagnostic:v1" if diagnostic_condition
                            else "sentientos.sibling_chat_recall_plan:" + protocol), "model": model_name,
                "source_report_sha256": sha(SOURCE_REPORT.read_bytes()), "model_identity": identity,
                "ollama_version": version, "options": options, "context_tokens": config.max_context_tokens,
                "generation": config.generation.as_kwargs(),
                "trials": ([diagnostic_condition.split("_", 1)] if diagnostic_condition
                           else conditions(cited)), "questions": questions,
                "profiles": profiles, "exposures": exposure, "matched_base_sha256": {
                    k: sha(v.encode()) for k, v in bases.items()}, "source_code_sha256": sha(Path(__file__).read_bytes()),
                "intervention": ({"id": "explicit_developmental_history_field_to_row_mapping:v2",
                                  "guidance": EXPLICIT_ROW_MAPPING,
                                  "guidance_sha256": sha(EXPLICIT_ROW_MAPPING.encode())}
                                 if explicit_row_mapping else None),
                "criterion": "One JSON array, distinct integer inputs, exact answers and outcome labels, row order ignored. Grade each delivery against every profile. Missing or malformed replies never pass."}
        if diagnostic_condition:
            plan["diagnostic_condition"] = diagnostic_condition
        if cited:
            plan["criterion"] = ("One JSON object with record_id and rows. A single Markdown JSON fence is accepted. "
                "Score exact rows against every profile, independently of the citation. Passing also requires the "
                "source record ID, null for empty history, or inline-example for the direct-reading control. "
                "The scorer removes exactly one surrounding ```json fence before parsing.")
        save(root / "plan.json", plan)
        plan_hash = sha((root / "plan.json").read_bytes())
        if preflight_only:
            if get_api("ps")["models"]:
                raise ValueError("preflight-only mode found a resident server model")
            save(root / "preflight.json", {
                "schema": "sentientos.sibling_chat_recall_preflight:v1",
                "plan_sha256": plan_hash, "model_invoked": False,
                "inference_performed": False, "runtime_condition_created": False,
                "learning_established": False, "authority": False,
                "resident_vram_bytes": 0,
            })
            print("preflight_saved", plan_hash, flush=True)
            return
        trials = []
        inference.capture_only = False
        trial_conditions = ([tuple(diagnostic_condition.split("_", 1))] if diagnostic_condition
                            else conditions(cited))
        for index, (arm, scope) in enumerate(trial_conditions):
            key = arm + "_" + scope
            inference.frozen_hash = exposure[key]["prompt_sha256"]
            inference.receipt = None
            trial_root = root / "trials" / str(index)
            service = PersistentConversationService(inference=inference,
                inference_timeout_seconds=options["timeout_seconds"],
                session_store=ConversationSessionStore(trial_root / "sessions"),
                memory_store=CanonicalMemoryStore(trial_root / "memory"),
                resident_cognition_bridge=ResidentDevelopmentalCompanionBridge(owners[arm], cognition_available=lambda: False))
            try:
                response = service.chat(questions[scope], session_id=service.create_session(), request_id="sibling-recall")
            except Exception as error:
                record_failed_trial(root, trial_root, index=index, condition=key,
                    plan_hash=plan_hash, prompt_hash=exposure[key]["invocation_prompt_digest"], error=error)
                raise
            receipt = inference.receipt
            disk = read(root / "inference-custody/receipts" / (receipt.receipt_id + ".json"))
            if (not validate_receipt(disk)[0] or disk["receipt_digest"] != receipt.receipt_digest
                    or disk["request"]["active_model_identity"] != identity
                    or disk["request"]["prompt_digest"] != exposure[key]["invocation_prompt_digest"]
                    or disk["output_digest"] != digest_payload({"output": receipt.output_text})
                    or disk["status"] != "admitted_completed" or not receipt.admission_decision_ref
                    or receipt.fallback_occurred or receipt.output_text is None):
                raise ValueError("governed inference did not yield a verified model response")
            placement, = get_api("ps")["models"]
            if (placement["digest"] != manifest_digest
                    or (gpu_layers == 0 and placement["size_vram"] != 0)
                    or (gpu_layers > 0 and placement["size_vram"] <= 0)):
                raise ValueError("model residency differs from the selected CPU/GPU placement")
            grade = (score_cited_answer if cited else score_answer)(response.response, profiles)
            expected = ("inline" if scope == "inline" else "empty" if arm == "empty"
                        else "shared_low" if scope == "low" else key)
            records = exposure[key]["prompt_score_evidence"]
            citation = "inline-example" if scope == "inline" else records[0]["record_id"] if records else None
            result = {"trial": index, "condition": key, "plan_sha256": plan_hash,
                      "prompt_sha256": inference.frozen_hash, "receipt": disk, "resident_vram_bytes": placement["size_vram"],
                      "model_output": receipt.output_text, "delivered": response.response, "score": grade,
                      "expected_profile": expected, "exact": expected in grade["exact_profiles"]
                           and (not cited or grade["cited_record"] == citation)}
            save(trial_root / "result.json", result)
            trials.append(result)
            print(index, key, grade, flush=True)
        if any(owner.ordinary_chat_developmental_history_state_snapshot() != snapshots[k] for k, owner in owners.items()):
            raise ValueError("resident history changed during the read-only comparison")
        save(root / "result.json", {"plan_sha256": plan_hash, "trials": trials})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("cycles", "ollama_install", "models", "new_run_directory"):
        parser.add_argument(arg, type=Path)
    parser.add_argument("--cited", action="store_true")
    parser.add_argument("--explicit-row-mapping", action="store_true",
                        help="Run the cited protocol with an explicit history-field to output-row mapping")
    parser.add_argument("--preflight-only", action="store_true",
                        help="Save and validate the complete prompt plan without invoking the model")
    parser.add_argument("--model", choices=tuple(MODEL_MANIFESTS), default=MODEL,
                        help="Select a pre-pinned local model artifact")
    parser.add_argument("--diagnostic-condition", choices=("empty_wide", "empty_inline"),
                        help="Run one empty-history cited control to diagnose model generation")
    parser.add_argument("--gpu-layers", type=int, default=0,
                        help="Offload this many Ollama model layers (0 keeps the run on CPU)")
    args = parser.parse_args()
    run(args.cycles, args.ollama_install, args.models, args.new_run_directory, cited=args.cited,
        explicit_row_mapping=args.explicit_row_mapping, preflight_only=args.preflight_only,
        model_name=args.model, diagnostic_condition=args.diagnostic_condition, gpu_layers=args.gpu_layers)
