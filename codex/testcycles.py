"""Codex test refinement cycles with generated test proposals."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, MutableMapping

import json
import textwrap

from .config import WET_RUN_ENABLED
from .implementations import Implementor, ImplementationRecord
from .refinements import Refiner, RefinementTransform
from .sandbox import CodexSandbox


def _default_now() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(value: str) -> str:
    normalized = "".join(
        char if char.isalnum() else "_" for char in value.strip().lower()
    )
    normalized = "_".join(filter(None, normalized.split("_")))
    return normalized or "spec"


@dataclass
class TestProposal:
    """Serialized metadata describing a synthesized test case."""

    proposal_id: str
    spec_id: str
    status: str
    created_at: str
    coverage_target: str
    failure_context: str
    feedback: str
    implementation_paths: list[str]
    style: str
    test_path: str
    approved_at: str | None = None
    approved_by: str | None = None
    rejected_at: str | None = None
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "proposal_id": self.proposal_id,
            "spec_id": self.spec_id,
            "status": self.status,
            "created_at": self.created_at,
            "coverage_target": self.coverage_target,
            "failure_context": self.failure_context,
            "feedback": self.feedback,
            "implementation_paths": list(self.implementation_paths),
            "style": self.style,
            "test_path": self.test_path,
        }
        if self.approved_at:
            payload["approved_at"] = self.approved_at
        if self.approved_by:
            payload["approved_by"] = self.approved_by
        if self.rejected_at:
            payload["rejected_at"] = self.rejected_at
        if self.rejection_reason:
            payload["rejection_reason"] = self.rejection_reason
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TestProposal":
        return cls(
            proposal_id=str(payload.get("proposal_id")),
            spec_id=str(payload.get("spec_id")),
            status=str(payload.get("status", "pending")),
            created_at=str(payload.get("created_at", "")),
            coverage_target=str(payload.get("coverage_target", "")),
            failure_context=str(payload.get("failure_context", "")),
            feedback=str(payload.get("feedback", "")),
            implementation_paths=list(payload.get("implementation_paths", [])),
            style=str(payload.get("style", "regression")),
            test_path=str(payload.get("test_path", "")),
            approved_at=payload.get("approved_at"),
            approved_by=payload.get("approved_by"),
            rejected_at=payload.get("rejected_at"),
            rejection_reason=payload.get("rejection_reason"),
        )


class TestSynthesizer:
    """Generate and manage Codex test proposals for refinement cycles."""

    __test__ = False

    _STYLE_TEMPLATES: Mapping[str, str] = {
        "branch": textwrap.dedent(
            """
            def {function_name}():
                '''Generated regression targeting uncovered branch.'''

                # spec: {spec_id}
                # coverage: {coverage_target}
                # implementation: {implementation_paths}
                raise AssertionError(
                    "Generated guard for {failure_context}. Update implementation before approving."
                )
            """
        ).strip(),
        "regression": textwrap.dedent(
            """
            def {function_name}():
                '''Auto-generated regression check.'''

                # spec: {spec_id}
                # coverage: {coverage_target}
                # implementation: {implementation_paths}
                result = None  # TODO: connect to implementation under test
                assert result is not None, "Generated test requires implementation hook"
            """
        ).strip(),
    }

    def __init__(
        self,
        *,
        repo_root: Path | str = Path("."),
        integration_root: Path | str | None = None,
        now: Callable[[], datetime] = _default_now,
        sandbox: CodexSandbox | None = None,
    ) -> None:
        self._repo_root = Path(repo_root)
        self._integration_root = (
            Path(integration_root)
            if integration_root is not None
            else self._repo_root / "integration"
        )
        self._sandbox = sandbox or CodexSandbox(root=self._repo_root)
        self._tests_root = self._repo_root / "tests" / "generated"
        self._pending_dir = self._tests_root / "pending"
        self._approved_dir = self._tests_root / "approved"
        self._rejected_dir = self._integration_root / "rejected_tests"
        self._log_path = self._integration_root / "test_cycle_log.jsonl"
        self._style_stats_path = self._integration_root / "test_style_stats.json"
        self._now = now

        for directory in (
            self._integration_root,
            self._tests_root,
            self._pending_dir,
            self._approved_dir,
            self._rejected_dir,
        ):
            self._sandbox._require_writable(directory)
            directory.mkdir(parents=True, exist_ok=True)

        for package_dir in (self._tests_root, self._approved_dir):
            init_file = package_dir / "__init__.py"
            if not init_file.exists():
                self._sandbox.commit_text(init_file, "\n", approved=True)

    # ------------------------------------------------------------------
    # Public API
    def propose_tests(
        self,
        spec_id: str,
        *,
        failure_context: str,
        feedback: str,
        implementation_paths: Iterable[str],
        coverage_target: str,
        operator: str | None = None,
    ) -> list[TestProposal]:
        """Generate pending test proposals for the provided failure."""

        timestamp = self._now().isoformat()
        slug = _slugify(spec_id)
        style = self._select_style(coverage_target)
        function_name = f"test_{slug}_{self._next_index(slug)}"
        filename = f"{function_name}.py.tmpl"
        pending_path = self._pending_dir / filename
        template = self._STYLE_TEMPLATES.get(style, self._STYLE_TEMPLATES["regression"])
        body = template.format(
            function_name=function_name,
            spec_id=spec_id,
            coverage_target=coverage_target or "unspecified",
            implementation_paths=", ".join(sorted(set(implementation_paths))) or "(unknown)",
            failure_context=failure_context,
        )
        header = textwrap.dedent(
            f"""
            '''Generated test proposal for {spec_id}.'''

            # operator: {operator or "codex"}
            # feedback: {feedback}
            # failure: {failure_context}
            # coverage_target: {coverage_target or "unspecified"}
            """
        ).strip()
        payload = f"{header}\n\n{body}\n"
        self._sandbox.commit_text(pending_path, payload, approved=True)

        proposal = TestProposal(
            proposal_id=f"{slug}-{timestamp.replace(':', '').replace('-', '')}",
            spec_id=spec_id,
            status="pending",
            created_at=timestamp,
            coverage_target=coverage_target,
            failure_context=failure_context,
            feedback=feedback,
            implementation_paths=list(implementation_paths),
            style=style,
            test_path=str(pending_path.relative_to(self._repo_root)),
        )
        self._write_proposal(self._pending_dir / f"{proposal.proposal_id}.json", proposal)
        self._log_action(
            "test_proposed",
            spec_id,
            operator=operator,
            metadata={
                "proposal_id": proposal.proposal_id,
                "coverage_target": coverage_target,
                "style": style,
                "test_path": proposal.test_path,
            },
        )
        return [proposal]

    def approve(
        self,
        proposal_id: str,
        *,
        operator: str,
        edit: Callable[[str], str] | str | None = None,
    ) -> TestProposal:
        """Approve a pending test proposal and activate it in the suite."""

        proposal = self._load_proposal(self._pending_dir, proposal_id)
        if proposal is None:
            raise FileNotFoundError(f"Test proposal {proposal_id} not found")

        template_path = self._repo_root / proposal.test_path
        content = template_path.read_text(encoding="utf-8")
        if isinstance(edit, str):
            content = edit
        elif callable(edit):
            content = edit(content)

        approved_path = self._approved_dir / template_path.name.replace(".py.tmpl", ".py")
        self._sandbox.commit_text(approved_path, content, approved=True)
        template_path.unlink(missing_ok=True)

        timestamp = self._now().isoformat()
        proposal.status = "approved"
        proposal.approved_at = timestamp
        proposal.approved_by = operator
        proposal.test_path = str(approved_path.relative_to(self._repo_root))

        self._write_proposal(self._approved_dir / f"{proposal.proposal_id}.json", proposal)
        self._delete_proposal(self._pending_dir, proposal_id)
        self._increment_style_stat(proposal.style, approved=True, proposed=False)
        self._log_action(
            "test_approved",
            proposal.spec_id,
            operator=operator,
            metadata={
                "proposal_id": proposal.proposal_id,
                "test_path": proposal.test_path,
            },
        )
        return proposal

    def reject(
        self,
        proposal_id: str,
        *,
        operator: str,
        reason: str,
    ) -> TestProposal:
        """Archive a pending proposal under the rejected tests ledger."""

        proposal = self._load_proposal(self._pending_dir, proposal_id)
        if proposal is None:
            raise FileNotFoundError(f"Test proposal {proposal_id} not found")

        template_path = self._repo_root / proposal.test_path
        archived_path = self._rejected_dir / template_path.name
        self._sandbox.commit_text(
            archived_path, template_path.read_text(encoding="utf-8"), approved=True
        )
        template_path.unlink(missing_ok=True)

        timestamp = self._now().isoformat()
        proposal.status = "rejected"
        proposal.rejected_at = timestamp
        proposal.rejection_reason = reason
        proposal.test_path = str(archived_path.relative_to(self._repo_root))

        self._write_proposal(self._rejected_dir / f"{proposal.proposal_id}.json", proposal)
        self._delete_proposal(self._pending_dir, proposal_id)
        self._log_action(
            "test_rejected",
            proposal.spec_id,
            operator=operator,
            metadata={
                "proposal_id": proposal.proposal_id,
                "reason": reason,
            },
        )
        return proposal

    def pending(self, *, spec_id: str | None = None) -> list[TestProposal]:
        return self._read_proposals(self._pending_dir, spec_id)

    def approved(self, *, spec_id: str | None = None) -> list[TestProposal]:
        return self._read_proposals(self._approved_dir, spec_id)

    def approved_test_paths(self, *, spec_id: str | None = None) -> list[Path]:
        proposals = self.approved(spec_id=spec_id)
        paths: list[Path] = []
        for proposal in proposals:
            if proposal.test_path:
                paths.append(self._repo_root / proposal.test_path)
        return paths

    def log_action(
        self,
        action: str,
        spec_id: str,
        *,
        operator: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self._log_action(action, spec_id, operator=operator, metadata=metadata)

    # ------------------------------------------------------------------
    # Internal helpers
    def _write_proposal(self, path: Path, proposal: TestProposal) -> None:
        self._sandbox.commit_json(path, proposal.to_dict(), approved=True)

    def _delete_proposal(self, directory: Path, proposal_id: str) -> None:
        json_path = directory / f"{proposal_id}.json"
        if json_path.exists():
            json_path.unlink()

    def _load_proposal(self, directory: Path, proposal_id: str) -> TestProposal | None:
        json_path = directory / f"{proposal_id}.json"
        if not json_path.exists():
            return None
        data = json.loads(json_path.read_text(encoding="utf-8"))
        return TestProposal.from_dict(data)

    def _read_proposals(
        self, directory: Path, spec_id: str | None = None
    ) -> list[TestProposal]:
        proposals: list[TestProposal] = []
        for json_path in sorted(directory.glob("*.json")):
            data = json.loads(json_path.read_text(encoding="utf-8"))
            proposal = TestProposal.from_dict(data)
            if spec_id and proposal.spec_id != spec_id:
                continue
            proposals.append(proposal)
        return proposals

    def _log_action(
        self,
        action: str,
        spec_id: str,
        *,
        operator: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if WET_RUN_ENABLED:
            return
        payload: MutableMapping[str, Any] = {
            "timestamp": self._now().isoformat(),
            "spec_id": spec_id,
            "action": action,
        }
        if operator:
            payload["operator"] = operator
        if metadata:
            payload["metadata"] = dict(metadata)
        self._sandbox.append_jsonl(self._log_path, payload, approved=True)

    def _load_style_stats(self) -> dict[str, dict[str, int]]:
        if not self._style_stats_path.exists():
            return {}
        data = json.loads(self._style_stats_path.read_text(encoding="utf-8"))
        return {key: dict(value) for key, value in data.items()}

    def _save_style_stats(self, stats: Mapping[str, Mapping[str, int]]) -> None:
        self._sandbox.commit_json(self._style_stats_path, stats, approved=True)

    def _increment_style_stat(
        self, style: str, *, approved: bool = False, proposed: bool = True
    ) -> None:
        stats = self._load_style_stats()
        entry = stats.setdefault(style, {"approved": 0, "proposed": 0})
        if proposed:
            entry["proposed"] = entry.get("proposed", 0) + 1
        if approved:
            entry["approved"] = entry.get("approved", 0) + 1
        self._save_style_stats(stats)

    def _select_style(self, coverage_target: str) -> str:
        stats = self._load_style_stats()
        if stats:
            preferred = max(stats.items(), key=lambda item: item[1].get("approved", 0))[0]
            if stats[preferred].get("approved", 0) > 0:
                self._increment_style_stat(preferred)
                return preferred
        normalized = (coverage_target or "").lower()
        if "branch" in normalized or "path" in normalized:
            style = "branch"
        else:
            style = "regression"
        self._increment_style_stat(style)
        return style

    def _next_index(self, slug: str) -> int:
        counter = 1
        prefix = f"test_{slug}_"
        for path in self._pending_dir.glob("test_*.py.tmpl"):
            name = path.stem
            if name.startswith(prefix) and name[len(prefix) :].isdigit():
                counter = max(counter, int(name[len(prefix) :]) + 1)
        for path in self._approved_dir.glob("test_*.py"):
            name = path.stem
            if name.startswith(prefix) and name[len(prefix) :].isdigit():
                counter = max(counter, int(name[len(prefix) :]) + 1)
        return counter


class TestCycleManager:
    """Coordinate Codex refinement loops with synthesized tests."""

    __test__ = False

    def __init__(
        self,
        *,
        implementor: Implementor | None = None,
        refiner: Refiner | None = None,
        synthesizer: TestSynthesizer | None = None,
        run_tests: Callable[[Iterable[Path]], bool] | None = None,
    ) -> None:
        self._implementor = implementor or Implementor()
        self._refiner = refiner or Refiner(implementor=self._implementor)
        self._synthesizer = synthesizer or TestSynthesizer()
        self._run_tests = run_tests or (lambda paths: True)

    # ------------------------------------------------------------------
    def propose_from_failure(
        self,
        spec_id: str,
        *,
        failure: str,
        feedback: str,
        coverage_target: str,
        implementation_paths: Iterable[str],
        operator: str | None = None,
    ) -> list[TestProposal]:
        return self._synthesizer.propose_tests(
            spec_id,
            failure_context=failure,
            feedback=feedback,
            implementation_paths=implementation_paths,
            coverage_target=coverage_target,
            operator=operator,
        )

    def run_round(
        self,
        spec_id: str,
        *,
        operator: str,
        change_summary: str,
        failure: str,
        transform: RefinementTransform | None = None,
        existing_tests: Iterable[Path | str] | None = None,
        halt: bool = False,
    ) -> dict[str, Any]:
        if halt:
            self._synthesizer.log_action(
                "cycle_halted", spec_id, operator=operator, metadata={"reason": "operator_halt"}
            )
            return {"status": "halted"}

        record = self._safe_record(spec_id)
        if record and record.final_rejected:
            self._synthesizer.log_action(
                "cycle_blocked",
                spec_id,
                operator=operator,
                metadata={"reason": "final_rejected"},
            )
            return {"status": "final_rejected"}

        pending = self._synthesizer.pending(spec_id=spec_id)
        if pending:
            raise RuntimeError("Pending tests require operator approval before execution")

        approved_paths = self._synthesizer.approved_test_paths(spec_id=spec_id)
        collected: list[Path] = []
        for entry in existing_tests or []:
            collected.append(Path(entry))
        collected.extend(approved_paths)

        self._synthesizer.log_action(
            "tests_triggered",
            spec_id,
            operator=operator,
            metadata={"tests": [str(path) for path in collected]},
        )
        passed = self._run_tests(collected)
        if passed:
            self._synthesizer.log_action("cycle_passed", spec_id, operator=operator)
            return {"status": "passed", "tests": collected}

        version = self._refiner.refine(
            spec_id,
            failure=failure,
            change_summary=change_summary,
            operator=operator,
            transform=transform,
        )
        self._synthesizer.log_action(
            "refinement_generated",
            spec_id,
            operator=operator,
            metadata={
                "version_id": version.version_id,
                "parent_version": version.parent_id,
            },
        )
        return {
            "status": "refined",
            "version_id": version.version_id,
            "tests": collected,
        }

    # ------------------------------------------------------------------
    def _safe_record(self, spec_id: str) -> ImplementationRecord | None:
        try:
            return self._implementor.load_record(spec_id)
        except FileNotFoundError:
            return None


__all__ = ["TestSynthesizer", "TestCycleManager", "TestProposal"]
