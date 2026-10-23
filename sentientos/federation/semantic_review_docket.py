"""Append-only local docket for revalidated federation semantic-review receipts.

Docket entries are local review metadata only. Their content digests are not
authentication, and reading an entry requires the caller to supply the exact
replay acceptance and locally pinned semantic policy used for revalidation.
No remote evidence is resolved and no admission, Health, planning, or execution
authority is exposed here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import threading

from sentientos.private_file_custody import (
    PrivateFileCustodyError,
    list_bounded_json_names_at,
    open_private_directory,
    publish_immutable_bytes,
    read_private_file_at,
)
from .peer_replay_owner import FederationPeerReplayAcceptance
from .peer_semantic_acceptance import (
    FederationPeerSemanticAcceptanceError,
    FederationPeerSemanticAcceptancePolicy,
    FederationPeerSemanticAcceptanceReceipt,
    accept_peer_event_for_local_review,
    semantic_acceptance_receipt_bytes,
    semantic_acceptance_receipt_digest_for,
    verify_semantic_acceptance_receipt_bytes,
)

_MAX_DOCKET_ENTRIES = 4096
_MAX_RECEIPT_BYTES = 70_000
_RECEIPT_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RECEIPT_NAME = re.compile(r"[0-9a-f]{64}\.json\Z")


class FederationPeerSemanticReviewDocketError(ValueError):
    """A review docket input, entry, or private publication failed closed."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class FederationPeerSemanticReviewDocketAppend:
    """The local receipt returned after immutable publication and readback."""

    receipt_digest: str
    created: bool
    receipt: FederationPeerSemanticAcceptanceReceipt


