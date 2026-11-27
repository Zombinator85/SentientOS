"""Condition-worker operations bound to persistent branch objects.

This backend implements no-inference baseline and access preflight, score-free
receipt-index recovery, and read-only consolidation-snapshot preparation. A
pending consolidation intent can be reconciled only against an already
completed resident tick. It can rebuild that tick's bounded strategy
projection, but marks the consolidation reference and answer-exclusion audit
unverified and the projection ineligible for probe use. It does not
reauthenticate original invocation receipts or open peer stores. First-time
tick execution and delayed probes remain disabled.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

from .durable_learning_condition_worker_rpc import CONDITIONS
from .local_model_authority import digest_payload


_BASELINE_RUNTIME_ROOTS = frozenset({"state", "history", "session", "journal"})


def _safe_worker_reason(exc: Exception, fallback: str) -> str:
    """Return a bounded machine code without leaking exception details."""
    raw = exc.args[0] if isinstance(exc, ValueError) and exc.args else None
    return (raw if isinstance(raw, str)
        and re.fullmatch(r"[a-z0-9_]{1,128}", raw) else fallback)


def build_condition_worker_baseline_runtime_manifest(*, protocol: Mapping[str, Any],
        condition: str, appcontainer_sid: str, session_id: str,
        roots: Mapping[str, Path], peer_condition: str | None = None,
        peer_branch_id: str | None = None,
        peer_appcontainer_sid: str | None = None,
        peer_roots: Mapping[str, Path] | None = None) -> dict[str, Any]:
    """Pin the four branch roots for a no-inference worker launch descriptor."""
    from .durable_developmental_learning_experiment import (
        verify_durable_learning_protocol)
    from .windows_handle_custody import observe_private_directory_identity

    if (os.name != "nt" or not isinstance(protocol, Mapping)
            or condition not in CONDITIONS
            or not isinstance(appcontainer_sid, str)
            or re.fullmatch(r"S-1-15-2-(?:[0-9]+-)*[0-9]+",
                appcontainer_sid) is None
            or not isinstance(session_id, str) or not session_id
            or not isinstance(roots, Mapping)
            or set(roots) != _BASELINE_RUNTIME_ROOTS
            or ((peer_condition is None) != (peer_branch_id is None))
            or ((peer_condition is None) != (peer_roots is None))
            or ((peer_condition is None) != (peer_appcontainer_sid is None))
            or (peer_appcontainer_sid is not None and
                (not isinstance(peer_appcontainer_sid, str)
                    or re.fullmatch(r"S-1-15-2-(?:[0-9]+-)*[0-9]+",
                        peer_appcontainer_sid) is None))
            or (peer_roots is not None and
                (peer_condition not in CONDITIONS - {condition}
                    or not isinstance(peer_branch_id, str)
                    or not isinstance(peer_roots, Mapping)
                    or set(peer_roots) != _BASELINE_RUNTIME_ROOTS))):
        raise ValueError("durable_learning_worker_baseline_manifest_arguments_invalid")
    verification = verify_durable_learning_protocol(protocol)
    branch_ids = verification.get("condition_branch_ids")
    if not isinstance(branch_ids, Mapping) or not isinstance(
            branch_ids.get(condition), str):
        raise ValueError("durable_learning_worker_baseline_manifest_branch_invalid")
    root_rows: dict[str, dict[str, Any]] = {}
    peer_root_rows: dict[str, dict[str, Any]] = {}
    resolved: dict[str, Path] = {}
    def observe_rows(values: Mapping[str, Path],
            output: dict[str, dict[str, Any]], prefix: str,
            permitted_sid: str) -> None:
        for name in sorted(_BASELINE_RUNTIME_ROOTS):
            supplied = values[name]
            if not isinstance(supplied, Path) or not supplied.is_absolute():
                raise ValueError(
                    "durable_learning_worker_baseline_manifest_root_invalid")
            try:
                root = supplied.resolve(strict=True)
                identity = observe_private_directory_identity(root,
                    permitted_appcontainer_sid=permitted_sid)
            except (OSError, TypeError, ValueError) as exc:
                raise ValueError(
                    "durable_learning_worker_baseline_manifest_root_unavailable") from exc
            if not root.is_dir():
                raise ValueError(
                    "durable_learning_worker_baseline_manifest_root_invalid")
            resolved[prefix + name] = root
            output[name] = {"path": str(root),
                "identity": {"volume_serial": identity[0],
                    "file_id_hex": identity[1].hex()}}
    observe_rows(roots, root_rows, "own:", appcontainer_sid)
    if peer_roots is not None:
        peer_ids = verification.get("condition_branch_ids")
        if (not isinstance(peer_ids, Mapping)
                or peer_ids.get(peer_condition) != peer_branch_id):
            raise ValueError(
                "durable_learning_worker_baseline_manifest_peer_branch_invalid")
        observe_rows(peer_roots, peer_root_rows, "peer:",
            peer_appcontainer_sid)
    paths = list(resolved.values())
    for index, left in enumerate(paths):
        for right in paths[index + 1:]:
            if left == right or left in right.parents or right in left.parents:
                raise ValueError(
                    "durable_learning_worker_baseline_manifest_roots_overlap")
    identity_keys = [(row["identity"]["volume_serial"],
        row["identity"]["file_id_hex"])
        for row in (*root_rows.values(), *peer_root_rows.values())]
    if len(set(identity_keys)) != len(identity_keys):
        raise ValueError(
            "durable_learning_worker_baseline_manifest_root_identity_overlap")
    semantic = {"schema_version":
            ("sentientos.durable_learning_worker_baseline_runtime_manifest:v2"
                if peer_roots is not None else
                "sentientos.durable_learning_worker_baseline_runtime_manifest:v1"),
        "protocol_id": protocol["protocol_id"],
        "protocol_digest": protocol["protocol_digest"],
        "condition": condition,
        "branch_id": branch_ids[condition],
        "appcontainer_sid": appcontainer_sid,
        "session_id": session_id,
        "roots": root_rows,
        "authority": False}
    if peer_roots is not None:
        semantic.update({"peer_condition": peer_condition,
            "peer_branch_id": peer_branch_id,
            "peer_roots": peer_root_rows})
    return {**semantic, "manifest_digest": digest_payload(semantic)}


def build_condition_worker_baseline_runtime_manifest_pair(*, protocol: Mapping[str, Any],
        appcontainer_sids: Mapping[str, str],
        session_ids: Mapping[str, str],
        roots_by_condition: Mapping[str, Mapping[str, Path]]
        ) -> dict[str, dict[str, Any]]:
    """Build a reciprocal pair from the supervisor's two branch root maps."""
    from .durable_developmental_learning_experiment import (
        _CONDITIONS, verify_durable_learning_protocol)
    if (not isinstance(protocol, Mapping)
            or not isinstance(appcontainer_sids, Mapping)
            or set(appcontainer_sids) != set(_CONDITIONS)
            or not isinstance(session_ids, Mapping)
            or set(session_ids) != set(_CONDITIONS)
            or not isinstance(roots_by_condition, Mapping)
            or set(roots_by_condition) != set(_CONDITIONS)
            or any(not isinstance(appcontainer_sids[condition], str)
                or not isinstance(session_ids[condition], str)
                or not isinstance(roots_by_condition[condition], Mapping)
                for condition in _CONDITIONS)):
        raise ValueError(
            "durable_learning_worker_baseline_manifest_pair_arguments_invalid")
    verification = verify_durable_learning_protocol(protocol)
    branch_ids = verification.get("condition_branch_ids")
    if not isinstance(branch_ids, Mapping):
        raise ValueError(
            "durable_learning_worker_baseline_manifest_pair_protocol_invalid")
    pair: dict[str, dict[str, Any]] = {}
    for condition in _CONDITIONS:
        peer_condition = next(item for item in _CONDITIONS
            if item != condition)
        pair[condition] = build_condition_worker_baseline_runtime_manifest(
            protocol=protocol, condition=condition,
            appcontainer_sid=appcontainer_sids[condition],
            session_id=session_ids[condition],
            roots=roots_by_condition[condition],
            peer_condition=peer_condition,
            peer_branch_id=branch_ids.get(peer_condition),
            peer_appcontainer_sid=appcontainer_sids[peer_condition],
            peer_roots=roots_by_condition[peer_condition])
    for condition in _CONDITIONS:
        peer_condition = next(item for item in _CONDITIONS
            if item != condition)
        own = pair[condition]
        peer = pair[peer_condition]
        if (own["peer_branch_id"] != peer["branch_id"]
                or peer["peer_branch_id"] != own["branch_id"]
                or any(own["peer_roots"][name] != peer["roots"][name]
                    or peer["peer_roots"][name] != own["roots"][name]
                    for name in _BASELINE_RUNTIME_ROOTS)):
            raise ValueError(
                "durable_learning_worker_baseline_manifest_pair_changed_during_build")
    return pair


