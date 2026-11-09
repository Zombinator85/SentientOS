"""Bounded ingress for Godot's non-authoritative renderer self-reports."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
import time
import base64
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, cast

from .embodiment_self_observation import (
    EmbodimentEvidenceOwner,
    EmbodimentObservation,
    semantic_digest,
)

RENDERER_REPORT_SCHEMA_V1 = "sentientos.avatar_renderer_report:v1"
RENDERER_REPORT_SCHEMA = "sentientos.avatar_renderer_report:v2"
MAX_RENDERER_REPORT_BYTES = 32_768
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_CORRELATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_REPORT_FIELDS = frozenset({
    "schema_version", "evidence_class", "source_id", "renderer_generation_id",
    "sequence", "reported_at", "session_id", "turn_id", "output_digest",
    "output_mode", "commanded_state", "renderer_state", "frame_delta_seconds",
    "apply_duration_usec", "body_generation", "effect_proven",
    "independent_observation", "source_digest",
})
_ADOPTED_BODY_REPORT_FIELDS = frozenset({
    "status", "evidence_posture", "artifact_sha256", "manifest_digest",
    "pointer_digest", "adoption_receipt_digest", "authority_effects_performed",
})


class RendererReportIngressError(ValueError):
    """Invalid, oversized, or conflicting renderer report."""


class RendererReportEvidenceStore:
    """Content-addressed durable custody for authenticated renderer self-reports."""

    def __init__(self, root: Path | str, *, create: bool = True) -> None:
        self.root = Path(root)
        exists = self.root.exists()
        if self.root.is_symlink():
            raise RendererReportIngressError("renderer_report_store_root_symlink")
        if exists:
            if self.root.stat().st_mode & 0o077:
                raise RendererReportIngressError("renderer_report_store_permissions_too_open")
        elif create:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if exists and (not self.root.is_dir() or self.root.is_symlink()):
            raise RendererReportIngressError("renderer_report_store_root_invalid")
        self._available = self.root.exists()

    def capture(self, *, report: Mapping[str, Any], transport: Mapping[str, Any]) -> dict[str, Any]:
        if self.root.is_symlink() or not self.root.is_dir() or self.root.stat().st_mode & 0o077:
            raise RendererReportIngressError("renderer_report_store_permissions_invalid")
        observation = renderer_report_observation(report)
        if set(transport) != {"message_id", "source_id", "session_id", "generation_id",
                              "sequence", "created_at", "report_source_id",
                              "report_generation_id", "report_sequence", "signed_envelope"}:
            raise RendererReportIngressError("renderer_report_transport_provenance_invalid")
        if (transport["report_source_id"] != report["source_id"]
                or transport["report_generation_id"] != report["renderer_generation_id"]
                or transport["report_sequence"] != report["sequence"]
                or transport["sequence"] != report["sequence"]
                or (report["session_id"] is not None and transport["session_id"] != report["session_id"])):
            raise RendererReportIngressError("renderer_report_transport_lineage_mismatch")
        for field in ("message_id", "source_id", "session_id", "generation_id", "created_at"):
            if not isinstance(transport[field], str) or not transport[field] or len(transport[field]) > 256:
                raise RendererReportIngressError("renderer_report_transport_provenance_invalid")
        if type(transport["sequence"]) is not int or transport["sequence"] < 1:
            raise RendererReportIngressError("renderer_report_transport_provenance_invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", str(transport["message_id"])):
            raise RendererReportIngressError("renderer_report_transport_provenance_invalid")
        signed_envelope = transport["signed_envelope"]
        if not isinstance(signed_envelope, bytes) or not signed_envelope:
            raise RendererReportIngressError("renderer_report_signed_envelope_missing")
        try:
            from .gaming_companion_bridge_runtime import bridge_message_id
            if bridge_message_id(signed_envelope) != transport["message_id"]:
                raise RendererReportIngressError("renderer_report_signed_envelope_mismatch")
            envelope = json.loads(signed_envelope.decode("utf-8"))
            if (envelope.get("kind") != "renderer_report"
                    or envelope.get("source_id") != transport["source_id"]
                    or envelope.get("session_id") != transport["session_id"]
                    or envelope.get("generation_id") != transport["generation_id"]
                    or envelope.get("sequence") != transport["sequence"]):
                raise RendererReportIngressError("renderer_report_transport_envelope_mismatch")
            envelope_time = datetime.fromisoformat(str(envelope["created_at"]).replace("Z", "+00:00"))
            transport_time_check = datetime.fromisoformat(str(transport["created_at"]).replace("Z", "+00:00"))
            if (envelope_time.tzinfo is None or transport_time_check.tzinfo is None
                    or envelope_time != transport_time_check):
                raise RendererReportIngressError("renderer_report_transport_envelope_mismatch")
        except RendererReportIngressError:
            raise
        except (ValueError, TypeError) as exc:
            raise RendererReportIngressError("renderer_report_signed_envelope_invalid") from exc
        try:
            transport_time = datetime.fromisoformat(str(transport["created_at"]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise RendererReportIngressError("renderer_report_transport_provenance_invalid") from exc
        if transport_time.tzinfo is None:
            raise RendererReportIngressError("renderer_report_transport_provenance_invalid")
        transport_summary = {key: value for key, value in transport.items() if key != "signed_envelope"}
        transport_summary["signed_envelope_sha256"] = hashlib.sha256(signed_envelope).hexdigest()
        record = EmbodimentEvidenceOwner([observation]).world_state_records()[0]
        record["payload"] = {
            **dict(record["payload"]),
            "transport_provenance": transport_summary,
            "transport_authenticated_at_capture": True,
            "transport_authentication_principal": transport["source_id"],
            "renderer_source_independently_authenticated": False,
            "transport_signature_reverified_on_load": False,
            "renderer_state_independently_observed": False,
            "durable_capture_schema": "sentientos.renderer_report_capture:v1",
        }
        payload = {"schema_version": "sentientos.renderer_report_capture:v1",
                   "report": dict(report), "world_state_record": record,
                   "transport_provenance": transport_summary,
                   "signed_envelope_base64": base64.b64encode(signed_envelope).decode("ascii"),
                   "capture_status": "authenticated_edge_relay_renderer_self_report_unverified",
                   "effect_proven": False, "independent_observation": False}
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_RENDERER_REPORT_BYTES * 2:
            raise RendererReportIngressError("renderer_report_capture_size_exceeded")
        file_digest = hashlib.sha256(encoded).hexdigest()
        filename = f"{file_digest}.json"
        dir_fd = os.open(self.root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
                         | getattr(os, "O_NOFOLLOW", 0))
        temp_name = f".{file_digest}.{os.getpid()}.{threading.get_ident()}.tmp"
        temp_fd: int | None = None
        try:
            temp_fd = os.open(temp_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                              | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=dir_fd)
            with os.fdopen(temp_fd, "wb", closefd=True) as stream:
                temp_fd = None
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temp_name, filename, src_dir_fd=dir_fd, dst_dir_fd=dir_fd,
                        follow_symlinks=False)
            except FileExistsError:
                existing_fd = os.open(filename, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=dir_fd)
                with os.fdopen(existing_fd, "rb") as stream:
                    if stream.read(MAX_RENDERER_REPORT_BYTES * 2 + 1) != encoded:
                        raise RendererReportIngressError("renderer_report_capture_collision")
            os.unlink(temp_name, dir_fd=dir_fd)
            os.fsync(dir_fd)
        except OSError as exc:
            raise RendererReportIngressError("renderer_report_capture_write_failed") from exc
        finally:
            if temp_fd is not None:
                os.close(temp_fd)
            try:
                os.unlink(temp_name, dir_fd=dir_fd)
            except OSError:
                pass
            os.close(dir_fd)
        return {"capture_id": file_digest, "capture_digest": file_digest,
                "artifact_name": filename, "capture_status": payload["capture_status"],
                "effect_proven": False, "independent_observation": False}

    def world_state_records(self, *, max_records: int = 256) -> list[dict[str, Any]]:
        if type(max_records) is not int or not 1 <= max_records <= 1024:
            raise RendererReportIngressError("renderer_report_record_bound_invalid")
        if (not self._available or not self.root.is_dir() or self.root.is_symlink()
                or self.root.stat().st_mode & 0o077):
            return []
        paths = sorted(self.root.glob("[0-9a-f][0-9a-f]*.json"))[-max_records:]
        records: list[dict[str, Any]] = []
        for path in paths:
            if path.is_symlink() or not path.is_file():
                continue
            try:
                raw = path.read_bytes()
                if len(raw) > MAX_RENDERER_REPORT_BYTES * 2:
                    continue
                if path.stem != hashlib.sha256(raw).hexdigest():
                    continue
                value = json.loads(raw.decode("utf-8"))
                if not isinstance(value, dict) or value.get("schema_version") != "sentientos.renderer_report_capture:v1":
                    continue
                report = value.get("report")
                transport = value.get("transport_provenance")
                signed_envelope_text = value.get("signed_envelope_base64")
                if (not isinstance(report, dict) or not isinstance(transport, dict)
                        or not isinstance(signed_envelope_text, str)):
                    continue
                signed_envelope = base64.b64decode(signed_envelope_text, validate=True)
                if hashlib.sha256(signed_envelope).hexdigest() != transport.get("signed_envelope_sha256"):
                    continue
                from .gaming_companion_bridge_runtime import bridge_message_id
                if bridge_message_id(signed_envelope) != transport.get("message_id"):
                    continue
                envelope = json.loads(signed_envelope.decode("utf-8"))
                if (envelope.get("kind") != "renderer_report"
                        or envelope.get("source_id") != transport.get("source_id")
                        or envelope.get("session_id") != transport.get("session_id")
                        or envelope.get("generation_id") != transport.get("generation_id")
                        or envelope.get("sequence") != transport.get("sequence")):
                    continue
                envelope_time = datetime.fromisoformat(str(envelope["created_at"]).replace("Z", "+00:00"))
                transport_time = datetime.fromisoformat(str(transport["created_at"]).replace("Z", "+00:00"))
                if (envelope_time.tzinfo is None or transport_time.tzinfo is None
                        or envelope_time != transport_time):
                    continue
                # Re-run the report and transport lineage checks on every load.
                observation = renderer_report_observation(report)
                if (transport.get("report_source_id") != report.get("source_id")
                        or transport.get("report_generation_id") != report.get("renderer_generation_id")
                        or transport.get("report_sequence") != report.get("sequence")
                        or transport.get("sequence") != report.get("sequence")
                        or (report.get("session_id") is not None
                            and transport.get("session_id") != report.get("session_id"))):
                    continue
                record = EmbodimentEvidenceOwner([observation]).world_state_records()[0]
                record["payload"] = {**dict(record["payload"]),
                    "transport_provenance": transport,
                    "transport_authenticated_at_capture": True,
                    "transport_authentication_principal": transport.get("source_id"),
                    "renderer_source_independently_authenticated": False,
                    "transport_signature_reverified_on_load": False,
                    "renderer_state_independently_observed": False,
                    "durable_capture_id": hashlib.sha256(raw).hexdigest()}
                records.append(record)
            except (OSError, ValueError, TypeError):
                continue
        return records


class RendererReportCaptureOwner:
    """Supervise a supplied authenticated bridge runtime and persist renderer reports."""

    def __init__(self, *, runtime: Any, store: RendererReportEvidenceStore,
                 receive_timeout_seconds: float = 0.2) -> None:
        if not callable(getattr(runtime, "start", None)) or not callable(getattr(runtime, "receive", None)) or not callable(getattr(runtime, "close", None)):
            raise RendererReportIngressError("renderer_report_bridge_runtime_required")
        if not 0 < receive_timeout_seconds <= 5:
            raise RendererReportIngressError("renderer_report_receive_timeout_invalid")
        self._runtime = runtime
        self._store = store
        self._timeout = receive_timeout_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._captured = 0
        self._rejected = 0
        self._last_capture: Mapping[str, Any] | None = None

    def start(self) -> None:
        if self._thread is not None:
            raise RendererReportIngressError("renderer_report_owner_already_started")
        self._runtime.start()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="renderer-report-capture", daemon=True)
        self._thread.start()

    def status(self) -> dict[str, Any]:
        return {"running": bool(self._thread and self._thread.is_alive() and not self._stop.is_set()),
                "captured": self._captured, "rejected": self._rejected,
                "last_capture": dict(self._last_capture) if self._last_capture else None,
                "renderer_reports_are_independent_observations": False}

    def close(self) -> None:
        self._stop.set()
        self._runtime.close()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(1.0, self._timeout + 0.5))
        self._thread = None

    def _run(self) -> None:
        from .gaming_companion_bridge import VerifiedBridgeMessage

        while not self._stop.is_set():
            try:
                message = self._runtime.receive(timeout=self._timeout)
                if type(message) is not VerifiedBridgeMessage:
                    self._rejected += 1
                    continue
                if getattr(message, "kind", None) != "renderer_report":
                    self._rejected += 1
                    continue
                report = dict(message.payload)
                transport = {"message_id": message.message_id, "source_id": message.source_id,
                    "session_id": message.session_id, "generation_id": message.generation_id,
                    "sequence": message.sequence, "created_at": message.created_at,
                    "report_source_id": report.get("source_id"),
                    "report_generation_id": report.get("renderer_generation_id"),
                    "report_sequence": report.get("sequence"),
                    "signed_envelope": message.signed_envelope}
                self._last_capture = self._store.capture(report=report, transport=transport)
                self._captured += 1
            except ValueError as exc:
                if str(exc) == "bridge_receive_timeout":
                    continue
                if not self._stop.is_set():
                    self._rejected += 1
                time.sleep(min(self._timeout, 0.05))
            except Exception:
                if not self._stop.is_set():
                    self._rejected += 1
                time.sleep(min(self._timeout, 0.05))


def renderer_report_observation(report: Mapping[str, Any]) -> EmbodimentObservation:
    """Convert one Godot self-report into unverified embodiment evidence.

    The adopted-body branch preserves the renderer's asserted body lineage for
    later comparison with the authoritative pointer. It does not authenticate
    adoption or promote renderer state into independent observation.
    """
    if (not isinstance(report, Mapping)
            or set(report) not in (_REPORT_FIELDS, _REPORT_FIELDS | {"body_identity"})):
        raise RendererReportIngressError("renderer_report_shape_invalid")
    try:
        bounded = json.loads(json.dumps(report, ensure_ascii=False, allow_nan=False))
        encoded = json.dumps(bounded, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise RendererReportIngressError("renderer_report_not_bounded_json") from exc
    if len(encoded) > MAX_RENDERER_REPORT_BYTES:
        raise RendererReportIngressError("renderer_report_too_large")
    renderer_source_id = bounded.get("source_id")
    body_generation = bounded.get("body_generation")
    renderer_state = bounded.get("renderer_state")
    if (bounded["schema_version"] not in {RENDERER_REPORT_SCHEMA_V1, RENDERER_REPORT_SCHEMA}
            or bounded["evidence_class"] != "avatar_renderer_reported_state"
            or not isinstance(bounded["renderer_generation_id"], str)
            or not bounded["renderer_generation_id"].startswith("godot-demo-")
            or type(bounded["sequence"]) is not int or bounded["sequence"] < 1
            or not isinstance(bounded["reported_at"], str) or not bounded["reported_at"]
            or bounded["effect_proven"] is not False
            or bounded["independent_observation"] is not False
            or not isinstance(bounded["source_digest"], str)
            or not _SHA256.fullmatch(bounded["source_digest"])):
        raise RendererReportIngressError("renderer_report_identity_invalid")
    adopted_body = (renderer_state.get("adopted_body")
                    if isinstance(renderer_state, Mapping) else None)
    if renderer_source_id == "godot-procedural-demo":
        if (body_generation != "godot-procedural-demo-unadopted"
                or "body_identity" in bounded or adopted_body is not None):
            raise RendererReportIngressError("renderer_report_identity_invalid")
    elif renderer_source_id == "godot-adopted-body-demo":
        if (bounded["schema_version"] != RENDERER_REPORT_SCHEMA
                or "body_identity" not in bounded
                or not isinstance(bounded.get("body_identity"), str)
                or not bounded["body_identity"] or len(bounded["body_identity"]) > 128
                or type(body_generation) is not int or body_generation < 1
                or not isinstance(adopted_body, Mapping)
                or set(adopted_body) != _ADOPTED_BODY_REPORT_FIELDS
                or adopted_body.get("status") != "active"
                or adopted_body.get("evidence_posture")
                    != "trusted_loader_adoption_receipt_verified"
                or adopted_body.get("authority_effects_performed") is not False
                or not isinstance(adopted_body.get("artifact_sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", str(adopted_body.get("artifact_sha256"))) is None
                or any(not isinstance(adopted_body.get(field), str)
                    or _SHA256.fullmatch(str(adopted_body[field])) is None
                    for field in ("manifest_digest", "pointer_digest", "adoption_receipt_digest"))):
            raise RendererReportIngressError("renderer_report_adopted_body_lineage_invalid")
    else:
        raise RendererReportIngressError("renderer_report_identity_invalid")
    source_payload = dict(bounded)
    claimed_source_digest = source_payload.pop("source_digest")
    expected_source_digest = "sha256:" + hashlib.sha256(json.dumps(
        source_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False).encode("utf-8")).hexdigest()
    if claimed_source_digest != expected_source_digest:
        raise RendererReportIngressError("renderer_report_source_digest_mismatch")
    try:
        timestamp = datetime.fromisoformat(bounded["reported_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise RendererReportIngressError("renderer_report_timestamp_invalid") from exc
    if timestamp.tzinfo is None:
        raise RendererReportIngressError("renderer_report_timestamp_invalid")
    state = bounded["commanded_state"]
    renderer_state = bounded["renderer_state"]
    renderer_state_fields = {"expression", "motion", "applied_render_cap_fps"}
    if bounded["schema_version"] == RENDERER_REPORT_SCHEMA:
        renderer_state_fields.add("speech")
    if renderer_source_id == "godot-adopted-body-demo":
        renderer_state_fields.add("adopted_body")
    intensity = state.get("intensity") if isinstance(state, dict) else None
    frame_delta = bounded["frame_delta_seconds"]
    apply_duration = bounded["apply_duration_usec"]
    if (not isinstance(state, dict)
            or set(state) != {"expression", "mood", "intensity", "motion", "workload_mode"}
            or any(not isinstance(state[key], str) or not state[key]
                   for key in ("expression", "mood", "motion"))
            or state["workload_mode"] not in {"normal", "gaming"}
            or not isinstance(intensity, (int, float)) or isinstance(intensity, bool)
            or not 0 <= intensity <= 1
            or not isinstance(renderer_state, dict)
            or set(renderer_state) != renderer_state_fields
            or not isinstance(renderer_state["expression"], dict)
            or not isinstance(renderer_state["motion"], dict)
            or not isinstance(renderer_state["expression"].get("status"), str)
            or set(renderer_state["motion"]) != {
                "active_motion", "animation_player_active", "head_rotation_radians",
                "left_arm_rotation_radians", "body_position", "observed_nodes",
            }
            or not isinstance(renderer_state["motion"].get("observed_nodes"), dict)
            or type(renderer_state["applied_render_cap_fps"]) is not int
            or renderer_state["applied_render_cap_fps"] not in {15, 60}
            or (frame_delta is not None and (
                type(frame_delta) not in {int, float} or not math.isfinite(frame_delta)
                or frame_delta < 0))
            or type(apply_duration) is not int or apply_duration < 0):
        raise RendererReportIngressError("renderer_report_state_invalid")
    if bounded["schema_version"] == RENDERER_REPORT_SCHEMA:
        _validate_speech_report(renderer_state["speech"])
    session_id, turn_id = bounded["session_id"], bounded["turn_id"]
    output_digest, output_mode = bounded["output_digest"], bounded["output_mode"]
    if (session_id is None) != (turn_id is None):
        raise RendererReportIngressError("renderer_report_correlation_incomplete")
    if session_id is not None and (
            not isinstance(session_id, str) or not _CORRELATION_ID.fullmatch(session_id)
            or not isinstance(turn_id, str) or not _CORRELATION_ID.fullmatch(turn_id)
            or not isinstance(output_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", output_digest)
            or output_mode != "chat_response_visual_only"):
        raise RendererReportIngressError("renderer_report_correlation_invalid")
    if session_id is None and any(value is not None for value in (output_digest, output_mode)):
        raise RendererReportIngressError("renderer_report_correlation_invalid")

    report_digest = semantic_digest(bounded)
    source_id = (f"godot-renderer:{bounded['renderer_generation_id']}:{bounded['sequence']}")
    observation = EmbodimentObservation(
        source_id=source_id,
        source_schema=str(bounded["schema_version"]),
        source_digest=report_digest,
        observed_at=bounded["reported_at"],
        provenance_class=("godot_adopted_body_renderer_self_report_unverified"
            if renderer_source_id == "godot-adopted-body-demo"
            else "godot_procedural_demo_unverified"),
        freshness="unknown",
        posture="synthetic_test",
        evidence_class="avatar_renderer_reported_state",
        subject_id=source_id,
        subject_kind="avatar_renderer_reported_state",
        payload={
            "renderer_report": bounded,
            "renderer_report_digest": report_digest,
            "renderer_source_digest_claim": bounded["source_digest"],
            "capture_status": "unverified_renderer_self_report",
        },
        effect_claimed=False,
        effect_proven=False,
    )
    observation.validate()
    return observation


def _validate_speech_report(value: object) -> None:
    """Validate renderer speech activity without accepting phoneme claims."""
    if not isinstance(value, Mapping) or value.get("phoneme_claimed") is not False:
        raise RendererReportIngressError("renderer_report_speech_state_invalid")
    status = value.get("status")
    if status == "not_requested":
        if set(value) != {"status", "phoneme_claimed"}:
            raise RendererReportIngressError("renderer_report_speech_state_invalid")
        return
    if status in {"speaking", "idle"}:
        if (set(value) != {"status", "mouth_shape", "mouth_weight", "timing_event",
                           "timing_source", "phoneme_claimed"}
                or not isinstance(value.get("mouth_shape"), str)
                or value.get("timing_source") != "governed_local_tts"
                or value.get("timing_event") not in {
                    "speech_started", "word_started", "speech_finished",
                    "speech_interrupted", "speech_failed"}
                or isinstance(value.get("mouth_weight"), bool)
                or not isinstance(value.get("mouth_weight"), (int, float))
                or not math.isfinite(float(value["mouth_weight"]))
                or not 0 <= float(value["mouth_weight"]) <= 1
                or ((status == "speaking") != (float(value["mouth_weight"]) > 0))):
            raise RendererReportIngressError("renderer_report_speech_state_invalid")
        return
    if (status == "unavailable"
            and set(value) == {"status", "reason", "timing_event", "phoneme_claimed"}
            and isinstance(value.get("reason"), str)
            and value.get("timing_event") in {
                "speech_started", "word_started", "speech_finished",
                "speech_interrupted", "speech_failed"}):
        return
    raise RendererReportIngressError("renderer_report_speech_state_invalid")


def renderer_report_world_state_record(report: Mapping[str, Any]) -> dict[str, Any]:
    """Project the report with the repository's existing non-authoritative owner."""
    observation = renderer_report_observation(report)
    records = EmbodimentEvidenceOwner([observation]).world_state_records()
    if len(records) != 1:
        raise RendererReportIngressError("renderer_report_projection_invalid")
    return cast(dict[str, Any], records[0])
