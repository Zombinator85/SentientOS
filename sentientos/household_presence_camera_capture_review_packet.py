from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Any, Literal, Mapping

ReviewMode = Literal["design_only", "dry_run_only", "future_live_review"]

ReviewStatus = Literal[
    "capture_review_packet_ready_for_operator_review",
    "capture_review_packet_ready_for_dry_run_only",
    "capture_review_packet_valid_with_warnings",
    "capture_review_packet_blocked_missing_authorization",
    "capture_review_packet_blocked_missing_denial_ledger",
    "capture_review_packet_blocked_missing_disabled_capture_proof",
    "capture_review_packet_blocked_missing_shell_proof",
    "capture_review_packet_blocked_missing_stub_proof",
    "capture_review_packet_blocked_missing_host_candidate",
    "capture_review_packet_blocked_missing_zone_config",
    "capture_review_packet_blocked_missing_dry_run_proof",
    "capture_review_packet_blocked_missing_policy_chain",
    "capture_review_packet_blocked_unresolved_denials",
    "capture_review_packet_blocked_scope_mismatch",
    "capture_review_packet_blocked_stale_proof",
    "capture_review_packet_blocked_media_payload",
    "capture_review_packet_blocked_speaker_boundary",
    "capture_review_packet_blocked_external_authority",
    "capture_review_packet_invalid",
    "capture_review_packet_failed",
]