def verify_condition_worker_baseline_runtime_manifest(manifest: Mapping[str, Any],
        *, protocol: Mapping[str, Any], protocol_id: str,
        protocol_digest: str, condition: str, appcontainer_sid: str
        ) -> dict[str, Any]:
    """Verify the closed, protocol-bound baseline launch descriptor."""
    from .durable_developmental_learning_experiment import (
        verify_durable_learning_protocol)

    if (not isinstance(protocol, Mapping)
            or not isinstance(protocol_id, str)
            or not isinstance(protocol_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", protocol_digest) is None
            or condition not in CONDITIONS
            or not isinstance(appcontainer_sid, str)
            or re.fullmatch(r"S-1-15-2-(?:[0-9]+-)*[0-9]+",
                appcontainer_sid) is None):
        raise ValueError("durable_learning_worker_baseline_manifest_binding_invalid")
    fields = {"schema_version", "protocol_id", "protocol_digest",
        "condition", "branch_id", "appcontainer_sid", "session_id",
        "roots", "authority", "manifest_digest"}
    v2_fields = fields | {"peer_condition", "peer_branch_id", "peer_roots"}
    manifest_v2 = (isinstance(manifest, Mapping) and manifest.get(
        "schema_version") ==
            "sentientos.durable_learning_worker_baseline_runtime_manifest:v2")
    if manifest_v2:
        fields = v2_fields
    if (not isinstance(manifest, Mapping) or set(manifest) != fields
            or manifest.get("schema_version") not in {
                "sentientos.durable_learning_worker_baseline_runtime_manifest:v1",
                "sentientos.durable_learning_worker_baseline_runtime_manifest:v2"}
            or manifest.get("protocol_id") != protocol_id
            or manifest.get("protocol_digest") != protocol_digest
            or manifest.get("condition") != condition
            or not isinstance(manifest.get("appcontainer_sid"), str)
            or manifest["appcontainer_sid"].casefold() !=
                appcontainer_sid.casefold()
            or not isinstance(manifest.get("session_id"), str)
            or not manifest["session_id"]
            or manifest.get("authority") is not False
            or not isinstance(manifest.get("roots"), Mapping)
            or set(manifest["roots"]) != _BASELINE_RUNTIME_ROOTS):
        raise ValueError("durable_learning_worker_baseline_manifest_invalid")
    semantic = {key: value for key, value in manifest.items()
        if key != "manifest_digest"}
    if manifest.get("manifest_digest") != digest_payload(semantic):
        raise ValueError("durable_learning_worker_baseline_manifest_digest_invalid")
    verification = verify_durable_learning_protocol(protocol)
    if (protocol.get("protocol_id") != protocol_id
            or protocol.get("protocol_digest") != protocol_digest
            or verification.get("condition_branch_ids", {}).get(condition)
                != manifest.get("branch_id")):
        raise ValueError("durable_learning_worker_baseline_manifest_protocol_mismatch")
    all_roots = dict(manifest["roots"])
    if manifest_v2:
        peer_condition = manifest.get("peer_condition")
        peer_roots = manifest.get("peer_roots")
        if (peer_condition not in CONDITIONS - {condition}
                or not isinstance(manifest.get("peer_branch_id"), str)
                or not isinstance(peer_roots, Mapping)
                or set(peer_roots) != _BASELINE_RUNTIME_ROOTS
                or verification.get("condition_branch_ids", {}).get(
                    peer_condition) != manifest.get("peer_branch_id")):
            raise ValueError(
                "durable_learning_worker_baseline_manifest_peer_invalid")
        all_roots.update(peer_roots)
    identities: list[tuple[int, str]] = []
    for row in all_roots.values():
        if (not isinstance(row, Mapping) or set(row) != {"path", "identity"}
                or not isinstance(row.get("path"), str)
                or not Path(row["path"]).is_absolute()
                or not isinstance(row.get("identity"), Mapping)
                or set(row["identity"]) != {"volume_serial", "file_id_hex"}
                or type(row["identity"].get("volume_serial")) is not int
                or not 0 <= row["identity"]["volume_serial"] <=
                    0xFFFFFFFFFFFFFFFF
                or not isinstance(row["identity"].get("file_id_hex"), str)
                or re.fullmatch(r"[0-9a-f]{32}",
                    row["identity"]["file_id_hex"]) is None):
            raise ValueError("durable_learning_worker_baseline_manifest_root_invalid")
        identities.append((row["identity"]["volume_serial"],
            row["identity"]["file_id_hex"]))
    if len(set(identities)) != len(identities):
        raise ValueError(
            "durable_learning_worker_baseline_manifest_root_identity_overlap")
    if manifest_v2:
        paths = [Path(row["path"]) for row in all_roots.values()]
        for index, left in enumerate(paths):
            for right in paths[index + 1:]:
                if left == right or left in right.parents or right in left.parents:
                    raise ValueError(
                        "durable_learning_worker_baseline_manifest_roots_overlap")
    return json.loads(json.dumps(dict(manifest), ensure_ascii=False,
        allow_nan=False, sort_keys=True))


class _ReadOnlyConditionBaselineOwner:
    """Expose only reconciled history inventory for baseline inspection."""

    def __init__(self, *, state_root: Path, history_root: Path) -> None:
        from types import SimpleNamespace
        from .resident_developmental_writeback import DevelopmentalHistoryStore

        self.config = SimpleNamespace(state_root=state_root)
        self.writeback = SimpleNamespace(
            store=DevelopmentalHistoryStore(history_root))

    def ordinary_chat_developmental_history_state_snapshot(self
            ) -> dict[str, Any]:
        completed = self.writeback.store.inspect_completed_records()
        return self._snapshot_from_completed_records(completed)

    @staticmethod
    def _snapshot_from_completed_records(completed: Any) -> dict[str, Any]:
        refs = sorted(({
            "record_id": record.record_id,
            "record_digest": record.record_digest,
            "receipt_id": receipt.receipt_id,
            "receipt_digest": receipt.receipt_digest,
        } for record, receipt in completed), key=lambda row: row["record_id"])
        history_digest = digest_payload({
            "schema_version": "sentientos.resident_history_state_digest:v1",
            "records": refs, "authority": False})
        return {"schema_version":
                "sentientos.resident_history_state_snapshot:v1",
            "history_state_digest": "sha256:" + history_digest,
            "record_refs": refs, "authority": False}

    def ordinary_chat_developmental_history_probe_input_inventory(
            self) -> dict[str, Any]:
        """Derive v12's historical probe set from the verified read-only store."""
        from collections.abc import Sequence
        from .durable_developmental_learning_experiment import (
            MAX_HISTORY_PROBE_INPUTS)

        completed = self.writeback.store.inspect_completed_records()
        snapshot = self._snapshot_from_completed_records(completed)
        refs = snapshot["record_refs"]
        if len(completed) > 4096:
            raise ValueError("durable_learning_worker_history_inventory_over_bound")
        inputs: set[int] = set()
        pending: list[Any] = [record.candidate for record, _receipt in completed]
        while pending:
            value = pending.pop()
            if isinstance(value, Mapping):
                for key, item in value.items():
                    if key == "probe_input" and type(item) is int:
                        inputs.add(item)
                    elif (key == "probe_inputs"
                            and isinstance(item, Sequence)
                            and not isinstance(item, (str, bytes))):
                        inputs.update(candidate for candidate in item
                            if type(candidate) is int)
                    if isinstance(item, (Mapping, list, tuple)):
                        pending.append(item)
            elif isinstance(value, (list, tuple)):
                pending.extend(value)
        ordered = sorted(inputs)
        if len(ordered) > MAX_HISTORY_PROBE_INPUTS:
            raise ValueError("durable_learning_worker_history_inventory_over_bound")
        body = {"schema_version":
                "sentientos.resident_history_probe_input_inventory:v1",
            "history_state_digest": snapshot["history_state_digest"],
            "record_count": len(refs),
            "record_refs_digest": digest_payload({"record_refs": refs}),
            "probe_inputs": ordered,
            "probe_inputs_digest": digest_payload({"probe_inputs": ordered}),
            "owner_verified": True, "authority": False}
        return {**body, "inventory_digest": digest_payload(body)}

    def ordinary_chat_developmental_history_context(self, **_kwargs: Any
            ) -> Mapping[str, Any]:
        raise RuntimeError(
            "durable_learning_worker_history_projection_not_enabled")


class _ConditionWorkerReceiptOnlyInvoker:
    """Provide historical receipt verification while denying model calls."""

    def __init__(self, verifier: Any) -> None:
        self._verifier = verifier

    def build_request(self, **_kwargs: Any) -> Any:
        raise RuntimeError("durable_learning_worker_inference_not_enabled")

    def invoke(self, _request: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("durable_learning_worker_inference_not_enabled")

    def verify_persisted_invocation_receipt(self, receipt_id: str,
            receipt_digest: str, **expected: Any) -> Mapping[str, Any]:
        return self._verifier.verify_persisted_invocation_receipt(
            receipt_id, receipt_digest, **expected)


def _build_condition_worker_recovery_owner(*, state_root: Path,
        history_root: Path, invocation_receipt_verifier: Any) -> Any:
    """Construct the resident owner with execution disabled and custody reads enabled."""
    from .codex_task_authority_admission import (
        RESIDENT_DEVELOPMENTAL_WRITEBACK,
        RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION)
    from .resident_developmental_cognition import (
        ResidentDevelopmentalCognitionConfig,
        ResidentDevelopmentalCognitionOwner)
    from .resident_developmental_writeback import (
        ResidentDevelopmentalWritebackController)
    from .runtime_admission import (AdmissionLedger,
        RuntimeAdmissionAuthority, RuntimeAdmissionVerifier)

    if (not isinstance(state_root, Path) or not state_root.is_absolute()
            or not isinstance(history_root, Path) or not history_root.is_absolute()
            or not callable(getattr(invocation_receipt_verifier,
                "verify_persisted_invocation_receipt", None))):
        raise ValueError("durable_learning_recovery_owner_arguments_invalid")
    ledger = AdmissionLedger(state_root / "runtime_admissions.json")
    definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK:
        RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}
    admission_verifier = RuntimeAdmissionVerifier(definitions=definitions,
        ledger=ledger)
    writeback = ResidentDevelopmentalWritebackController(
        history_root=history_root, admission_verifier=admission_verifier,
        current_sequence=ledger.current_sequence)
    config = ResidentDevelopmentalCognitionConfig(
        history_root=history_root, state_root=state_root,
        allowed_source_kinds=(), max_selected_facts=1,
        comparison_enabled=False, enabled=False)
    return ResidentDevelopmentalCognitionOwner(config=config,
        writeback=writeback,
        admission_authority=RuntimeAdmissionAuthority(
            definitions=definitions, ledger=ledger),
        invoker=_ConditionWorkerReceiptOnlyInvoker(
            invocation_receipt_verifier),
        invocation_receipt_verifier=invocation_receipt_verifier,
        current_sequence=ledger.current_sequence)


class ConditionWorkerProfileStatePreflightBackend:
    """Minimal pre-acquisition worker for filesystem and registry observation."""

    def __init__(self, worker_context: Mapping[str, Any]) -> None:
        if (not isinstance(worker_context, Mapping)
                or worker_context.get("authority") is not False
                or not isinstance(worker_context.get("protocol_id"), str)
                or not isinstance(worker_context.get("protocol_digest"), str)
                or not isinstance(worker_context.get("condition"), str)
                or not isinstance(worker_context.get("appcontainer_sid"), str)
                or worker_context.get(
                    "access_probe_supervisor_verification_required") is not True
                or not isinstance(worker_context.get("access_probe_manifest"),
                    Mapping)
                or worker_context.get("access_probe_manifest_digest") !=
                    worker_context["access_probe_manifest"].get(
                        "manifest_digest")):
            raise ValueError(
                "durable_learning_access_probe_worker_context_invalid")
        from .windows_appcontainer_access import (
            verify_condition_worker_access_probe_manifest)
        self._protocol_id = worker_context["protocol_id"]
        self._protocol_digest = worker_context["protocol_digest"]
        self._condition = worker_context["condition"]
        self._manifest = verify_condition_worker_access_probe_manifest(
            worker_context["access_probe_manifest"],
            protocol_id=self._protocol_id, condition=self._condition,
            appcontainer_sid=worker_context["appcontainer_sid"])

    def probe_access_matrix(self,
            request: Mapping[str, Any]) -> dict[str, Any]:
        if (not isinstance(request, Mapping)
                or request.get("operation") != "probe_access_matrix"
                or request.get("protocol_id") != self._protocol_id
                or request.get("protocol_digest") != self._protocol_digest
                or request.get("condition") != self._condition):
            return {"status": "rejected", "result": {
                "reason_code": "worker_access_probe_binding_mismatch",
                "authority": False}}
        payload = request.get("payload")
        if (not isinstance(payload, Mapping)
                or payload.get("probe_manifest_digest") !=
                    self._manifest["manifest_digest"]):
            return {"status": "rejected", "result": {
                "reason_code": "worker_access_probe_manifest_mismatch",
                "authority": False}}
        from .windows_appcontainer_access import (
            probe_condition_worker_file_access)
        try:
            report = probe_condition_worker_file_access(self._manifest)
        except (OSError, TypeError, ValueError) as exc:
            return {"status": "rejected", "result": {
                "reason_code": getattr(exc, "args", [
                    "worker_access_probe_failed"])[0],
                "filesystem_isolation_verified": False,
                "authority": False}}
        return {"status": "completed", "result": report}

    def inventory_profile_registry(self,
            request: Mapping[str, Any]) -> dict[str, Any]:
        """Return a bounded registry inventory from this SID-bound worker."""
        payload = request.get("payload") if isinstance(request, Mapping) else None
        if (not isinstance(request, Mapping)
                or request.get("operation") != "inventory_profile_registry"
                or request.get("protocol_id") != self._protocol_id
                or request.get("protocol_digest") != self._protocol_digest
                or request.get("condition") != self._condition
                or not isinstance(payload, Mapping)
                or payload.get("probe_manifest_digest") !=
                    self._manifest["manifest_digest"]
                or payload.get("expected_appcontainer_sid") !=
                    self._manifest["appcontainer_sid"]):
            return {"status": "rejected", "result": {
                "reason_code": "worker_registry_inventory_binding_mismatch",
                "authority": False}}
        from .windows_appcontainer_registry import (
            inventory_current_appcontainer_registry)
        try:
            report = inventory_current_appcontainer_registry(
                expected_appcontainer_sid=self._manifest["appcontainer_sid"])
        except (OSError, TypeError, ValueError) as exc:
            return {"status": "rejected", "result": {
                "reason_code": getattr(exc, "args", [
                    "worker_registry_inventory_failed"])[0],
                "registry_state_accounted": False,
                "authority": False}}
        return {"status": "completed", "result": report}


# Preserve the earlier import name for callers that construct the file-probe
# backend directly; the backend now also owns the paired profile observation.
ConditionWorkerAccessProbeOnlyBackend = ConditionWorkerProfileStatePreflightBackend


def run_condition_worker_access_probe_from_environment(*, timeout_ms: int = 30_000
        ) -> dict[str, Any]:
    """Bootstrap a pipe worker with no branch, receipts, model, or GPU path."""
    from .durable_learning_condition_worker_rpc import (
        ConditionWorkerRPCDispatcher)
    from .windows_appcontainer_pipe import (
        bootstrap_condition_worker_pipe_from_environment,
        serve_condition_worker_access_probe_once)

    connection, context = bootstrap_condition_worker_pipe_from_environment(
        timeout_ms=timeout_ms)
    try:
        backend = ConditionWorkerProfileStatePreflightBackend(context)
        dispatcher = ConditionWorkerRPCDispatcher(
            protocol_id=context["protocol_id"],
            protocol_digest=context["protocol_digest"],
            condition=context["condition"],
            process_start_nonce=context["process_start_nonce"],
            backend=backend,
            allowed_operations=frozenset({"probe_access_matrix",
                "inventory_profile_registry"}))
        return serve_condition_worker_access_probe_once(connection, dispatcher,
            process_start_nonce=context["process_start_nonce"],
            timeout_ms=timeout_ms)
    except Exception:
        connection.close()
        raise


def run_condition_worker_baseline_from_environment(*, timeout_ms: int = 30_000
        ) -> dict[str, Any]:
    """Bootstrap one manifest-bound branch and serve one no-inference baseline."""
    protocol_text = os.environ.get(
        "SENTIENTOS_WORKER_BASELINE_PROTOCOL_JSON")
    manifest_text = os.environ.get(
        "SENTIENTOS_WORKER_BASELINE_RUNTIME_MANIFEST_JSON")
    if (not isinstance(protocol_text, str) or not protocol_text
            or not isinstance(manifest_text, str) or not manifest_text
            or len(protocol_text.encode("utf-8", errors="strict")) > 24_000
            or len(manifest_text.encode("utf-8", errors="strict")) > 8192):
        raise ValueError("durable_learning_worker_baseline_environment_invalid")
    from .durable_learning_condition_worker_rpc import (
        ConditionWorkerRPCDispatcher, _reject_duplicate_json_keys)
    from .durable_developmental_learning_experiment import (
        verify_durable_learning_protocol)
    try:
        protocol = json.loads(protocol_text,
            object_pairs_hook=_reject_duplicate_json_keys)
        manifest = json.loads(manifest_text,
            object_pairs_hook=_reject_duplicate_json_keys)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            "durable_learning_worker_baseline_environment_json_invalid") from exc
    if not isinstance(protocol, dict) or not isinstance(manifest, dict):
        raise ValueError("durable_learning_worker_baseline_environment_shape_invalid")
    verify_durable_learning_protocol(protocol)
    from .windows_appcontainer_pipe import (
        bootstrap_condition_worker_pipe_from_environment,
        serve_condition_worker_baseline_once)
    connection, context = bootstrap_condition_worker_pipe_from_environment(
        timeout_ms=timeout_ms, protocol=protocol)
    try:
        if (protocol.get("protocol_id") != context["protocol_id"]
                or protocol.get("protocol_digest") !=
                    context["protocol_digest"]):
            raise ValueError(
                "durable_learning_worker_baseline_protocol_binding_mismatch")
        backend = (
            DurableLearningConditionWorkerBackend.
            from_worker_baseline_runtime_manifest(protocol=protocol,
                manifest=manifest, worker_context=context))
        dispatcher = ConditionWorkerRPCDispatcher(
            protocol_id=context["protocol_id"],
            protocol_digest=context["protocol_digest"],
            condition=context["condition"],
            process_start_nonce=context["process_start_nonce"],
            backend=backend,
            allowed_operations=frozenset({"inspect_baseline"}))
        return serve_condition_worker_baseline_once(connection, dispatcher,
            process_start_nonce=context["process_start_nonce"],
            timeout_ms=timeout_ms)
    except Exception:
        connection.close()
        raise


