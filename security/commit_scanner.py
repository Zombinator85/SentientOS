from __future__ import annotations

import ast
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .threat_model import ThreatModel


@dataclass(slots=True)
class Finding:
    file: Path
    lineno: int
    pattern: str
    severity: str
    message: str
    context: str

    def to_dict(self) -> dict[str, object]:
        return {
            "file": str(self.file),
            "lineno": self.lineno,
            "pattern": self.pattern,
            "severity": self.severity,
            "message": self.message,
            "context": self.context,
        }


_RISKY_CALLS = {
    "subprocess.call": "shell interaction",
    "subprocess.Popen": "shell interaction",
    "subprocess.run": "shell interaction",
    "os.system": "shell interaction",
    "os.popen": "shell interaction",
    "eval": "dynamic execution",
    "exec": "dynamic execution",
    "pickle.loads": "unsafe deserialization",
    "yaml.load": "unsafe yaml load",
    "requests.get": "network request",
    "requests.post": "network request",
    "socket.socket": "raw socket",
}


_PRIVILEGE_GATES = (
    "require_admin_banner",
    "require_lumos_approval",
    "require_sanctuary_privilege",
)


def _collect_changed_files(root: Path) -> List[Path]:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return []
    paths: List[Path] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        candidate = line[3:].strip()
        if candidate.endswith(".py"):
            paths.append(root / candidate)
    return paths


def _resolve_target_files(root: Path, changed_only: bool) -> List[Path]:
    if changed_only:
        files = _collect_changed_files(root)
        if files:
            return files
    return sorted(root.glob("**/*.py"))


def _get_call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return f"{_get_call_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Name):
        return node.id
    return ""


class _SecurityVisitor(ast.NodeVisitor):
    def __init__(self, filename: Path, source: str):
        self.filename = filename
        self.source = source
        self.lines = source.splitlines()
        self.findings: List[Finding] = []
        lowered = source
        self.has_gate = any(token in lowered for token in _PRIVILEGE_GATES)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        name = _get_call_name(node.func)
        reason = _RISKY_CALLS.get(name)
        if reason:
            severity = "medium"
            if reason in {"shell interaction", "dynamic execution", "unsafe deserialization"}:
                severity = "high"
            if reason == "network request":
                severity = "medium-high"
            if reason == "raw socket":
                severity = "medium"
            if not self.has_gate:
                severity = f"{severity}+"
            context = self._context_line(node.lineno)
            message = self._build_message(name, node)
            self.findings.append(
                Finding(
                    file=self.filename,
                    lineno=node.lineno,
                    pattern=name,
                    severity=severity,
                    message=message,
                    context=context,
                )
            )
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:  # noqa: N802
        for item in node.items:
            ctx = item.context_expr
            if isinstance(ctx, ast.Call) and _get_call_name(ctx.func) == "open":
                if len(ctx.args) >= 2:
                    mode_arg = ctx.args[1]
                    if isinstance(mode_arg, ast.Str) and "w" in mode_arg.s:
                        if not self.has_gate:
                            context = self._context_line(ctx.lineno)
                            self.findings.append(
                                Finding(
                                    file=self.filename,
                                    lineno=ctx.lineno,
                                    pattern="open",
                                    severity="medium",
                                    message="File opened for writing without privilege gate.",
                                    context=context,
                                )
                            )
        self.generic_visit(node)

    def _context_line(self, lineno: int) -> str:
        if 1 <= lineno <= len(self.lines):
            return self.lines[lineno - 1].strip()
        return ""

    def _build_message(self, name: str, node: ast.Call) -> str:
        if name.startswith("subprocess"):
            shell_kw = next((kw for kw in node.keywords if kw.arg == "shell"), None)
            if shell_kw and isinstance(shell_kw.value, ast.Constant) and shell_kw.value.value is True:
                return "Subprocess invoked with shell=True; ensure sanitized inputs."
            return "Subprocess call detected; confirm arguments are validated."
        if name == "os.system":
            return "os.system call detected; prefer subprocess with explicit arguments."
        if name in {"eval", "exec"}:
            return "Dynamic execution detected; review input sources."
        if name == "pickle.loads":
            return "pickle.loads used; ensure data comes from trusted source."
        if name == "yaml.load":
            for kw in node.keywords:
                if kw.arg == "Loader":
                    break
            else:
                return "yaml.load without Loader; switch to safe loader."
        if name.startswith("requests"):
            verify_kw = next((kw for kw in node.keywords if kw.arg == "verify"), None)
            if verify_kw and isinstance(verify_kw.value, ast.Constant) and not verify_kw.value.value:
                return "requests call disables TLS verification; review justification."
            return "requests call detected; ensure threat model covers outbound HTTP."
        if name == "socket.socket":
            return "Socket usage detected; enforce network daemon policies."
        return f"Review call to {name}."


def scan_repository(root: Path, threat_model: ThreatModel, *, changed_only: bool = True) -> List[Finding]:
    files = _resolve_target_files(root, changed_only=changed_only)
    findings: List[Finding] = []
    for path in files:
        try:
            source = path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            continue
        visitor = _SecurityVisitor(path, source)
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            findings.append(
                Finding(
                    file=path,
                    lineno=exc.lineno or 0,
                    pattern="syntax_error",
                    severity="high",
                    message=f"Unable to parse Python file: {exc}",
                    context="",
                )
            )
            continue
        visitor.visit(tree)
        findings.extend(visitor.findings)
    return findings
