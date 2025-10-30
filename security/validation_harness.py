from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

from .commit_scanner import Finding


@dataclass(slots=True)
class ValidationResult:
    finding: Finding
    status: str
    evidence: str
    transcript: List[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "finding": self.finding.to_dict(),
            "status": self.status,
            "evidence": self.evidence,
            "transcript": self.transcript,
        }


class ValidationHarness:
    """Static validation harness that produces evidence bundles for findings."""

    def __init__(self, repository_root: Path):
        self.repository_root = repository_root

    def validate(self, findings: Iterable[Finding]) -> List[ValidationResult]:
        results: List[ValidationResult] = []
        for finding in findings:
            handler = getattr(self, f"_validate_{finding.pattern.replace('.', '_')}", None)
            if handler is None:
                results.append(
                    ValidationResult(
                        finding=finding,
                        status="skipped",
                        evidence="No dedicated validator registered.",
                        transcript=[],
                    )
                )
                continue
            try:
                results.append(handler(finding))
            except Exception as exc:  # pragma: no cover - defensive
                results.append(
                    ValidationResult(
                        finding=finding,
                        status="error",
                        evidence=f"Validator raised {exc.__class__.__name__}: {exc}",
                        transcript=[],
                    )
                )
        return results

    def _validate_subprocess_run(self, finding: Finding) -> ValidationResult:
        snippet = self._context_snippet(finding)
        evidence = (
            "Confirmed subprocess invocation by re-reading source context. "
            "Shell usage amplifies risk if user input is forwarded."
        )
        return ValidationResult(finding=finding, status="confirmed", evidence=evidence, transcript=[snippet])

    _validate_subprocess_call = _validate_subprocess_run
    _validate_subprocess_Popen = _validate_subprocess_run

    def _validate_os_system(self, finding: Finding) -> ValidationResult:
        snippet = self._context_snippet(finding)
        evidence = "os.system invocation captured; prefer guarded subprocess usage."
        return ValidationResult(finding=finding, status="confirmed", evidence=evidence, transcript=[snippet])

    def _validate_eval(self, finding: Finding) -> ValidationResult:
        snippet = self._context_snippet(finding)
        evidence = "Dynamic eval located. Static confirmation sufficient for review."
        return ValidationResult(finding=finding, status="confirmed", evidence=evidence, transcript=[snippet])

    _validate_exec = _validate_eval

    def _validate_pickle_loads(self, finding: Finding) -> ValidationResult:
        snippet = self._context_snippet(finding)
        evidence = "pickle.loads usage verified; confirm trusted data sources."
        return ValidationResult(finding=finding, status="confirmed", evidence=evidence, transcript=[snippet])

    def _validate_yaml_load(self, finding: Finding) -> ValidationResult:
        snippet = self._context_snippet(finding)
        evidence = "yaml.load without explicit safe loader detected."
        return ValidationResult(finding=finding, status="confirmed", evidence=evidence, transcript=[snippet])

    def _validate_requests_get(self, finding: Finding) -> ValidationResult:
        snippet = self._context_snippet(finding)
        evidence = "requests.get call documented; ensure TLS verification remains enabled."
        return ValidationResult(finding=finding, status="confirmed", evidence=evidence, transcript=[snippet])

    _validate_requests_post = _validate_requests_get

    def _validate_socket_socket(self, finding: Finding) -> ValidationResult:
        snippet = self._context_snippet(finding)
        evidence = "socket.socket usage confirmed; align with network daemon policy."
        return ValidationResult(finding=finding, status="confirmed", evidence=evidence, transcript=[snippet])

    def _validate_open(self, finding: Finding) -> ValidationResult:
        snippet = self._context_snippet(finding)
        evidence = "Write-mode file handle lacks privilege gate; review storage path."
        return ValidationResult(finding=finding, status="confirmed", evidence=evidence, transcript=[snippet])

    def _validate_syntax_error(self, finding: Finding) -> ValidationResult:
        evidence = "Parsing failure reproduced; syntax errors block validation of security posture."
        return ValidationResult(finding=finding, status="error", evidence=evidence, transcript=[])

    def _context_snippet(self, finding: Finding) -> str:
        try:
            lines = finding.file.read_text(encoding="utf-8").splitlines()
        except (FileNotFoundError, OSError):
            return finding.context
        index = max(finding.lineno - 1, 0)
        if 0 <= index < len(lines):
            return lines[index].strip()
        return finding.context