def run_condition_worker_recovery_from_environment(*,
        timeout_ms: int = 30_000) -> dict[str, Any]:
    """Serve bounded persisted-cognition recovery with all inference disabled."""
    protocol_text = os.environ.get(
        "SENTIENTOS_WORKER_BASELINE_PROTOCOL_JSON")
    manifest_text = os.environ.get(
        "SENTIENTOS_WORKER_BASELINE_RUNTIME_MANIFEST_JSON")
    if (not isinstance(protocol_text, str) or not protocol_text
            or not isinstance(manifest_text, str) or not manifest_text
            or len(protocol_text.encode("utf-8", errors="strict")) > 24_000
            or len(manifest_text.encode("utf-8", errors="strict")) > 8192):
        raise ValueError("durable_learning_worker_recovery_environment_invalid")
    from .durable_learning_condition_worker_rpc import (
        ConditionWorkerRPCDispatcher, _reject_duplicate_json_keys)
    from .durable_developmental_learning_experiment import (
        verify_durable_learning_protocol)
    try:
        protocol = json.loads(protocol_text,
            object_pairs_hook=_reject_duplicate_json_keys)
        manifest = json.loads(manifest_text,
            object_pairs_hook=_reject_duplicate_json_keys)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(
            "durable_learning_worker_recovery_environment_json_invalid") from exc
    if not isinstance(protocol, dict) or not isinstance(manifest, dict):
        raise ValueError(
            "durable_learning_worker_recovery_environment_shape_invalid")
    verify_durable_learning_protocol(protocol)
    from .windows_appcontainer_pipe import (
        bootstrap_condition_worker_pipe_from_environment,
        serve_condition_worker_rpc)
    connection, context = bootstrap_condition_worker_pipe_from_environment(
        timeout_ms=timeout_ms, protocol=protocol)
    try:
        if (protocol.get("protocol_id") != context["protocol_id"]
                or protocol.get("protocol_digest") !=
                    context["protocol_digest"]
                or "invocation_receipt_verifier" not in context
                or "condition_receipt_bundle" not in context):
            raise ValueError(
                "durable_learning_worker_recovery_bootstrap_incomplete")
        backend = (
            DurableLearningConditionWorkerBackend.
            from_worker_recovery_runtime_manifest(protocol=protocol,
                manifest=manifest, worker_context=context))
        dispatcher = ConditionWorkerRPCDispatcher(
            protocol_id=context["protocol_id"],
            protocol_digest=context["protocol_digest"],
            condition=context["condition"],
            process_start_nonce=context["process_start_nonce"],
            backend=backend,
            allowed_operations=frozenset({"inspect_baseline",
                "recover_acquisition_receipts",
                "prepare_consolidation_snapshot", "consolidate_branch",
                "reconstruct_strategy_projection",
                "reconstruct_strategy_projection_v2"}))
        served = serve_condition_worker_rpc(connection, dispatcher,
            max_requests=5, timeout_ms=timeout_ms)
        return {"schema_version":
                "sentientos.durable_learning_condition_recovery_worker_once:v1",
            "requests_processed": served["requests_processed"],
            "stopped_after_ambiguous_backend_result":
                served["stopped_after_ambiguous_backend_result"],
            "authority": False}
    finally:
        connection.close()


