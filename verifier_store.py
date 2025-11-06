from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Sequence

from sentientos.storage import get_data_root


if TYPE_CHECKING:
    from sentient_verifier import ConsensusVerdict, Vote


@dataclass(frozen=True)
class VerifierSummary:
    job_id: str
    script_hash: str
    from_node: str | None
    verdict: str
    created_at: float
    verifier_node: str | None = None
    score: float | None = None
    proof_pass: int = 0
    proof_fail: int = 0
    proof_error: int = 0

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "job_id": self.job_id,
            "script_hash": self.script_hash,
            "from_node": self.from_node,
            "verdict": self.verdict,
            "created_at": self.created_at,
        }
        if self.verifier_node is not None:
            payload["verifier_node"] = self.verifier_node
        if self.score is not None:
            payload["score"] = self.score
        payload["proof_pass"] = self.proof_pass
        payload["proof_fail"] = self.proof_fail
        payload["proof_error"] = self.proof_error
        return payload


class VerifierStore:
    """Persist verification reports on the local filesystem."""

    def __init__(self, root: Optional[Path] = None, *, rotate_bytes: int = 5_000_000) -> None:
        self._root = Path(root) if root else get_data_root() / "verify"
        self._reports_dir = self._root / "reports"
        self._bundles_dir = self._root / "bundles"
        self._votes_dir = self._root / "votes"
        self._consensus_dir = self._root / "consensus"
        self._index_path = self._root / "reports.jsonl"
        self._consensus_index_path = self._root / "consensus_index.json"
        self._rotate_bytes = max(100_000, int(rotate_bytes))
        self._lock = threading.RLock()
        self._root.mkdir(parents=True, exist_ok=True)
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        self._bundles_dir.mkdir(parents=True, exist_ok=True)
        self._votes_dir.mkdir(parents=True, exist_ok=True)
        self._consensus_dir.mkdir(parents=True, exist_ok=True)

    @classmethod
    def default(cls) -> "VerifierStore":
        return cls()

    # -- persistence helpers -------------------------------------------------

    def save_report(self, report: Mapping[str, object]) -> VerifierSummary:
        """Store the verification ``report`` and append it to the index."""

        job_id = str(report.get("job_id") or "")
        if not job_id:
            raise ValueError("report is missing job_id")
        created_iso = self._extract_timestamp(report)
        created_at = created_iso or time.time()
        proof_pass, proof_fail, proof_error = self._extract_proof_counts(report)
        summary = VerifierSummary(
            job_id=job_id,
            script_hash=str(report.get("script_hash") or ""),
            from_node=self._optional_string(report.get("from_node")),
            verdict=str(report.get("verdict") or "unknown"),
            created_at=created_at,
            verifier_node=self._optional_string(report.get("verifier_node")),
            score=self._coerce_float(report.get("score")),
            proof_pass=proof_pass,
            proof_fail=proof_fail,
            proof_error=proof_error,
        )
        with self._lock:
            self._write_report_file(job_id, report)
            self._rotate_index_if_needed()
            with self._index_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(summary.to_dict(), sort_keys=True) + "\n")
            self._enforce_retention()
        return summary

    def get_report(self, job_id: str) -> Optional[Dict[str, object]]:
        path = self._reports_dir / f"{job_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def save_bundle(self, job_id: str, bundle: Mapping[str, object]) -> None:
        path = self._bundles_dir / f"{job_id}.json"
        try:
            path.write_text(json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")
        except OSError:
            path.write_text(json.dumps(bundle, sort_keys=True), encoding="utf-8")

    def get_bundle(self, job_id: str) -> Optional[Dict[str, object]]:
        path = self._bundles_dir / f"{job_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def store_vote(self, vote: "Vote" | Mapping[str, object]) -> None:
        if hasattr(vote, "to_dict"):
            payload = vote.to_dict()  # type: ignore[assignment]
        else:
            payload = dict(vote)
        job_id = str(payload.get("job_id") or "")
        voter = str(payload.get("voter_node") or "")
        if not job_id or not voter:
            raise ValueError("vote must include job_id and voter_node")
        with self._lock:
            vote_dir = self._votes_dir / job_id
            vote_dir.mkdir(parents=True, exist_ok=True)
            path = vote_dir / f"{voter}.json"
            path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
            self._update_consensus_index(job_id, vote_payload=payload)
            self._prune_votes_locked()

    def list_votes(self, job_id: str) -> List[Dict[str, object]]:
        vote_dir = self._votes_dir / job_id
        if not vote_dir.exists():
            return []
        votes: List[Dict[str, object]] = []
        for path in sorted(vote_dir.glob("*.json")):
            try:
                votes.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                continue
        return votes

    def store_consensus(self, consensus: "ConsensusVerdict" | Mapping[str, object]) -> None:
        if hasattr(consensus, "to_dict"):
            payload = consensus.to_dict()  # type: ignore[assignment]
        else:
            payload = dict(consensus)
        job_id = str(payload.get("job_id") or "")
        if not job_id:
            raise ValueError("consensus requires job_id")
        with self._lock:
            path = self._consensus_dir / f"{job_id}.json"
            path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
            self._update_consensus_index(job_id, consensus_payload=payload)

    def get_consensus(self, job_id: str) -> Optional[Dict[str, object]]:
        path = self._consensus_dir / f"{job_id}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def latest_consensus(self, job_id: str) -> Optional[Dict[str, object]]:
        return self.get_consensus(job_id)

    # Backwards compatibility
    def load_bundle(self, job_id: str) -> Optional[Dict[str, object]]:  # pragma: no cover - legacy
        return self.get_bundle(job_id)

    def get_status(self, job_id: str) -> Optional[VerifierSummary]:
        entries = self._load_index()
        for entry in reversed(entries):
            if entry.get("job_id") == job_id:
                return self._summary_from_entry(entry)
        return None

    def list_reports(self, *, limit: int = 50) -> List[VerifierSummary]:
        entries = self._load_index()
        trimmed = entries[-max(1, limit) :]
        return [self._summary_from_entry(entry) for entry in reversed(trimmed)]

    def verdict_counts(self, *, since: float | None = None) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for entry in self._load_index():
            created_at = self._coerce_float(entry.get("created_at"))
            if since is not None and created_at is not None and created_at < since:
                continue
            verdict = str(entry.get("verdict") or "unknown")
            counts[verdict] = counts.get(verdict, 0) + 1
        return counts

    def stats(self, *, since: float | None = None) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        proof_pass = 0
        proof_fail = 0
        proof_error = 0
        for entry in self._load_index():
            created_at = self._coerce_float(entry.get("created_at"))
            if since is not None and created_at is not None and created_at < since:
                continue
            verdict = str(entry.get("verdict") or "unknown")
            counts[verdict] = counts.get(verdict, 0) + 1
            proof_pass += self._coerce_int(entry.get("proof_pass"))
            proof_fail += self._coerce_int(entry.get("proof_fail"))
            proof_error += self._coerce_int(entry.get("proof_error"))
        return {
            "counts": counts,
            "proof_counts": {
                "pass": proof_pass,
                "fail": proof_fail,
                "error": proof_error,
            },
        }

    def consensus_index(self) -> Dict[str, Any]:
        with self._lock:
            return self._load_consensus_index()

    def replay_job(
        self,
        job_id: str,
        *,
        verifier: "SentientVerifier" | None = None,
    ) -> Optional[Mapping[str, object]]:
        bundle = self.get_bundle(job_id)
        if bundle is None:
            return None
        if verifier is None:
            from sentient_verifier import SentientVerifier  # Local import to avoid cycle

            verifier = SentientVerifier(store=self)
        report = verifier.verify_bundle(dict(bundle))
        return report.to_dict()

    # -- internal helpers ----------------------------------------------------

    def _write_report_file(self, job_id: str, report: Mapping[str, object]) -> None:
        path = self._reports_dir / f"{job_id}.json"
        try:
            path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        except OSError:
            # Losing the report is worse than missing pretty formatting: retry
            path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")

    def _rotate_index_if_needed(self) -> None:
        if not self._index_path.exists():
            return
        try:
            size = self._index_path.stat().st_size
        except OSError:
            return
        if size <= self._rotate_bytes:
            return
        backup = self._index_path.with_name(self._index_path.name + ".1")
        try:
            if backup.exists():
                backup.unlink()
            self._index_path.rename(backup)
        except OSError:
            return

    def _enforce_retention(self) -> None:
        max_jobs = 1000
        max_bytes = 100 * 1024 * 1024
        entries = self._load_index()
        if not entries:
            return
        total_size = 0
        sizes: Dict[str, int] = {}
        for entry in entries:
            job_id = str(entry.get("job_id") or "")
            if not job_id:
                continue
            size = self._job_disk_usage(job_id)
            sizes[job_id] = size
            total_size += size
        changed = False
        while entries and (len(entries) > max_jobs or total_size > max_bytes):
            entry = entries.pop(0)
            job_id = str(entry.get("job_id") or "")
            if job_id:
                total_size -= sizes.get(job_id, 0)
                self._remove_job_files(job_id)
            changed = True
        if changed:
            self._rewrite_index(entries)

    def _load_index(self) -> List[Dict[str, object]]:
        if not self._index_path.exists():
            return []
        try:
            raw = self._index_path.read_text(encoding="utf-8")
        except OSError:
            return []
        entries: List[Dict[str, object]] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                entries.append(record)
        return entries

    @staticmethod
    def _summary_from_entry(entry: Mapping[str, object]) -> VerifierSummary:
        return VerifierSummary(
            job_id=str(entry.get("job_id") or ""),
            script_hash=str(entry.get("script_hash") or ""),
            from_node=VerifierStore._optional_string(entry.get("from_node")),
            verdict=str(entry.get("verdict") or "unknown"),
            created_at=float(entry.get("created_at") or 0.0),
            verifier_node=VerifierStore._optional_string(entry.get("verifier_node")),
            score=VerifierStore._coerce_float(entry.get("score")),
            proof_pass=VerifierStore._coerce_int(entry.get("proof_pass")),
            proof_fail=VerifierStore._coerce_int(entry.get("proof_fail")),
            proof_error=VerifierStore._coerce_int(entry.get("proof_error")),
        )

    @staticmethod
    def _extract_timestamp(report: Mapping[str, object]) -> float | None:
        timestamps = report.get("timestamps")
        if isinstance(timestamps, Mapping):
            for key in ("verified", "submitted"):
                value = timestamps.get(key)
                if isinstance(value, (int, float)):
                    return float(value)
                if isinstance(value, str):
                    try:
                        return _parse_iso_timestamp(value)
                    except ValueError:
                        continue
        return None

    @staticmethod
    def _extract_proof_counts(report: Mapping[str, object]) -> tuple[int, int, int]:
        counts = report.get("proof_counts")
        if not isinstance(counts, Mapping):
            return 0, 0, 0
        return (
            VerifierStore._coerce_int(counts.get("pass")),
            VerifierStore._coerce_int(counts.get("fail")),
            VerifierStore._coerce_int(counts.get("error")),
        )

    @staticmethod
    def _coerce_float(value: object) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if value in (None, ""):
            return None
        return str(value)

    @staticmethod
    def _coerce_int(value: object) -> int:
        try:
            if value is None or value == "":
                return 0
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _job_disk_usage(self, job_id: str) -> int:
        total = 0
        if not job_id:
            return total
        for root in (self._reports_dir, self._bundles_dir, self._consensus_dir):
            path = root / f"{job_id}.json"
            try:
                total += path.stat().st_size
            except OSError:
                continue
        vote_dir = self._votes_dir / job_id
        if vote_dir.exists():
            for vote_path in vote_dir.glob("*.json"):
                try:
                    total += vote_path.stat().st_size
                except OSError:
                    continue
        return total

    def _remove_job_files(self, job_id: str) -> None:
        for root in (self._reports_dir, self._bundles_dir, self._consensus_dir):
            path = root / f"{job_id}.json"
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                continue
        vote_dir = self._votes_dir / job_id
        if vote_dir.exists():
            for vote_path in vote_dir.glob("*.json"):
                try:
                    vote_path.unlink()
                except OSError:
                    continue
            try:
                vote_dir.rmdir()
            except OSError:
                pass

    def _rewrite_index(self, entries: Sequence[Mapping[str, object]]) -> None:
        try:
            lines = [json.dumps(dict(entry), sort_keys=True) for entry in entries]
            data = "\n".join(lines)
            if lines:
                data += "\n"
            self._index_path.write_text(data, encoding="utf-8")
        except OSError:
            pass

    def _load_consensus_index(self) -> Dict[str, Any]:
        if not self._consensus_index_path.exists():
            return {}
        try:
            content = self._consensus_index_path.read_text(encoding="utf-8")
        except OSError:
            return {}
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return {}
        if isinstance(payload, dict):
            return payload
        return {}

    def _write_consensus_index(self, data: Mapping[str, Any]) -> None:
        try:
            self._consensus_index_path.write_text(
                json.dumps(data, sort_keys=True, indent=2),
                encoding="utf-8",
            )
        except OSError:
            pass

    def _update_consensus_index(
        self,
        job_id: str,
        *,
        vote_payload: Optional[Mapping[str, object]] = None,
        consensus_payload: Optional[Mapping[str, object]] = None,
    ) -> None:
        index = self._load_consensus_index()
        entry = dict(index.get(job_id) or {})
        participants = set(entry.get("participants") or [])
        votes_count = int(entry.get("votes_count") or 0)
        finalized = bool(entry.get("finalized") or False)
        final_verdict = entry.get("final_verdict")
        quorum_k = entry.get("quorum_k")
        quorum_n = entry.get("quorum_n")
        if vote_payload:
            voter = str(vote_payload.get("voter_node") or "")
            if voter:
                participants.add(voter)
            votes_count = len(self.list_votes(job_id))
        if consensus_payload:
            finalized = bool(consensus_payload.get("finalized_at"))
            final_verdict = consensus_payload.get("final_verdict")
            if consensus_payload.get("quorum_k") is not None:
                try:
                    quorum_k = int(consensus_payload.get("quorum_k"))
                except (TypeError, ValueError):
                    quorum_k = quorum_k
            if consensus_payload.get("quorum_n") is not None:
                try:
                    quorum_n = int(consensus_payload.get("quorum_n"))
                except (TypeError, ValueError):
                    quorum_n = quorum_n
            votes = consensus_payload.get("votes")
            if isinstance(votes, list):
                for vote in votes:
                    if isinstance(vote, Mapping):
                        voter_node = vote.get("voter_node")
                        if isinstance(voter_node, str) and voter_node:
                            participants.add(voter_node)
        index[job_id] = {
            "votes_count": votes_count,
            "participants": sorted(participants),
            "finalized": finalized,
            "final_verdict": final_verdict,
            "quorum_k": quorum_k,
            "quorum_n": quorum_n,
        }
        self._write_consensus_index(index)

    def _prune_votes_locked(self) -> None:
        files: List[tuple[float, int, Path]] = []
        total_bytes = 0
        for path in self._votes_dir.glob("*/*.json"):
            try:
                stat = path.stat()
            except OSError:
                continue
            files.append((stat.st_mtime, stat.st_size, path))
            total_bytes += stat.st_size
        files.sort(key=lambda item: item[0])
        max_files = 2000
        max_bytes = 200 * 1024 * 1024
        while files and (len(files) > max_files or total_bytes > max_bytes):
            _, size, path = files.pop(0)
            total_bytes -= size
            try:
                path.unlink()
            except OSError:
                continue
            parent = path.parent
            try:
                if not any(parent.iterdir()):
                    parent.rmdir()
            except OSError:
                pass


def _parse_iso_timestamp(value: str) -> float:
    from datetime import datetime

    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


__all__ = [
    "VerifierStore",
    "VerifierSummary",
]
