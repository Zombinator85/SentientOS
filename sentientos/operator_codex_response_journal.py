"""Crash-tolerant custody for operator-recorded external Codex responses.

The journal preserves operator-submitted bytes and packet/preregistration
identity. It does not authenticate a model inference or grant admission.
"""
from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import Any, Mapping

from .embodied_consequence import canonical_bytes, digest


class OperatorResponseJournalError(ValueError):
    """Invalid, conflicting, or unrecoverable response-journal data."""


_PACKET_ID = re.compile(r"[0-9a-f]{24}\Z")
_RESPONSE_FIELDS = {"packet_id", "session_id", "timestamp", "visible_model_name",
    "effort_setting", "generation_settings", "raw_output"}
_JOURNAL_FIELDS = {"schema_version", "packet_id", "preregistration_digest",
    "packet_digest", "response", "response_digest"}


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def record_operator_codex_response(*, journal_dir: str | Path,
        preregistration: Mapping[str, Any], packet_id: str,
        response: Mapping[str, Any]) -> dict[str, Any]:
    """Write one immutable response envelope, refusing overwrite and symlinks."""
    if (not isinstance(preregistration, Mapping)
            or preregistration.get("schema_version")
                != "sentientos.operator_codex_strategy_preregistration:v1"
            or not isinstance(preregistration.get("packet_digests"), Mapping)
            or not isinstance(packet_id, str) or not _PACKET_ID.fullmatch(packet_id)
            or packet_id not in preregistration["packet_digests"]
            or not isinstance(response, Mapping)
            or set(response) - _RESPONSE_FIELDS
            or response.get("packet_id") != packet_id):
        raise OperatorResponseJournalError("external_response_identity_invalid")
    envelope = {"schema_version": "sentientos.operator_codex_response_journal:v1",
        "packet_id": packet_id, "preregistration_digest": digest(preregistration),
        "packet_digest": preregistration["packet_digests"][packet_id],
        "response": dict(response), "response_digest": digest(response)}
    directory = Path(journal_dir)
    try:
        mode = directory.lstat().st_mode
        if not stat.S_ISDIR(mode):
            raise OperatorResponseJournalError("external_response_journal_directory_invalid")
        directory_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise OperatorResponseJournalError("external_response_journal_directory_invalid") from exc
    name = packet_id + ".json"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(name, flags, 0o600, dir_fd=directory_fd)
    except FileExistsError as exc:
        os.close(directory_fd)
        raise OperatorResponseJournalError("external_response_packet_already_recorded") from exc
    try:
        payload = canonical_bytes(envelope) + b"\n"
        with os.fdopen(fd, "wb", closefd=True) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(directory_fd)
    except Exception:
        # The exclusive entry remains as crash evidence; never replace it implicitly.
        raise
    finally:
        os.close(directory_fd)
    return envelope


def recover_operator_codex_responses(*, journal_dir: str | Path,
        preregistration: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Reconstruct recorded responses and an explicit partial/corrupt disposition."""
    packet_digests = preregistration.get("packet_digests")
    if (not isinstance(packet_digests, Mapping) or not packet_digests
            or preregistration.get("schema_version")
            != "sentientos.operator_codex_strategy_preregistration:v1"):
        raise OperatorResponseJournalError("external_response_preregistration_invalid")
    packet_ids = set(packet_digests)
    directory = Path(journal_dir)
    try:
        if not stat.S_ISDIR(directory.lstat().st_mode):
            raise OperatorResponseJournalError("external_response_journal_directory_invalid")
        entries = list(directory.iterdir())
    except OSError as exc:
        raise OperatorResponseJournalError("external_response_journal_directory_invalid") from exc
    responses: dict[str, dict[str, Any]] = {}
    corrupt: list[str] = []
    unknown: list[str] = []
    expected_registration_digest = digest(preregistration)
    for path in entries:
        if path.suffix != ".json":
            continue
        packet_id = path.stem
        if packet_id not in packet_ids:
            unknown.append(path.name)
            continue
        try:
            if not stat.S_ISREG(path.lstat().st_mode):
                raise ValueError("not_regular")
            envelope = json.loads(path.read_text(encoding="utf-8"),
                object_pairs_hook=_unique_object)
            if (not isinstance(envelope, Mapping) or set(envelope) != _JOURNAL_FIELDS
                    or envelope.get("schema_version") != "sentientos.operator_codex_response_journal:v1"
                    or envelope.get("packet_id") != packet_id
                    or envelope.get("preregistration_digest") != expected_registration_digest
                    or envelope.get("packet_digest") != packet_digests[packet_id]
                    or not isinstance(envelope.get("response"), Mapping)
                    or envelope["response"].get("packet_id") != packet_id
                    or set(envelope["response"]) - _RESPONSE_FIELDS
                    or envelope.get("response_digest") != digest(envelope["response"])):
                raise ValueError("envelope_invalid")
            responses[packet_id] = dict(envelope["response"])
        except (OSError, UnicodeError, ValueError, TypeError):
            corrupt.append(path.name)
    disposition = {"status": "complete" if len(responses) == len(packet_ids)
            and not corrupt and not unknown else "partial_or_corrupt",
        "packet_count": len(packet_ids), "recorded_packet_ids": sorted(responses),
        "missing_packet_ids": sorted(packet_ids - set(responses) - {Path(name).stem for name in corrupt}),
        "corrupt_entries": sorted(corrupt), "unknown_entries": sorted(unknown),
        "external_sessions_replayed": False,
        "provenance_posture": "operator_recorded_unverified_external_output"}
    return responses, disposition