class DurableLearningConditionWorkerBackend:
    """Expose bounded evidence for one already-created branch.

    Receipt recovery is limited to indexing entries in the verified staged
    bundle supplied by the worker bootstrap. The operation does not open peer
    stores, replay calls, or reauthenticate original receipts. Consolidation
    may only reconcile an already committed owner tick into its worker journal.
    """

    def __init__(self, *, protocol: Mapping[str, Any],
            protocol_id: str, protocol_digest: str,
            condition: str, branch: Any,
            condition_receipt_bundle: Mapping[str, Any] | None = None,
            condition_receipt_store_artifact_digest: str | None = None,
            operation_journal: Any = None,
            access_probe_manifest: Mapping[str, Any] | None = None) -> None:
        from .durable_developmental_learning_experiment import (
            DurableLearningConditionBranch,
            verify_durable_learning_protocol,
        )

        if (not isinstance(protocol, Mapping)
                or not isinstance(protocol_id, str)
                or not isinstance(protocol_digest, str)
                or condition not in CONDITIONS
                or not isinstance(branch, DurableLearningConditionBranch)):
            raise ValueError("durable_learning_worker_backend_binding_invalid")
        try:
            # Detach the sealed protocol so later supervisor-side mutation
            # cannot change the worker's protocol binding.
            frozen_protocol = json.loads(json.dumps(dict(protocol),
                ensure_ascii=False, allow_nan=False, sort_keys=True))
        except (TypeError, ValueError, RecursionError) as exc:
            raise ValueError(
                "durable_learning_worker_backend_protocol_invalid") from exc
        verification = verify_durable_learning_protocol(frozen_protocol)
        expected_branch_ids = verification.get("condition_branch_ids")
        if (frozen_protocol.get("protocol_id") != protocol_id
                or frozen_protocol.get("protocol_digest") != protocol_digest
                or not isinstance(expected_branch_ids, Mapping)
                or expected_branch_ids.get(condition) != branch.branch_id):
            raise ValueError("durable_learning_worker_backend_binding_mismatch")
        self._protocol = frozen_protocol
        self._condition = condition
        self._branch = branch
        if operation_journal is not None:
            from .durable_learning_condition_worker_journal import (
                ConditionWorkerOperationJournal)
            binding = getattr(operation_journal, "binding", None)
            if (not isinstance(operation_journal,
                    ConditionWorkerOperationJournal)
                    or not isinstance(binding, Mapping)
                    or binding.get("protocol_id") != protocol_id
                    or binding.get("protocol_digest") != protocol_digest
                    or binding.get("condition") != condition
                    or binding.get("branch_id") != branch.branch_id
                    or binding.get("authority") is not False):
                raise ValueError(
                    "durable_learning_worker_backend_journal_binding_invalid")
        self._operation_journal = operation_journal
        self._access_probe_manifest = access_probe_manifest
        self._baseline_runtime_manifest: Mapping[str, Any] | None = None
        self._receipt_entries: dict[str, Mapping[str, Any]] | None = None
        self._recovered_receipt_entries: dict[str, Mapping[str, Any]] = {}
        self._receipt_reference_set_verification: dict[str, Any] | None = None
        if (condition_receipt_store_artifact_digest is not None
                and (condition_receipt_bundle is None
                    or not isinstance(condition_receipt_store_artifact_digest, str)
                    or re.fullmatch(r"[0-9a-f]{64}",
                        condition_receipt_store_artifact_digest) is None)):
            raise ValueError(
                "durable_learning_worker_backend_receipt_store_digest_invalid")
        self._receipt_store_artifact_digest = (
            condition_receipt_store_artifact_digest)
        self._prepared_consolidation_snapshot: Any = None
        self._prepared_consolidation_evidence: dict[str, Any] | None = None
        if condition_receipt_bundle is not None:
            from .durable_learning_condition_receipts import (
                verify_condition_scoped_acquisition_receipt_bundle)
            try:
                detached_bundle = json.loads(json.dumps(
                    dict(condition_receipt_bundle), ensure_ascii=False,
                    allow_nan=False, sort_keys=True))
                verification = verify_condition_scoped_acquisition_receipt_bundle(
                    detached_bundle, protocol=frozen_protocol,
                    condition=condition)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    "durable_learning_worker_backend_receipt_bundle_invalid") from exc
            self._receipt_entries = {entry["task_digest"]: dict(entry)
                for entry in detached_bundle["task_receipts"]}
            self._receipt_bundle_digest = verification["bundle_digest"]
        else:
            self._receipt_bundle_digest = None

    @classmethod
    def from_worker_bootstrap_context(cls, *, protocol: Mapping[str, Any],
            protocol_id: str, protocol_digest: str, condition: str,
            branch: Any, worker_context: Mapping[str, Any],
            operation_journal: Any = None
            ) -> "DurableLearningConditionWorkerBackend":
        """Bind worker startup context and an optional staged receipt bundle.

        Receipt artifacts are optional before acquisition. When any receipt
        bundle field is supplied, the complete existing bundle verification
        contract still applies.
        """
        if not isinstance(protocol, Mapping) or not isinstance(
                worker_context, Mapping):
            raise ValueError(
                "durable_learning_worker_bootstrap_context_invalid")
        bundle = worker_context.get("condition_receipt_bundle")
        artifact = worker_context.get("condition_receipt_store_artifact")
        verification = worker_context.get(
            "condition_receipt_bundle_verification")
        artifact_digest = worker_context.get(
            "condition_receipt_store_artifact_digest")
        access_manifest = worker_context.get("access_probe_manifest")
        branch_id = getattr(branch, "branch_id", None)
        if (not isinstance(worker_context, Mapping)
                or worker_context.get("protocol_id") != protocol_id
                or worker_context.get("condition") != condition
                or worker_context.get("authority") is not False
                or not isinstance(worker_context.get("appcontainer_sid"), str)
                or not isinstance(branch_id, str)):
            raise ValueError(
                "durable_learning_worker_bootstrap_context_invalid")
        receipt_state = (bundle, artifact, verification, artifact_digest)
        receipt_custody = worker_context.get(
            "condition_receipt_bundle_custody_authenticated")
        if any(value is not None for value in receipt_state):
            artifact_semantic = ({key: value for key, value in artifact.items()
                if key != "artifact_digest"}
                if isinstance(artifact, Mapping) else {})
            if (not isinstance(bundle, Mapping)
                    or not isinstance(artifact, Mapping)
                    or artifact.get("schema_version") !=
                    "sentientos.durable_learning_condition_receipt_bundle_store:v1"
                or artifact.get("protocol_id") != protocol_id
                or artifact.get("protocol_digest") != protocol_digest
                or artifact.get("condition") != condition
                or not isinstance(branch_id, str)
                or artifact.get("branch_id") != branch_id
                or artifact.get("appcontainer_sid") !=
                    worker_context.get("appcontainer_sid")
                or artifact.get("bundle_digest") != bundle.get("bundle_digest")
                or artifact.get("access_policy") != "condition_receipt_read"
                or artifact.get("effective_access_verified") is not False
                or artifact.get("peer_denial_verified") is not False
                or artifact.get("bundle_receipt_authentication_verified") is not False
                or artifact.get("authority") is not False
                or artifact.get("artifact_digest") != digest_payload(
                    artifact_semantic)
                or artifact.get("artifact_digest") != artifact_digest
                or not isinstance(verification, Mapping)
                or verification.get("schema_version") not in (
                    "sentientos.durable_learning_condition_receipt_bundle_verification:v1",
                    "sentientos.durable_learning_condition_receipt_bundle_verification:v2")
                or verification.get("protocol_id") != protocol_id
                or verification.get("condition") != condition
                or verification.get("bundle_digest") !=
                    bundle.get("bundle_digest")
                or verification.get("closed_shape_verified") is not True
                or verification.get("protocol_condition_task_binding_verified") is not True
                or verification.get("bundle_integrity_verified") is not True
                or verification.get("retained_state_refs_verified") is not (
                    verification.get("schema_version") ==
                    "sentientos.durable_learning_condition_receipt_bundle_verification:v2")
                or verification.get("source_invocation_receipts_reverified") is not False
                or verification.get("custody_authenticated") is not False
                or worker_context.get(
                    "condition_receipt_bundle_custody_authenticated") is not False
                or not isinstance(artifact_digest, str)
                or re.fullmatch(r"[0-9a-f]{64}", artifact_digest) is None):
                raise ValueError(
                    "durable_learning_worker_bootstrap_receipt_context_invalid")
        elif (receipt_custody is not None
                and receipt_custody is not False):
            raise ValueError(
                "durable_learning_worker_bootstrap_receipt_context_invalid")
        if access_manifest is not None:
            from .windows_appcontainer_access import (
                verify_condition_worker_access_probe_manifest)
            access_manifest = verify_condition_worker_access_probe_manifest(
                access_manifest, protocol_id=protocol_id,
                condition=condition,
                appcontainer_sid=worker_context["appcontainer_sid"])
        return cls(protocol=protocol, protocol_id=protocol_id,
            protocol_digest=protocol_digest, condition=condition,
            branch=branch, condition_receipt_bundle=bundle,
            condition_receipt_store_artifact_digest=artifact_digest,
            operation_journal=operation_journal,
            access_probe_manifest=access_manifest)

    @classmethod
    def from_worker_local_runtime(cls, *, protocol: Mapping[str, Any],
            protocol_id: str, protocol_digest: str, condition: str,
            owner: Any,
            conversation_session_store: Any, session_id: str,
            operation_journal_root: Path,
            operation_journal_root_identity: tuple[int, bytes],
            worker_context: Mapping[str, Any],
            invocation_receipt_verifier: Any = None
            ) -> "DurableLearningConditionWorkerBackend":
        """Construct one condition branch from objects created inside a worker.

        This worker-side factory accepts one resident owner and one session
        store. It derives the retained-state resolver from the local experience
        source and does not accept a serving inference controller, sibling
        branch, or callable from the supervisor.
        """
        from .durable_developmental_learning_experiment import (
            ConversationSessionDurableLearningContext,
            DurableLearningConditionBranch,
            ResidentDevelopmentalLearningExperienceSource,
            verify_durable_learning_protocol,
        )

        if (not isinstance(worker_context, Mapping)
                or worker_context.get("protocol_id") != protocol_id
                or worker_context.get("condition") != condition
                or not isinstance(protocol, Mapping)
                or not isinstance(session_id, str) or not session_id):
            raise ValueError("durable_learning_worker_local_runtime_invalid")
        if invocation_receipt_verifier is None:
            invocation_receipt_verifier = worker_context.get(
                "invocation_receipt_verifier")
        if invocation_receipt_verifier is not None:
            from .durable_learning_invocation_receipts import (
                ConditionInvocationReceiptVerifier)
            if (not isinstance(invocation_receipt_verifier,
                    ConditionInvocationReceiptVerifier)
                    or not hasattr(owner, "invocation_receipt_verifier")):
                raise ValueError(
                    "durable_learning_worker_invocation_receipt_verifier_invalid")
            owner.invocation_receipt_verifier = invocation_receipt_verifier
        verification = verify_durable_learning_protocol(protocol)
        branch_ids = verification.get("condition_branch_ids")
        if not isinstance(branch_ids, Mapping) or not isinstance(
                branch_ids.get(condition), str):
            raise ValueError("durable_learning_worker_local_branch_unbound")
        experience_source = ResidentDevelopmentalLearningExperienceSource(owner)
        context = ConversationSessionDurableLearningContext(
            conversation_session_store=conversation_session_store,
            session_id=session_id)

        def inference_unavailable(**_kwargs: Any) -> Mapping[str, Any]:
            raise RuntimeError("durable_learning_worker_inference_not_enabled")

        branch = DurableLearningConditionBranch(
            branch_id=branch_ids[condition],
            experience_source=experience_source,
            retained_state_snapshot_resolver=(
                experience_source.current_history_state_snapshot),
            invocation_executor=inference_unavailable,
            conversation_context=context,
            conversation_session_store=conversation_session_store,
            session_id=session_id)
        from .durable_learning_condition_worker_journal import (
            ConditionWorkerOperationJournal)
        operation_journal = ConditionWorkerOperationJournal(
            root=operation_journal_root,
            expected_root_identity=operation_journal_root_identity,
            appcontainer_sid=worker_context.get("appcontainer_sid"),
            protocol_id=protocol_id, protocol_digest=protocol_digest,
            condition=condition, branch_id=branch_ids[condition])
        return cls.from_worker_bootstrap_context(protocol=protocol,
            protocol_id=protocol_id, protocol_digest=protocol_digest,
            condition=condition, branch=branch,
            worker_context=worker_context,
            operation_journal=operation_journal)

    @classmethod
    def from_worker_readonly_baseline_stores(cls, *,
            protocol: Mapping[str, Any], protocol_id: str,
            protocol_digest: str, condition: str,
            state_root: Path, history_root: Path,
            conversation_session_root: Path, session_id: str,
            operation_journal_root: Path,
            expected_root_identities: Mapping[str, tuple[int, bytes]],
            worker_context: Mapping[str, Any]
            ) -> "DurableLearningConditionWorkerBackend":
        """Build a baseline-only owner from verified read-only persistent stores.

        This factory exposes completed history inventory and an existing empty
        session. It creates no cognition model, admission writer, serving
        controller, or developmental writeback path.
        """
        if os.name != "nt":
            raise ValueError("durable_learning_worker_baseline_windows_only")
        from .conversation_session import ConversationSessionStore
        from .windows_handle_custody import observe_private_directory_identity

        roots = {"state": state_root, "history": history_root,
            "session": conversation_session_root,
            "journal": operation_journal_root}
        if (not isinstance(worker_context, Mapping)
                or worker_context.get("protocol_id") != protocol_id
                or worker_context.get("protocol_digest") != protocol_digest
                or worker_context.get("condition") != condition
                or worker_context.get("authority") is not False
                or not isinstance(expected_root_identities, Mapping)
                or set(expected_root_identities) != set(roots)
                or not isinstance(session_id, str) or not session_id):
            raise ValueError(
                "durable_learning_worker_baseline_store_context_invalid")
        sid = worker_context.get("appcontainer_sid")
        if not isinstance(sid, str):
            raise ValueError(
                "durable_learning_worker_baseline_appcontainer_invalid")
        normalized: dict[str, Path] = {}
        identities: dict[str, tuple[int, bytes]] = {}
        for name, supplied in roots.items():
            if not isinstance(supplied, Path) or not supplied.is_absolute():
                raise ValueError(
                    "durable_learning_worker_baseline_store_root_invalid")
            try:
                root = supplied.resolve(strict=True)
                identity = observe_private_directory_identity(root,
                    permitted_appcontainer_sid=sid)
            except (OSError, TypeError, ValueError) as exc:
                raise ValueError(
                    "durable_learning_worker_baseline_store_root_unavailable") from exc
            expected = expected_root_identities[name]
            if (not isinstance(expected, tuple) or len(expected) != 2
                    or type(expected[0]) is not int
                    or not isinstance(expected[1], bytes)
                    or identity != expected):
                raise ValueError(
                    "durable_learning_worker_baseline_store_identity_mismatch")
            normalized[name] = root
            identities[name] = identity
        paths = list(normalized.values())
        for index, left in enumerate(paths):
            for right in paths[index + 1:]:
                try:
                    same_object = left.samefile(right)
                except OSError as exc:
                    raise ValueError(
                        "durable_learning_worker_baseline_store_identity_unavailable") from exc
                if same_object or cls._overlap(left, right):
                    raise ValueError(
                        "durable_learning_worker_baseline_store_roots_overlap")
        owner = _ReadOnlyConditionBaselineOwner(
            state_root=normalized["state"],
            history_root=normalized["history"])
        sessions = ConversationSessionStore(normalized["session"])
        return cls.from_worker_local_runtime(protocol=protocol,
            protocol_id=protocol_id, protocol_digest=protocol_digest,
            condition=condition, owner=owner,
            conversation_session_store=sessions, session_id=session_id,
            operation_journal_root=normalized["journal"],
            operation_journal_root_identity=identities["journal"],
            worker_context=worker_context)

    @classmethod
    def from_worker_baseline_runtime_manifest(cls, *,
            protocol: Mapping[str, Any], manifest: Mapping[str, Any],
            worker_context: Mapping[str, Any]
            ) -> "DurableLearningConditionWorkerBackend":
        """Construct the no-inference backend from a validated closed manifest."""
        if not isinstance(worker_context, Mapping):
            raise ValueError(
                "durable_learning_worker_baseline_manifest_context_invalid")
        protocol_id = worker_context.get("protocol_id")
        protocol_digest = worker_context.get("protocol_digest")
        condition = worker_context.get("condition")
        sid = worker_context.get("appcontainer_sid")
        checked = verify_condition_worker_baseline_runtime_manifest(manifest,
            protocol=protocol, protocol_id=protocol_id,
            protocol_digest=protocol_digest, condition=condition,
            appcontainer_sid=sid)
        roots = {name: Path(row["path"])
            for name, row in checked["roots"].items()}
        identities = {name: (row["identity"]["volume_serial"],
            bytes.fromhex(row["identity"]["file_id_hex"]))
            for name, row in checked["roots"].items()}
        context = {**dict(worker_context), "authority": False}
        backend = cls.from_worker_readonly_baseline_stores(protocol=protocol,
            protocol_id=protocol_id, protocol_digest=protocol_digest,
            condition=condition, state_root=roots["state"],
            history_root=roots["history"],
            conversation_session_root=roots["session"],
            session_id=checked["session_id"],
            operation_journal_root=roots["journal"],
            expected_root_identities=identities, worker_context=context)
        backend._baseline_runtime_manifest = checked
        return backend

    @classmethod
    def from_worker_recovery_runtime_manifest(cls, *,
            protocol: Mapping[str, Any], manifest: Mapping[str, Any],
            worker_context: Mapping[str, Any]
            ) -> "DurableLearningConditionWorkerBackend":
        """Construct a resident owner for persisted-tick recovery without inference."""
        if not isinstance(protocol, Mapping) or not isinstance(
                worker_context, Mapping):
            raise ValueError(
                "durable_learning_worker_recovery_manifest_context_invalid")
        protocol_id = worker_context.get("protocol_id")
        protocol_digest = worker_context.get("protocol_digest")
        condition = worker_context.get("condition")
        sid = worker_context.get("appcontainer_sid")
        verifier = worker_context.get("invocation_receipt_verifier")
        from .durable_learning_invocation_receipts import (
            ConditionInvocationReceiptVerifier)
        if not isinstance(verifier, ConditionInvocationReceiptVerifier):
            raise ValueError(
                "durable_learning_worker_recovery_receipt_verifier_missing")
        bundle = worker_context.get("condition_receipt_bundle")
        bundle_verification = worker_context.get(
            "condition_receipt_bundle_verification")
        try:
            receipt_store_artifact = worker_context.get(
                "invocation_receipt_store_artifact")
            receipt_store_artifact_digest = worker_context.get(
                "invocation_receipt_store_artifact_digest")
            receipt_store_verification = verifier.verify_store_artifact(
                artifact=receipt_store_artifact, protocol=protocol,
                condition=worker_context.get("condition"))
            if (receipt_store_verification.get("store_index_reloaded") is not True
                    or receipt_store_verification.get(
                        "verifier_allowlist_matches_store") is not True
                    or receipt_store_verification.get("artifact_digest") !=
                        receipt_store_artifact_digest):
                raise ValueError(
                    "durable_learning_worker_recovery_receipt_store_invalid")
            from .durable_learning_condition_receipts import (
                verify_condition_scoped_acquisition_receipt_bundle)
            checked_bundle_verification = (
                verify_condition_scoped_acquisition_receipt_bundle(
                    bundle, protocol=protocol,
                    condition=worker_context.get("condition")))
            if (not isinstance(bundle_verification, Mapping)
                    or dict(bundle_verification) != checked_bundle_verification
                    or not isinstance(bundle, Mapping)):
                raise ValueError(
                    "durable_learning_worker_recovery_bundle_binding_invalid")
            receipt_refs = [{"receipt_id": entry["invocation_receipt_id"],
                "receipt_digest": entry["invocation_receipt_digest"]}
                for entry in bundle["task_receipts"]]
            receipt_ref_verification = verifier.verify_receipt_refs(
                receipt_refs)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                "durable_learning_worker_recovery_receipt_set_mismatch") from exc
        if (receipt_ref_verification.get("exact_store_set_match") is not True
                or receipt_ref_verification.get("receipt_count") != len(
                    protocol.get("acquisition_task_digests", []))):
            raise ValueError(
                "durable_learning_worker_recovery_receipt_set_mismatch")
        backend_receipt_set_verification = {
            "receipt_count": receipt_ref_verification["receipt_count"],
            "receipt_ref_set_digest": receipt_ref_verification[
                "receipt_ref_set_digest"],
            "exact_store_set_match": True,
            "store_index_reloaded": True,
            "verifier_allowlist_matches_store": True}
        checked = verify_condition_worker_baseline_runtime_manifest(manifest,
            protocol=protocol, protocol_id=protocol_id,
            protocol_digest=protocol_digest, condition=condition,
            appcontainer_sid=sid)
        roots = {name: Path(row["path"])
            for name, row in checked["roots"].items()}
        identities = {name: (row["identity"]["volume_serial"],
            bytes.fromhex(row["identity"]["file_id_hex"]))
            for name, row in checked["roots"].items()}
        from .windows_handle_custody import observe_private_directory_identity
        for name, root in roots.items():
            if observe_private_directory_identity(root,
                    permitted_appcontainer_sid=sid) != identities[name]:
                raise ValueError(
                    "durable_learning_worker_recovery_root_identity_mismatch")
        paths = list(roots.values())
        for index, left in enumerate(paths):
            for right in paths[index + 1:]:
                if cls._overlap(left, right):
                    raise ValueError(
                        "durable_learning_worker_recovery_roots_overlap")
        from .conversation_session import ConversationSessionStore
        owner = _build_condition_worker_recovery_owner(
            state_root=roots["state"], history_root=roots["history"],
            invocation_receipt_verifier=verifier)
        owner._worker_state_root_identity = identities["state"]
        sessions = ConversationSessionStore(roots["session"])
        context = {**dict(worker_context), "authority": False}
        backend = cls.from_worker_local_runtime(protocol=protocol,
            protocol_id=protocol_id, protocol_digest=protocol_digest,
            condition=condition, owner=owner,
            conversation_session_store=sessions,
            session_id=checked["session_id"],
            operation_journal_root=roots["journal"],
            operation_journal_root_identity=identities["journal"],
            worker_context=context,
            invocation_receipt_verifier=verifier)
        backend._baseline_runtime_manifest = checked
        backend._receipt_reference_set_verification = (
            backend_receipt_set_verification)
        return backend

    @property
    def recovered_receipt_entries(self) -> dict[str, Mapping[str, Any]]:
        """Return the last explicitly recovered, score-free receipt index."""
        return json.loads(json.dumps(self._recovered_receipt_entries,
            ensure_ascii=False, allow_nan=False, sort_keys=True))

    def _bound(self, request: Mapping[str, Any], operation: str) -> bool:
        return (request.get("protocol_id") == self._protocol["protocol_id"]
            and request.get("protocol_digest") ==
                self._protocol["protocol_digest"]
            and request.get("condition") == self._condition
            and request.get("operation") == operation)

    @staticmethod
    def _root_identity(value: Any) -> tuple[Path, str]:
        path = Path(value).resolve(strict=True)
        info = path.stat()
        if not path.is_dir():
            raise ValueError("durable_learning_worker_branch_root_invalid")
        return path, digest_payload({"resolved_root": str(path),
            "device": int(info.st_dev), "inode": int(info.st_ino)})

    @staticmethod
    def _overlap(left: Path, right: Path) -> bool:
        try:
            left.relative_to(right)
            return True
        except ValueError:
            pass
        try:
            right.relative_to(left)
            return True
        except ValueError:
            return False

    def inspect_baseline(self, request: Mapping[str, Any]) -> dict[str, Any]:
        if not self._bound(request, "inspect_baseline"):
            return {"status": "rejected", "result": {
                "reason_code": "worker_protocol_condition_binding_mismatch"}}
        from .durable_developmental_learning_experiment import (
            _resolve_history_state_snapshot,
        )

        source = self._branch.experience_source.current_history_state_snapshot()
        retained = _resolve_history_state_snapshot(
            self._branch.retained_state_snapshot_resolver)
        history_probe_inventory = None
        history_probe_inventory_matches_protocol = None
        if self._protocol.get("schema_version") == (
                "sentientos.durable_developmental_learning_protocol:v12"):
            from .durable_developmental_learning_experiment import (
                _verify_history_probe_input_inventory)
            history_probe_inventory = _verify_history_probe_input_inventory(
                self._branch.experience_source.history_probe_input_inventory())
            history_probe_inventory_matches_protocol = (
                history_probe_inventory.get("history_state_digest") ==
                    source.get("history_state_digest")
                and history_probe_inventory.get("history_state_digest") ==
                    self._protocol.get("baseline_history_state_digest")
                and history_probe_inventory.get("inventory_digest") ==
                    self._protocol.get(
                        "historical_probe_input_inventory_digest")
                and history_probe_inventory.get("probe_inputs") ==
                    self._protocol.get("historical_probe_inputs"))
        owner = self._branch.experience_source._owner
        config = getattr(owner, "config", None)
        writeback = getattr(owner, "writeback", None)
        writeback_store = getattr(writeback, "store", None)
        session_store = self._branch.conversation_session_store
        roots = [self._root_identity(getattr(config, "state_root", None)),
            self._root_identity(getattr(writeback_store, "root", None)),
            self._root_identity(getattr(session_store, "root", None))]
        if self._operation_journal is not None:
            roots.append(self._root_identity(
                self._operation_journal.binding["root"]))
        session = session_store.load(self._branch.session_id)
        turns = session.get("turns") if isinstance(session, Mapping) else None
        root_paths = [row[0] for row in roots]
        roots_disjoint = len({row[1] for row in roots}) == len(roots)
        if roots_disjoint:
            for index, left in enumerate(root_paths):
                for right in root_paths[index + 1:]:
                    try:
                        same_object = left.samefile(right)
                    except OSError:
                        roots_disjoint = False
                        continue
                    if same_object or self._overlap(left, right):
                        roots_disjoint = False
        session_baseline = (isinstance(session, Mapping)
            and session.get("session_id") == self._branch.session_id
            and session.get("lifecycle_state") == "active"
            and isinstance(turns, list) and not turns)
        if self._protocol.get("schema_version") == (
                "sentientos.durable_developmental_learning_protocol:v10"):
            from .conversation_session import MAX_SESSION_LIST_ENTRIES
            try:
                stored_sessions = session_store.list_recent(
                    limit=MAX_SESSION_LIST_ENTRIES)
            except (OSError, TypeError, ValueError):
                stored_sessions = None
            session_baseline = (session_baseline
                and isinstance(stored_sessions, list)
                and len(stored_sessions) == 1
                and isinstance(stored_sessions[0], Mapping)
                and stored_sessions[0].get("session_id") ==
                    self._branch.session_id)
        history_baseline = (source == retained
            and source.get("history_state_digest") ==
                self._protocol.get("baseline_history_state_digest"))
        journal_inventory = None
        journal_empty = False
        branch_root_access_verified: bool | None = None
        if self._operation_journal is not None:
            try:
                journal_inventory = (
                    self._operation_journal.inspect_baseline_inventory())
                journal_empty = journal_inventory.get("empty") is True
            except Exception:
                journal_inventory = None
        evidence = {"schema_version":
                ("sentientos.durable_learning_worker_baseline_inventory:v4"
                    if history_probe_inventory is not None else
                 "sentientos.durable_learning_worker_baseline_inventory:v3"
                    if isinstance(self._baseline_runtime_manifest, Mapping)
                    and self._baseline_runtime_manifest.get("schema_version") ==
                        "sentientos.durable_learning_worker_baseline_runtime_manifest:v2"
                    else "sentientos.durable_learning_worker_baseline_inventory:v2"),
            "protocol_id": self._protocol["protocol_id"],
            "protocol_digest": self._protocol["protocol_digest"],
            "condition": self._condition,
            "branch_id": self._branch.branch_id,
            "history_state_digest": source.get("history_state_digest"),
            "history_snapshot_matches_retained_state": source == retained,
            "history_matches_protocol_baseline": history_baseline,
            "active_empty_session_verified": session_baseline,
            "branch_roots_disjoint": roots_disjoint,
            "branch_root_identity_digests": [row[1] for row in roots],
            "operation_journal_inventory": journal_inventory,
            "operation_journal_empty_verified": journal_empty,
            "authority": False}
        if history_probe_inventory is not None:
            evidence["history_probe_input_inventory"] = history_probe_inventory
            evidence["history_probe_inventory_matches_protocol"] = (
                history_probe_inventory_matches_protocol)
        if (isinstance(self._baseline_runtime_manifest, Mapping)
                and self._baseline_runtime_manifest.get("schema_version") ==
                    "sentientos.durable_learning_worker_baseline_runtime_manifest:v2"):
            from .windows_appcontainer_access import (
                probe_condition_worker_baseline_branch_roots)
            root_access = probe_condition_worker_baseline_branch_roots(
                self._baseline_runtime_manifest)
            evidence["branch_root_access_matrix"] = root_access
            branch_root_access_verified = root_access.get(
                "branch_root_access_matrix_verified") is True
            evidence["branch_root_access_matrix_verified"] = (
                branch_root_access_verified)
        inventory_digest = digest_payload(evidence)
        expected = request.get("payload", {}).get(
            "expected_baseline_inventory_digest")
        if ((expected is not None and expected != inventory_digest)
                or not (history_baseline
                and session_baseline and roots_disjoint and journal_empty
                and history_probe_inventory_matches_protocol is not False)):
            return {"status": "rejected", "result": evidence}
        if branch_root_access_verified is False:
            return {"status": "rejected", "result": evidence}
        return {"status": "completed", "result": evidence}

    def probe_access_matrix(self,
            request: Mapping[str, Any]) -> dict[str, Any]:
        """Run the no-inference own/peer/scorer sentinel probe in this worker."""
        if not self._bound(request, "probe_access_matrix"):
            return {"status": "rejected", "result": {
                "reason_code": "worker_protocol_condition_binding_mismatch"}}
        manifest = self._access_probe_manifest
        expected_digest = (request.get("payload", {}).get(
            "probe_manifest_digest") if isinstance(request.get("payload"),
                Mapping) else None)
        if (not isinstance(manifest, Mapping)
                or expected_digest != manifest.get("manifest_digest")):
            return {"status": "rejected", "result": {
                "reason_code": "worker_access_probe_manifest_unavailable",
                "filesystem_isolation_verified": False,
                "authority": False}}
        from .windows_appcontainer_access import (
            probe_condition_worker_file_access)
        try:
            report = probe_condition_worker_file_access(manifest)
        except (OSError, TypeError, ValueError) as exc:
            return {"status": "rejected", "result": {
                "reason_code": getattr(exc, "args", [
                    "worker_access_probe_failed"])[0],
                "filesystem_isolation_verified": False,
                "authority": False}}
        return {"status": "completed", "result": report}

    def recover_acquisition_receipts(self,
            request: Mapping[str, Any]) -> dict[str, Any]:
        if not self._bound(request, "recover_acquisition_receipts"):
            return {"status": "rejected", "result": {
                "reason_code": "worker_protocol_condition_binding_mismatch"}}
        if self._receipt_entries is None:
            return {"status": "rejected", "result": {
                "reason_code":
                    "condition_scoped_acquisition_receipt_bundle_unavailable",
                "peer_artifacts_opened": False,
                "automatic_replay_performed": False,
                "authority": False}}
        payload = request.get("payload")
        task_digests = payload.get("task_digests") if isinstance(
            payload, Mapping) else None
        expected = self._protocol.get("acquisition_task_digests")
        if (not isinstance(task_digests, list)
                or not isinstance(expected, list)
                or any(task not in expected for task in task_digests)
                or any(task not in self._receipt_entries
                    for task in task_digests)):
            return {"status": "rejected", "result": {
                "reason_code": "condition_scoped_receipt_task_set_invalid",
                "peer_artifacts_opened": False,
                "automatic_replay_performed": False,
                "authority": False}}
        selected = {task: dict(self._receipt_entries[task])
            for task in task_digests}
        self._recovered_receipt_entries = selected
        receipt_set_verification = self._receipt_reference_set_verification
        if (not isinstance(receipt_set_verification, Mapping)
                or receipt_set_verification.get("exact_store_set_match") is not True
                or receipt_set_verification.get("store_index_reloaded") is not True
                or receipt_set_verification.get(
                    "verifier_allowlist_matches_store") is not True):
            return {"status": "rejected", "result": {
                "reason_code": "condition_scoped_receipt_store_verification_unavailable",
                "peer_artifacts_opened": False,
                "automatic_replay_performed": False,
                "authority": False}}
        index_digest = digest_payload({"protocol_id": self._protocol[
            "protocol_id"], "condition": self._condition,
            "branch_id": self._branch.branch_id,
            "bundle_digest": self._receipt_bundle_digest,
            "store_artifact_digest": self._receipt_store_artifact_digest,
            "task_receipts": [selected[task] for task in task_digests]})
        return {"status": "completed", "result": {
            "receipt_index_digest": index_digest,
            "receipt_count": len(selected),
            "bundle_digest": self._receipt_bundle_digest,
            "store_artifact_digest": self._receipt_store_artifact_digest,
            "store_artifact_digest_bound": (
                self._receipt_store_artifact_digest is not None),
            "receipt_ref_count": receipt_set_verification["receipt_count"],
            "receipt_ref_set_digest": receipt_set_verification[
                "receipt_ref_set_digest"],
            "exact_store_set_match": True,
            "store_index_reloaded": True,
            "verifier_allowlist_matches_store": True,
            "source_invocation_receipts_reverified": False,
            "peer_artifacts_opened": False,
            "automatic_replay_performed": False,
            "authority": False}}

    def _build_consolidation_snapshot(self) -> tuple[Any, dict[str, Any]]:
        """Build a local score-free snapshot from recovered receipts/transcript.

        This is read-only. It does not run the resident tick or write history.
        """
        from .durable_developmental_learning_experiment import (
            MAX_RETAINED_STATE_SNAPSHOT_BYTES,
            _durable_learning_target_experience_refs,
            _resolve_history_state_snapshot,
            _validate_outcome_exposure,
        )
        from .world_state_board import (
            WorldStateBoardBuilder, record_digest, validate_snapshot,
        )

        tasks = self._protocol.get("acquisition_task_digests")
        if (not isinstance(tasks, list)
                or set(self._recovered_receipt_entries) != set(tasks)
                or len(self._recovered_receipt_entries) != len(tasks)):
            raise ValueError(
                "durable_learning_worker_receipt_recovery_incomplete")
        branch = self._branch
        source_state = branch.experience_source.current_history_state_snapshot()
        retained_state = _resolve_history_state_snapshot(
            branch.retained_state_snapshot_resolver)
        if (source_state != retained_state
                or source_state.get("history_state_digest") !=
                    self._protocol.get("baseline_history_state_digest")):
            raise ValueError(
                "durable_learning_worker_consolidation_baseline_changed")
        session = branch.conversation_session_store.load(branch.session_id)
        turns = session.get("turns") if isinstance(session, Mapping) else None
        if (not isinstance(session, Mapping)
                or session.get("session_id") != branch.session_id
                or session.get("lifecycle_state") != "active"
                or not isinstance(turns, list)):
            raise ValueError(
                "durable_learning_worker_consolidation_session_invalid")

        records: list[dict[str, Any]] = []
        expected_session_turn_ids: list[str] = []
        for task_digest in tasks:
            entry = self._recovered_receipt_entries[task_digest]
            _validate_outcome_exposure(self._protocol,
                phase="acquisition", condition=self._condition,
                retained_state_digest=entry.get("retained_state_digest"),
                available=entry.get("available_experience_digests"),
                feedback=entry.get("preceding_feedback_digests"))
            context = branch.conversation_context.receipt_context(
                protocol=self._protocol, phase="acquisition",
                condition=self._condition, task_digest=task_digest)
            if (not isinstance(context, Mapping)
                    or context.get("session_id") != branch.session_id):
                raise ValueError(
                    "durable_learning_worker_consolidation_session_mismatch")
            users = [turn for turn in turns if isinstance(turn, Mapping)
                and turn.get("turn_id") == context.get("user_turn_id")
                and turn.get("role") == "user"]
            if len(users) != 1:
                raise ValueError(
                    "durable_learning_worker_consolidation_user_turn_invalid")
            user = users[0]
            prompt, user_linkage = user.get("text"), user.get("linkage")
            if (not isinstance(prompt, str)
                    or digest_payload({"prompt": prompt}) !=
                        entry.get("prompt_digest")
                    or not isinstance(user_linkage, Mapping)
                    or user_linkage.get("client_request_id_digest") !=
                        context.get("client_request_id_digest")):
                raise ValueError(
                    "durable_learning_worker_consolidation_prompt_binding_invalid")
            assistants = [turn for turn in turns if isinstance(turn, Mapping)
                and turn.get("role") == "assistant"
                and isinstance(turn.get("linkage"), Mapping)
                and turn["linkage"].get("source_user_turn_id") == user.get("turn_id")
                and turn["linkage"].get("invocation_receipt_id") ==
                    entry.get("invocation_receipt_id")
                and turn["linkage"].get("invocation_receipt_digest") ==
                    entry.get("invocation_receipt_digest")
                and turn["linkage"].get("durable_learning_protocol_id") ==
                    self._protocol["protocol_id"]
                and turn["linkage"].get("durable_learning_phase") == "acquisition"
                and turn["linkage"].get("durable_learning_condition") ==
                    self._condition
                and turn["linkage"].get("durable_learning_task_digest") ==
                    task_digest]
            if len(assistants) != 1:
                raise ValueError(
                    "durable_learning_worker_consolidation_assistant_turn_invalid")
            assistant = assistants[0]
            expected_session_turn_ids.extend((user.get("turn_id"),
                assistant.get("turn_id")))
            output = assistant.get("text")
            if (not isinstance(output, str) or not output
                    or digest_payload({"output": output}) !=
                        entry.get("output_digest")):
                raise ValueError(
                    "durable_learning_worker_consolidation_output_binding_invalid")
            common = {"protocol_id": self._protocol["protocol_id"],
                "condition": self._condition,
                "condition_branch_id": branch.branch_id,
                "phase": "acquisition", "task_digest": task_digest,
                "outcome_id": entry["outcome_id"],
                "outcome_digest": entry["outcome_digest"],
                "outcome_verification_digest": entry[
                    "outcome_verification_digest"],
                "invocation_attempt_id": entry["invocation_attempt_id"],
                "invocation_receipt_id": entry["invocation_receipt_id"],
                "invocation_receipt_digest": entry[
                    "invocation_receipt_digest"],
                "receipt_store_artifact_digest":
                    self._receipt_store_artifact_digest,
                "retained_state_digest": entry["retained_state_digest"],
                "retained_state_record_refs": ([dict(ref) for ref in
                    entry["retained_state_record_refs"]]
                    if isinstance(entry.get("retained_state_record_refs"), list)
                    else None),
                "available_experience_digests": list(
                    entry["available_experience_digests"]),
                "preceding_feedback_digests": list(
                    entry["preceding_feedback_digests"]),
                "prompt_digest": entry["prompt_digest"],
                "output_digest": entry["output_digest"],
                "current_truth": False, "authority": False}
            records.extend([
                {"source_kind": "developmental_experiment_input",
                    "source_id": (f"durable-learning:{self._protocol['protocol_id']}:"
                        f"{self._condition}:{task_digest}:prompt"),
                    "schema_version":
                        "sentientos.durable_learning_acquisition_turn:v1",
                    "subject_id": f"durable-learning-task:{task_digest}",
                    "subject_kind": "durable_learning_acquisition_turn",
                    "stage": "history", "disposition": "recorded",
                    "evidence_strength": "receipt_bound_prompt",
                    "effect_claimed": False, "effect_proven": False,
                    "payload": {**common, "role": "user",
                        "turn_id": user["turn_id"],
                        "turn_text_digest": digest_payload({"text": prompt}),
                        "text": prompt}},
                {"source_kind": "local_model_output",
                    "source_id": (f"durable-learning:{self._protocol['protocol_id']}:"
                        f"{self._condition}:{task_digest}:response"),
                    "schema_version":
                        "sentientos.durable_learning_acquisition_turn:v1",
                    "subject_id": f"durable-learning-task:{task_digest}",
                    "subject_kind": "durable_learning_acquisition_turn",
                    "stage": "history", "disposition": "recorded",
                    "evidence_strength": "receipt_bound_model_output",
                    "effect_claimed": False, "effect_proven": False,
                    "payload": {**common, "role": "assistant",
                        "turn_id": assistant["turn_id"],
                        "turn_text_digest": digest_payload({"text": output}),
                        "text": output}},
            ])
        session_turn_ids = [turn.get("turn_id") for turn in turns
            if isinstance(turn, Mapping)]
        if (len(turns) != 2 * len(tasks)
                or len(session_turn_ids) != len(turns)
                or any(not isinstance(turn_id, str) or not turn_id
                    for turn_id in session_turn_ids)
                or len(set(session_turn_ids)) != len(session_turn_ids)
                or expected_session_turn_ids != session_turn_ids):
            raise ValueError(
                "durable_learning_worker_consolidation_transcript_scope_invalid")
        for record in records:
            record["digest"] = record_digest(record)
        snapshot = WorldStateBoardBuilder(
            max_source_count=max(1, len(records)),
            max_artifact_size=MAX_RETAINED_STATE_SNAPSHOT_BYTES).build(
                records, manifest_id=(f"durable-learning-"
                    f"{self._protocol['protocol_id']}-{self._condition}"))
        expected_payload_digests = sorted(digest_payload(record["payload"])
            for record in records if isinstance(record.get("payload"), Mapping))
        observed_payload_digests = sorted(digest_payload(dict(fact.payload))
            for fact in snapshot.facts if isinstance(fact.payload, Mapping))
        if (not validate_snapshot(snapshot).valid or snapshot.degraded
                or len(snapshot.sources) != len(records)
                or len(snapshot.facts) != len(records)
                or len(expected_payload_digests) != len(records)
                or observed_payload_digests != expected_payload_digests):
            raise ValueError(
                "durable_learning_worker_consolidation_snapshot_invalid")
        baseline_record_refs = [{"record_id": ref["record_id"],
            "record_digest": ref["record_digest"]}
            for ref in source_state["record_refs"]]
        source_fact_ids = [fact.fact_id for fact in snapshot.facts]
        allowed_history_record_refs = (
            _durable_learning_target_experience_refs(
                protocol=self._protocol, branch=branch)
            if self._condition == "relevant_experience_available" else [])
        if (len(baseline_record_refs) > 512 or len(source_fact_ids) > 1024
                or len(allowed_history_record_refs) > 512):
            raise ValueError(
                "durable_learning_worker_consolidation_recovery_context_over_bound")
        evidence = {"protocol_id": self._protocol["protocol_id"],
            "protocol_digest": self._protocol["protocol_digest"],
            "condition": self._condition, "branch_id": branch.branch_id,
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_digest": snapshot.digest,
            "source_count": len(records),
            "receipt_bundle_digest": self._receipt_bundle_digest,
            "receipt_store_artifact_digest":
                self._receipt_store_artifact_digest,
            "observed_baseline_history_state_digest":
                source_state["history_state_digest"],
            "baseline_record_refs": baseline_record_refs,
            "source_fact_ids": source_fact_ids,
            "allowed_history_record_refs": allowed_history_record_refs,
            "withhold_developmental_history": (
                self._condition == "relevant_experience_withheld"),
            "baseline_state_matches_protocol": True,
            "score_free_snapshot_payload_readback_verified": True,
            "score_material_included": False,
            "source_invocation_receipts_reverified": False,
            "custody_authenticated": False,
            "developmental_writeback_performed": False,
            "authority": False}
        self._prepared_consolidation_snapshot = snapshot
        self._prepared_consolidation_evidence = evidence
        return snapshot, dict(evidence)

    def prepare_consolidation_snapshot(self,
            request: Mapping[str, Any]) -> dict[str, Any]:
        """Expose receipt-digest-bound, read-only snapshot preparation."""
        if not self._bound(request, "prepare_consolidation_snapshot"):
            return {"status": "rejected", "result": {
                "reason_code": "worker_protocol_condition_binding_mismatch"}}
        payload = request.get("payload")
        supplied = (payload.get("acquisition_receipt_digests")
            if isinstance(payload, Mapping) else None)
        tasks = self._protocol.get("acquisition_task_digests")
        if (self._receipt_entries is None or not isinstance(supplied, list)
                or not isinstance(tasks, list)
                or set(self._recovered_receipt_entries) != set(tasks)
                or len(self._recovered_receipt_entries) != len(tasks)):
            return {"status": "rejected", "result": {
                "reason_code": "condition_scoped_receipt_recovery_incomplete",
                "developmental_writeback_performed": False,
                "authority": False}}
        expected = [self._recovered_receipt_entries[task][
            "invocation_receipt_digest"] for task in tasks]
        if supplied != expected:
            return {"status": "rejected", "result": {
                "reason_code": "condition_scoped_receipt_digest_sequence_mismatch",
                "developmental_writeback_performed": False,
                "authority": False}}
        try:
            _snapshot, evidence = self._build_consolidation_snapshot()
        except Exception as exc:
            return {"status": "rejected", "result": {
                "reason_code": _safe_worker_reason(exc,
                    "consolidation_snapshot_rejected"),
                "developmental_writeback_performed": False,
                "authority": False}}
        return {"status": "completed", "result": evidence}

    @staticmethod
    def _operation_not_enabled(_request: Mapping[str, Any]
            ) -> dict[str, Any]:
        return {"status": "rejected", "result": {
            "reason_code": "worker_owned_operation_runtime_not_enabled"}}

    def reconstruct_strategy_projection(self,
            request: Mapping[str, Any]) -> dict[str, Any]:
        """Legacy request shape; supplied external references remain unverified."""
        return self._reconstruct_strategy_projection(request,
            operation="reconstruct_strategy_projection",
            include_external_references=True)

    def reconstruct_strategy_projection_v2(self,
            request: Mapping[str, Any]) -> dict[str, Any]:
        """Rebuild a projection without accepting unverified external references."""
        return self._reconstruct_strategy_projection(request,
            operation="reconstruct_strategy_projection_v2",
            include_external_references=False)

    def _reconstruct_strategy_projection(self,
            request: Mapping[str, Any], *, operation: str,
            include_external_references: bool) -> dict[str, Any]:
        """Rebuild a non-consumable projection from a completed owner tick."""
        if not self._bound(request, operation):
            return {"status": "rejected", "result": {
                "reason_code": "worker_protocol_condition_binding_mismatch",
                "consolidation_receipt_reference_verified": False,
                "answer_exclusion_audit_verified": False,
                "probe_use_eligible": False,
                "supervisor_recovery_evidence_eligible": False,
                "authority": False}}
        payload = request.get("payload")
        contract = self._protocol.get("condition_contract")
        external_reference_fields = (("consolidation_receipt_digest",
            "answer_exclusion_audit_digest")
            if include_external_references else ())
        required_digest_fields = (*external_reference_fields,
            "strategy_projection_policy_digest")
        if (not isinstance(payload, Mapping)
                or not isinstance(contract, Mapping)
                or any(not isinstance(payload.get(key), str)
                    or re.fullmatch(r"[0-9a-f]{64}",
                        payload.get(key, "")) is None
                    for key in required_digest_fields)
                or payload.get("strategy_projection_policy_digest") !=
                    contract.get("strategy_projection_policy_digest")):
            return {"status": "rejected", "result": {
                "reason_code": "worker_strategy_projection_request_invalid",
                "consolidation_receipt_reference_verified": False,
                "answer_exclusion_audit_verified": False,
                "probe_use_eligible": False,
                "supervisor_recovery_evidence_eligible": False,
                "authority": False}}
        try:
            from .durable_developmental_learning_experiment import (
                build_durable_learning_strategy_projection,
                verify_durable_learning_strategy_projection,
            )
            snapshot, snapshot_evidence = self._build_consolidation_snapshot()
            recovery_payload = {
                "snapshot_digest": snapshot.digest,
                "baseline_history_state_digest": self._protocol[
                    "baseline_history_state_digest"],
                "source_fact_ids": list(snapshot_evidence[
                    "source_fact_ids"]),
                "baseline_record_refs": list(snapshot_evidence[
                    "baseline_record_refs"]),
                "withhold_developmental_history": (
                    self._condition == "relevant_experience_withheld"),
            }
            completion = self._reconcile_completed_owner_tick(
                payload=recovery_payload,
                snapshot_evidence=snapshot_evidence)
            projection = build_durable_learning_strategy_projection(
                protocol=self._protocol, condition=self._condition,
                branch=self._branch, tick_id=completion["tick_id"],
                snapshot_id=completion["snapshot_id"],
                snapshot_digest=completion["snapshot_digest"],
                source_fact_ids=completion["source_fact_ids"],
                writeback_record_ref=completion["new_writeback_ref"],
                writeback_receipt_ref=completion[
                    "new_writeback_receipt_ref"])
            if projection is not None:
                verify_durable_learning_strategy_projection(
                    self._protocol, condition=self._condition,
                    branch_id=self._branch.branch_id, branch=self._branch,
                    projection=projection)
        except Exception as exc:
            result = {
                "reason_code": _safe_worker_reason(exc,
                    "worker_strategy_projection_reconstruction_failed"),
                "consolidation_receipt_reference_verified": False,
                "answer_exclusion_audit_verified": False,
                "probe_use_eligible": False,
                "supervisor_recovery_evidence_eligible": False,
                "authority": False}
            if include_external_references:
                result.update({key: payload[key]
                    for key in external_reference_fields})
            return {"status": "rejected", "result": result}
        result = {
            "schema_version":
                ("sentientos.durable_learning_worker_strategy_projection:v1"
                    if include_external_references else
                    "sentientos.durable_learning_worker_strategy_projection:v2"),
            "protocol_id": self._protocol["protocol_id"],
            "protocol_digest": self._protocol["protocol_digest"],
            "condition": self._condition,
            "branch_id": self._branch.branch_id,
            "strategy_projection_policy_digest": payload[
                "strategy_projection_policy_digest"],
            "strategy_projection": projection,
            "projection_digest": (projection.get("projection_digest")
                if isinstance(projection, Mapping) else None),
            "owner_tick_reloaded": True,
            "consolidation_receipt_reference_verified": False,
            "answer_exclusion_audit_verified": False,
            "answer_example_exclusion_verified": False,
            "probe_use_eligible": False,
            "supervisor_recovery_evidence_eligible": False,
            "adoption_performed": False,
            "authority": False}
        if include_external_references:
            result.update({key: payload[key]
                for key in external_reference_fields})
        else:
            result["recovered_completion"] = completion
            result["recovered_completion_digest"] = digest_payload(completion)
        return {"status": "completed", "result": result}

    def consolidate_branch(self,
            request: Mapping[str, Any]) -> dict[str, Any]:
        """Recover a completed tick; refuse ambiguous or new mutations."""
        if not self._bound(request, "consolidate_branch"):
            return {"status": "rejected", "result": {
                "reason_code": "worker_protocol_condition_binding_mismatch"}}
        if self._operation_journal is None:
            return {"status": "rejected", "result": {
                "reason_code": "worker_operation_journal_unavailable",
                "developmental_writeback_performed": False,
                "authority": False}}
        try:
            recovery = self._operation_journal.inspect(request)
        except Exception as exc:
            return {"status": "rejected", "result": {
                "reason_code": _safe_worker_reason(exc,
                    "worker_operation_journal_invalid"),
                "developmental_writeback_performed": False,
                "authority": False}}
        if recovery.get("state") == "completed":
            payload = request.get("payload")
            try:
                tasks = self._protocol.get("acquisition_task_digests")
                if (not isinstance(tasks, list)
                        or set(self._recovered_receipt_entries) != set(tasks)
                        or len(self._recovered_receipt_entries) != len(tasks)):
                    raise ValueError(
                        "condition_scoped_receipt_recovery_incomplete")
                snapshot, snapshot_evidence = (
                    self._build_consolidation_snapshot())
                stored_completion = recovery["receipt"]["result"]
                reloaded_completion = self._reconcile_completed_owner_tick(
                    payload=payload, snapshot_evidence=snapshot_evidence)
                if digest_payload(stored_completion) != digest_payload(
                        reloaded_completion):
                    raise ValueError(
                        "worker_consolidation_completion_owner_state_mismatch")
                completion = self._verify_reconciled_owner_tick_completion(
                    stored_completion, payload=payload,
                    expected_snapshot_id=snapshot.snapshot_id,
                    expected_snapshot_digest=snapshot.digest)
            except Exception as exc:
                return {"status": "rejected", "result": {
                    "reason_code": _safe_worker_reason(exc,
                        "worker_consolidation_completion_invalid"),
                    "completion_receipt_digest": recovery["receipt"].get(
                        "receipt_digest"),
                    "automatic_replay_performed": False,
                    "authority": False}}
            return {"status": "completed", "result": {
                "recovered_completion": completion,
                "completion_receipt_digest": recovery["receipt"][
                    "receipt_digest"],
                "recovery_from_durable_journal": True,
                "automatic_replay_performed": False,
                "authority": False}}
        if recovery.get("state") == "scope_conflict":
            return {"status": "rejected", "result": {
                "reason_code": "worker_consolidation_scope_already_started",
                "automatic_replay_performed": False,
                "developmental_writeback_performed": False,
                "authority": False}}
        payload = request.get("payload")
        contract = self._protocol.get("condition_contract")
        tasks = self._protocol.get("acquisition_task_digests")
        if (not isinstance(payload, Mapping)
                or not isinstance(contract, Mapping)
                or not isinstance(tasks, list)
                or not tasks
                or set(self._recovered_receipt_entries) != set(tasks)
                or payload.get("acquisition_receipt_digests") != [
                    self._recovered_receipt_entries[task].get(
                        "invocation_receipt_digest") for task in tasks]
                or payload.get("consolidation_policy_digest") !=
                    contract.get("consolidation_policy_digest")
                or payload.get("baseline_history_state_digest") !=
                    self._protocol.get("baseline_history_state_digest")):
            return {"status": "rejected", "result": {
                "reason_code": "worker_consolidation_evidence_binding_invalid",
                "developmental_writeback_performed": False,
                "authority": False}}
        try:
            _snapshot, snapshot_evidence = self._build_consolidation_snapshot()
        except Exception as exc:
            return {"status": "rejected", "result": {
                "reason_code": _safe_worker_reason(exc,
                    "worker_consolidation_snapshot_unavailable"),
                "developmental_writeback_performed": False,
                "authority": False}}
        if payload.get("snapshot_digest") != snapshot_evidence.get(
                "snapshot_digest"):
            return {"status": "rejected", "result": {
                "reason_code": "worker_consolidation_snapshot_digest_mismatch",
                "expected_snapshot_digest": snapshot_evidence.get(
                    "snapshot_digest"),
                "developmental_writeback_performed": False,
                "authority": False}}
        recovery_in_progress = recovery.get("state") == "ambiguous"
        owner_tick_preexisting = False
        if recovery.get("state") == "new":
            owner = self._branch.experience_source._owner
            tick_status_fn = getattr(owner,
                "developmental_tick_status_readonly", None)
            if not callable(tick_status_fn):
                return {"status": "rejected", "result": {
                    "reason_code":
                        "worker_consolidation_owner_readonly_tick_status_unavailable",
                    "automatic_replay_performed": False,
                    "authority": False}}
            tick_id = (f"durable-learning-consolidation-"
                f"{self._protocol['protocol_id']}-{self._condition}")
            try:
                existing_tick = tick_status_fn(tick_id=tick_id)
            except Exception:
                return {"status": "rejected", "result": {
                    "reason_code":
                        "worker_consolidation_owner_readonly_tick_status_unavailable",
                    "automatic_replay_performed": False,
                    "authority": False}}
            existing_status = (existing_tick.get("status")
                if isinstance(existing_tick, Mapping) else None)
            existing_row = (existing_tick.get("tick")
                if isinstance(existing_tick, Mapping) else None)
            tick_status_valid = (
                isinstance(existing_tick, Mapping)
                and set(existing_tick) == {"status", "tick", "authority"}
                and existing_tick.get("authority") is False
                and existing_status in {
                    "not_started", "completed", "interrupted"}
                and ((existing_status == "not_started"
                        and existing_row is None)
                    or (existing_status in {"completed", "interrupted"}
                        and isinstance(existing_row, Mapping)
                        and existing_row.get("tick_id") == tick_id)))
            if not tick_status_valid:
                return {"status": "rejected", "result": {
                    "reason_code":
                        "worker_consolidation_owner_readonly_tick_status_invalid",
                    "automatic_replay_performed": False,
                    "authority": False}}
            if existing_status == "completed":
                recovery_in_progress = True
                owner_tick_preexisting = True
            elif existing_status == "interrupted":
                return {"status": "rejected", "result": {
                    "reason_code":
                        "worker_consolidation_owner_tick_interrupted",
                    "automatic_replay_performed": False,
                    "authority": False}}
        evidence_pairs = [
            ("source_fact_ids", "source_fact_ids"),
            ("allowed_history_record_refs", "allowed_history_record_refs"),
            ("withhold_developmental_history",
                "withhold_developmental_history"),
        ]
        if not recovery_in_progress:
            evidence_pairs.extend([
                ("baseline_history_state_digest",
                    "observed_baseline_history_state_digest"),
                ("baseline_record_refs", "baseline_record_refs"),
            ])
        if any(payload.get(field) != snapshot_evidence.get(evidence_field)
                for field, evidence_field in evidence_pairs):
            return {"status": "rejected", "result": {
                "reason_code": "worker_consolidation_recovery_context_mismatch",
                "developmental_writeback_performed": False,
                "authority": False}}
        if recovery_in_progress:
            try:
                completion = self._reconcile_completed_owner_tick(
                    payload=payload,
                    snapshot_evidence=snapshot_evidence)
                completion = self._verify_reconciled_owner_tick_completion(
                    completion, payload=payload,
                    expected_snapshot_id=(
                        self._prepared_consolidation_snapshot.snapshot_id),
                    expected_snapshot_digest=(
                        self._prepared_consolidation_snapshot.digest))
                if owner_tick_preexisting:
                    started = self._operation_journal.begin(request)
                    if started.get("state") == "completed":
                        receipt = started["receipt"]
                        if receipt.get("result_digest") != digest_payload(
                                completion):
                            raise ValueError(
                                "worker_consolidation_recovery_completion_conflict")
                    elif started.get("state") in {"started", "ambiguous"}:
                        receipt = self._operation_journal.complete(request,
                            result=completion)
                    else:
                        raise ValueError(
                            "worker_consolidation_recovery_scope_conflict")
                else:
                    receipt = self._operation_journal.complete(request,
                        result=completion)
            except Exception as exc:
                return {"status": "rejected", "result": {
                    "reason_code": _safe_worker_reason(exc,
                        "worker_consolidation_owner_tick_unverified"),
                    "intent_digest": recovery.get("intent", {}).get(
                        "intent_digest"),
                    "automatic_replay_performed": False,
                    "developmental_writeback_performed": False,
                    "authority": False}}
            return {"status": "completed", "result": {
                "recovered_completion": receipt["result"],
                "completion_receipt_digest": receipt["receipt_digest"],
                "recovery_from_owner_tick": True,
                "recovery_intent_created_after_owner_tick":
                    owner_tick_preexisting,
                "automatic_replay_performed": False,
                "recovery_inference_performed": False,
                "authority": False}}
        return {"status": "rejected", "result": {
            "reason_code": "worker_consolidation_execution_not_enabled",
            "snapshot_digest_verified": payload["snapshot_digest"],
            "operation_intent_written": False,
            "developmental_writeback_performed": False,
            "authority": False}}

    def _verify_reconciled_owner_tick_completion(self, value: Any, *,
            payload: Any, expected_snapshot_id: str,
            expected_snapshot_digest: str) -> dict[str, Any]:
        """Check the sealed recovery result against its original RPC intent."""
        from .durable_developmental_learning_experiment import (
            _resolve_history_state_snapshot,
            _verify_append_only_consolidation_state,
        )

        fields = {"schema_version", "protocol_id", "protocol_digest",
            "condition", "branch_id", "tick_id", "snapshot_id",
            "snapshot_digest", "baseline_history_state_digest",
            "resident_tick_status", "source_fact_ids", "selected_fact_ids",
            "observation_ids", "post_history_state_snapshot",
            "new_writeback_ref", "new_writeback_receipt_ref",
            "developmental_writeback_performed",
            "withhold_developmental_history", "scorer_outcomes_included",
            "recovery_inference_performed", "learning_established", "authority"}
        if (not isinstance(value, Mapping) or set(value) != fields
                or not isinstance(payload, Mapping)
                or value.get("schema_version") !=
                    "sentientos.durable_learning_worker_owner_tick_recovery:v1"
                or value.get("protocol_id") != self._protocol["protocol_id"]
                or value.get("protocol_digest") !=
                    self._protocol["protocol_digest"]
                or value.get("condition") != self._condition
                or value.get("branch_id") != self._branch.branch_id
                or value.get("tick_id") != (f"durable-learning-consolidation-"
                    f"{self._protocol['protocol_id']}-{self._condition}")
                or value.get("snapshot_digest") != payload.get("snapshot_digest")
                or value.get("snapshot_id") != expected_snapshot_id
                or value.get("snapshot_digest") != expected_snapshot_digest
                or value.get("baseline_history_state_digest") !=
                    payload.get("baseline_history_state_digest")
                or value.get("baseline_history_state_digest") !=
                    self._protocol.get("baseline_history_state_digest")
                or value.get("resident_tick_status") != "completed"
                or value.get("source_fact_ids") != payload.get("source_fact_ids")
                or value.get("withhold_developmental_history") is not
                    (self._condition == "relevant_experience_withheld")
                or value.get("withhold_developmental_history") is not
                    payload.get("withhold_developmental_history")
                or value.get("scorer_outcomes_included") is not False
                or value.get("recovery_inference_performed") is not False
                or value.get("learning_established") is not False
                or value.get("authority") is not False
                or not isinstance(value.get("snapshot_id"), str)
                or not value["snapshot_id"]
                or not isinstance(value.get("observation_ids"), list)
                or len(value["observation_ids"]) != 1
                or not isinstance(value["observation_ids"][0], str)
                or not value["observation_ids"][0]):
            raise ValueError("worker_consolidation_completion_binding_invalid")

        source_fact_ids = value.get("source_fact_ids")
        selected_fact_ids = value.get("selected_fact_ids")
        if (not isinstance(source_fact_ids, list)
                or not source_fact_ids
                or any(not isinstance(item, str) or not item
                    for item in source_fact_ids)
                or len(set(source_fact_ids)) != len(source_fact_ids)
                or not isinstance(selected_fact_ids, list)
                or any(not isinstance(item, str) or not item
                    for item in selected_fact_ids)
                or len(set(selected_fact_ids)) != len(selected_fact_ids)
                or not set(selected_fact_ids).issubset(set(source_fact_ids))):
            raise ValueError("worker_consolidation_completion_fact_binding_invalid")
        post_state = _resolve_history_state_snapshot(
            lambda: value.get("post_history_state_snapshot"))
        baseline_refs = payload.get("baseline_record_refs")
        _verify_append_only_consolidation_state(baseline_refs,
            post_state["record_refs"])
        baseline_ids = {ref["record_id"] for ref in baseline_refs}
        new_refs = [dict(ref) for ref in post_state["record_refs"]
            if ref["record_id"] not in baseline_ids]
        writeback_ref = value.get("new_writeback_ref")
        receipt_ref = value.get("new_writeback_receipt_ref")
        if writeback_ref is None and receipt_ref is None:
            if (new_refs or value.get("developmental_writeback_performed") is not False
                    or selected_fact_ids):
                raise ValueError(
                    "worker_consolidation_completion_writeback_invalid")
        elif (not isinstance(writeback_ref, Mapping)
                or set(writeback_ref) != {"record_id", "record_digest"}
                or not isinstance(receipt_ref, Mapping)
                or set(receipt_ref) != {"receipt_id", "receipt_digest"}
                or value.get("developmental_writeback_performed") is not True
                or len(new_refs) != 1
                or new_refs[0] != {**dict(writeback_ref), **dict(receipt_ref)}):
            raise ValueError(
                "worker_consolidation_completion_writeback_invalid")
        return dict(value)

    def _reconcile_completed_owner_tick(self, *, payload: Mapping[str, Any],
            snapshot_evidence: Mapping[str, Any]) -> dict[str, Any]:
        """Commit a verified owner tick after a worker/journal crash window.

        This path only reloads already committed owner state. It never starts
        or retries a resident tick and does not enable first-time mutation.
        """
        from .durable_developmental_learning_experiment import (
            _durable_learning_observation_has_history_context,
            _durable_learning_observation_has_no_prior_context,
            _durable_learning_target_experience_refs,
            _verify_append_only_consolidation_state,
            _resolve_history_state_snapshot,
        )

        owner = self._branch.experience_source._owner
        tick_status_fn = getattr(owner,
            "developmental_tick_status_readonly", None)
        observations_fn = getattr(owner, "developmental_tick_observations", None)
        writeback = getattr(owner, "writeback", None)
        inspect_records = getattr(writeback, "inspect_completed_records", None)
        if not all(callable(value) for value in
                (tick_status_fn, observations_fn, inspect_records)):
            raise ValueError("worker_consolidation_owner_recovery_api_unavailable")
        tick_id = (f"durable-learning-consolidation-"
            f"{self._protocol['protocol_id']}-{self._condition}")
        tick_status = tick_status_fn(tick_id=tick_id)
        if (not isinstance(tick_status, Mapping)
                or set(tick_status) != {"status", "tick", "authority"}
                or tick_status.get("authority") is not False
                or tick_status.get("status") != "completed"):
            raise ValueError("worker_consolidation_owner_tick_not_completed")
        tick = tick_status.get("tick")
        snapshot = self._prepared_consolidation_snapshot
        if (not isinstance(tick, Mapping) or snapshot is None
                or tick.get("tick_id") != tick_id
                or tick.get("snapshot_id") != snapshot.snapshot_id
                or tick.get("snapshot_digest") != snapshot.digest
                or payload.get("snapshot_digest") != snapshot.digest):
            raise ValueError("worker_consolidation_owner_tick_binding_invalid")
        source_fact_ids = snapshot_evidence.get("source_fact_ids")
        baseline_refs = payload.get("baseline_record_refs")
        if (not isinstance(source_fact_ids, list)
                or not isinstance(baseline_refs, list)):
            raise ValueError("worker_consolidation_owner_recovery_context_invalid")
        observations = observations_fn(tick_id=tick_id)
        if (not isinstance(observations, (list, tuple)) or len(observations) != 1
                or not isinstance(observations[0], Mapping)):
            raise ValueError("worker_consolidation_owner_observation_invalid")
        observation = observations[0]
        observation_id = observation.get("observation_id")
        expected_condition_id = ("durable-learning-history-withheld"
            if self._condition == "relevant_experience_withheld" else
            "with-history")
        expected_refs = (_durable_learning_target_experience_refs(
            protocol=self._protocol, branch=self._branch)
            if self._condition == "relevant_experience_available" else [])
        current_fact_ids = observation.get("current_fact_ids")
        if (not isinstance(observation_id, str) or not observation_id
                or observation.get("tick_id") != tick_id
                or observation.get("condition_id") != expected_condition_id
                or not isinstance(current_fact_ids, (list, tuple))
                or not current_fact_ids
                or not set(current_fact_ids).issubset(set(source_fact_ids))
                or observation.get("current_snapshot_id") != snapshot.snapshot_id
                or observation.get("current_snapshot_digest") != snapshot.digest):
            raise ValueError("worker_consolidation_owner_observation_binding_invalid")
        if self._condition == "relevant_experience_withheld":
            if (observation.get("developmental_projection_present") is not False
                    or observation.get("retrieved_record_ids")
                    or observation.get("retrieved_record_digests")
                    or not _durable_learning_observation_has_no_prior_context(
                        observation)):
                raise ValueError(
                    "worker_consolidation_owner_withheld_observation_invalid")
        elif (not _durable_learning_observation_has_history_context(
                observation, baseline_refs, expected_refs)):
            raise ValueError(
                "worker_consolidation_owner_available_observation_invalid")

        post_state = _resolve_history_state_snapshot(
            self._branch.experience_source.current_history_state_snapshot)
        _verify_append_only_consolidation_state(baseline_refs,
            post_state["record_refs"])
        baseline_ids = {ref["record_id"] for ref in baseline_refs}
        new_refs = [dict(ref) for ref in post_state["record_refs"]
            if ref["record_id"] not in baseline_ids]
        record_id, receipt_id = tick.get("record_id"), tick.get("receipt_id")
        record_ref: dict[str, str] | None = None
        writeback_receipt_ref: dict[str, str] | None = None
        selected_fact_ids: list[str] = []
        if record_id is None and receipt_id is None:
            if new_refs:
                raise ValueError(
                    "worker_consolidation_owner_state_delta_unattributed")
        elif not isinstance(record_id, str) or not isinstance(receipt_id, str):
            raise ValueError("worker_consolidation_owner_writeback_binding_invalid")
        else:
            matches = [(record, receipt) for record, receipt in inspect_records()
                if getattr(record, "record_id", None) == record_id
                and getattr(receipt, "receipt_id", None) == receipt_id]
            if len(matches) != 1:
                raise ValueError(
                    "worker_consolidation_owner_writeback_unverified")
            record, receipt = matches[0]
            record_ref = {"record_id": record.record_id,
                "record_digest": record.record_digest}
            writeback_receipt_ref = {"receipt_id": receipt.receipt_id,
                "receipt_digest": receipt.receipt_digest}
            expected_new_ref = {**record_ref, **writeback_receipt_ref}
            if (new_refs != [expected_new_ref]
                    or getattr(receipt, "record_id", None) != record.record_id
                    or getattr(receipt, "record_digest", None) !=
                        record.record_digest
                    or getattr(receipt, "storage_verified", None) is not True
                    or getattr(receipt, "grants_authority", None) is not False):
                raise ValueError(
                    "worker_consolidation_owner_writeback_lineage_invalid")
            candidate = getattr(record, "candidate", None)
            selected = candidate.get("selected_facts", ()) \
                if isinstance(candidate, Mapping) else ()
            selected_ids = [fact.get("fact_id") for fact in selected
                if isinstance(fact, Mapping)]
            if (not selected_ids
                    or not set(selected_ids).issubset(set(source_fact_ids))):
                raise ValueError(
                    "worker_consolidation_owner_writeback_fact_lineage_invalid")
            selected_fact_ids = selected_ids

        return {"schema_version":
                "sentientos.durable_learning_worker_owner_tick_recovery:v1",
            "protocol_id": self._protocol["protocol_id"],
            "protocol_digest": self._protocol["protocol_digest"],
            "condition": self._condition,
            "branch_id": self._branch.branch_id,
            "tick_id": tick_id,
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_digest": snapshot.digest,
            "baseline_history_state_digest": payload.get(
                "baseline_history_state_digest"),
            "resident_tick_status": "completed",
            "source_fact_ids": list(source_fact_ids),
            "selected_fact_ids": selected_fact_ids,
            "observation_ids": [observation_id],
            "post_history_state_snapshot": post_state,
            "new_writeback_ref": record_ref,
            "new_writeback_receipt_ref": writeback_receipt_ref,
            "developmental_writeback_performed": record_ref is not None,
            "withhold_developmental_history": (
                self._condition == "relevant_experience_withheld"),
            "scorer_outcomes_included": False,
            "recovery_inference_performed": False,
            "learning_established": False,
            "authority": False}

    inspect_delayed_probe_gate = _operation_not_enabled