class FederationPeerSemanticReviewDocket:
    """Store only policy-eligible receipts as bounded immutable private files.

    Listing returns filenames as untrusted content identifiers. A caller must
    provide the corresponding replay acceptance and locally pinned policy to
    `read`; each read reparses, canonicalizes, and semantically revalidates
    the complete receipt before returning it.
    """

    __slots__ = ("_root", "_max_entries", "_lock")

    def __init__(self, root: str | Path, *, max_entries: int = _MAX_DOCKET_ENTRIES) -> None:
        if not isinstance(root, (str, Path)) or not Path(root).is_absolute():
            raise FederationPeerSemanticReviewDocketError(
                "semantic_review_docket_root_must_be_absolute",
            )
        if type(max_entries) is not int or not 1 <= max_entries <= _MAX_DOCKET_ENTRIES:
            raise FederationPeerSemanticReviewDocketError(
                "semantic_review_docket_limit_invalid",
            )
        self._root = Path(root)
        self._max_entries = max_entries
        self._lock = threading.RLock()

    @property
    def root(self) -> Path:
        return self._root

    @property
    def max_entries(self) -> int:
        return self._max_entries

    def list_receipt_digests(self) -> tuple[str, ...]:
        """Return bounded filename-derived identifiers; this does not verify entries."""
        try:
            directory_fd = open_private_directory(self.root, create=False)
        except PrivateFileCustodyError as exc:
            if exc.code == "directory_root_missing":
                return ()
            raise FederationPeerSemanticReviewDocketError(
                "semantic_review_docket_unavailable",
            ) from exc
        try:
            try:
                names = list_bounded_json_names_at(
                    directory_fd,
                    max_entries=self.max_entries,
                    max_directory_entries=self.max_entries + 1024,
                )
            except PrivateFileCustodyError as exc:
                raise FederationPeerSemanticReviewDocketError(
                    "semantic_review_docket_bounds_exceeded",
                ) from exc
        finally:
            try:
                os.close(directory_fd)
            except OSError as exc:
                raise FederationPeerSemanticReviewDocketError(
                    "semantic_review_docket_unavailable",
                ) from exc
        if any(_RECEIPT_NAME.fullmatch(name) is None for name in names):
            raise FederationPeerSemanticReviewDocketError(
                "semantic_review_docket_filename_invalid",
            )
        return tuple("sha256:" + name[:-5] for name in names)

    def append(
        self,
        replay: FederationPeerReplayAcceptance,
        *,
        policy: FederationPeerSemanticAcceptancePolicy,
    ) -> FederationPeerSemanticReviewDocketAppend:
        """Append one locally eligible receipt; identical retries are idempotent."""
        if not isinstance(replay, FederationPeerReplayAcceptance):
            raise FederationPeerSemanticAcceptanceError("semantic_replay_receipt_required")
        if not isinstance(policy, FederationPeerSemanticAcceptancePolicy):
            raise FederationPeerSemanticAcceptanceError("semantic_policy_required")
        with self._lock:
            receipt = accept_peer_event_for_local_review(replay, policy=policy)
            if receipt.decision != "accepted_for_local_review":
                raise FederationPeerSemanticReviewDocketError(
                    "semantic_review_receipt_not_eligible",
                )
            raw = semantic_acceptance_receipt_bytes(receipt)
            digest = semantic_acceptance_receipt_digest_for(receipt)
            existing = self.list_receipt_digests()
            if digest not in existing and len(existing) >= self.max_entries:
                raise FederationPeerSemanticReviewDocketError(
                    "semantic_review_docket_limit_exceeded",
                )
            path = self.root / (digest[7:] + ".json")
            try:
                created = publish_immutable_bytes(
                    path,
                    raw,
                    max_bytes=_MAX_RECEIPT_BYTES,
                    collision_code="semantic_review_docket_content_conflict",
                    max_entries=self.max_entries,
                )
            except PrivateFileCustodyError as exc:
                raise FederationPeerSemanticReviewDocketError(
                    "semantic_review_docket_publication_failed",
                ) from exc
            verified = self.read(digest, replay=replay, policy=policy)
            if verified != receipt:
                raise FederationPeerSemanticReviewDocketError(
                    "semantic_review_docket_readback_mismatch",
                )
            return FederationPeerSemanticReviewDocketAppend(
                receipt_digest=digest,
                created=created,
                receipt=verified,
            )

    def read(
        self,
        receipt_digest: str,
        *,
        replay: FederationPeerReplayAcceptance,
        policy: FederationPeerSemanticAcceptancePolicy,
    ) -> FederationPeerSemanticAcceptanceReceipt:
        """Read one entry only after exact replay and local-policy revalidation."""
        if not isinstance(receipt_digest, str) or _RECEIPT_DIGEST.fullmatch(receipt_digest) is None:
            raise FederationPeerSemanticReviewDocketError(
                "semantic_review_docket_digest_invalid",
            )
        if not isinstance(replay, FederationPeerReplayAcceptance):
            raise FederationPeerSemanticAcceptanceError("semantic_replay_receipt_required")
        if not isinstance(policy, FederationPeerSemanticAcceptancePolicy):
            raise FederationPeerSemanticAcceptanceError("semantic_policy_required")
        try:
            directory_fd = open_private_directory(self.root, create=False)
        except PrivateFileCustodyError as exc:
            if exc.code == "directory_root_missing":
                raise FederationPeerSemanticReviewDocketError(
                    "semantic_review_docket_entry_missing",
                ) from exc
            raise FederationPeerSemanticReviewDocketError(
                "semantic_review_docket_unavailable",
            ) from exc
        try:
            try:
                raw = read_private_file_at(
                    directory_fd,
                    receipt_digest[7:] + ".json",
                    max_bytes=_MAX_RECEIPT_BYTES,
                    require_private_mode=True,
                )
            except PrivateFileCustodyError as exc:
                if exc.code == "file_missing":
                    raise FederationPeerSemanticReviewDocketError(
                        "semantic_review_docket_entry_missing",
                    ) from exc
                raise FederationPeerSemanticReviewDocketError(
                    "semantic_review_docket_entry_unavailable",
                ) from exc
        finally:
            try:
                os.close(directory_fd)
            except OSError as exc:
                raise FederationPeerSemanticReviewDocketError(
                    "semantic_review_docket_unavailable",
                ) from exc
        receipt = verify_semantic_acceptance_receipt_bytes(
            raw,
            replay=replay,
            policy=policy,
        )
        if (receipt.decision != "accepted_for_local_review"
                or semantic_acceptance_receipt_digest_for(receipt) != receipt_digest):
            raise FederationPeerSemanticReviewDocketError(
                "semantic_review_docket_entry_binding_mismatch",
            )
        return receipt


__all__ = [
    "FederationPeerSemanticReviewDocket",
    "FederationPeerSemanticReviewDocketAppend",
    "FederationPeerSemanticReviewDocketError",
]
