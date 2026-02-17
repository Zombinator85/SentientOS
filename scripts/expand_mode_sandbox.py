"""SentientOS Expand Sandbox
=================================

This module provides a CLI helper that lets SentientOS experiment with
"expand" style self-modification workflows **without** touching the live
repository.  Instead of relaxing the Covenant safeguards, the tool creates an
ephemeral sandbox directory, copies the current checkout into it, and executes
requested commands inside that safe bubble.  A summary of the results and the
diff created inside the sandbox are reported back to the operator for manual
review.

The design balances the desire for autonomy with the core project doctrine:

* Make changes as large as required to accomplish the objective, but keep them coherent, tested, and contract-validated.

* The original checkout remains untouched unless the operator explicitly
  applies the generated patch.
* Covenant paths (``vow/`` by default) are mirrored into the sandbox but kept
  read-only so tests can still reference them while preventing accidental
  edits.
* All actions are logged through structured status output that can be ingested
  by existing SentientOS observability tools.

Example usage::

    # Prepare a sandbox and run tests inside it
    python scripts/expand_mode_sandbox.py --run "python -m scripts.run_tests -q"

    # Execute a custom script and request a unified diff report
    python scripts/expand_mode_sandbox.py --run "python some_agent.py" \
        --show-diff

The sandbox directory is deleted when the command finishes unless
``--keep`` is provided.  Operators may then inspect the sandbox manually or
promote changes following the established blessing rituals.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Mapping, MutableMapping, Optional


DEFAULT_IMMUTABLE_PATHS = ("vow",)
DEFAULT_IGNORE_PATTERNS = (".git", "__pycache__", ".mypy_cache", "*.pyc")


class SandboxError(RuntimeError):
    """Raised when sandbox preparation or execution fails."""


@dataclass
class CommandResult:
    """Structured payload describing the outcome of a sandbox command."""

    args: List[str]
    returncode: int
    stdout: str
    stderr: str

    def to_dict(self) -> Mapping[str, object]:
        return {
            "args": self.args,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass
class Sandbox:
    """Context object that manages the sandbox lifecycle."""

    repo_root: Path
    keep: bool = False
    immutable_paths: Iterable[str] = DEFAULT_IMMUTABLE_PATHS
    ignore_patterns: Iterable[str] = DEFAULT_IGNORE_PATTERNS
    tmpdir: Optional[tempfile.TemporaryDirectory[str]] = field(default=None, init=False)
    sandbox_root: Optional[Path] = field(default=None, init=False)

    def __post_init__(self) -> None:
        if not self.repo_root.exists():
            raise SandboxError(f"Repository root {self.repo_root} does not exist")

    # -- Lifecycle -----------------------------------------------------
    def __enter__(self) -> "Sandbox":
        self.tmpdir = tempfile.TemporaryDirectory(prefix="sentientos-expand-")
        self.sandbox_root = Path(self.tmpdir.name) / "repo"
        self._copy_repo()
        self._initialise_git()
        self._protect_immutable_paths()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        if self.keep:
            return
        if self.tmpdir is not None:
            self.tmpdir.cleanup()

    # -- Internal helpers ---------------------------------------------
    def _copy_repo(self) -> None:
        assert self.sandbox_root is not None
        try:
            shutil.copytree(
                self.repo_root,
                self.sandbox_root,
                symlinks=True,
                ignore=shutil.ignore_patterns(*self.ignore_patterns),
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            raise SandboxError(f"Failed to copy repository: {exc}") from exc

    def _initialise_git(self) -> None:
        assert self.sandbox_root is not None
        self._run_checked(["git", "init"], cwd=self.sandbox_root)
        self._run_checked(["git", "add", "-A"], cwd=self.sandbox_root)
        # Using --allow-empty ensures we have a baseline even if nothing copies
        self._run_checked(
            ["git", "commit", "--allow-empty", "-m", "sandbox baseline"],
            cwd=self.sandbox_root,
        )

    def _protect_immutable_paths(self) -> None:
        assert self.sandbox_root is not None
        for rel in self.immutable_paths:
            path = self.sandbox_root / rel
            if path.exists():
                for subpath in path.rglob("*"):
                    if subpath.is_file():
                        subpath.chmod(0o444)
                path.chmod(0o555)

    # -- Public API ----------------------------------------------------
    def run(self, command: List[str], env: Optional[MutableMapping[str, str]] = None) -> CommandResult:
        if self.sandbox_root is None:
            raise SandboxError("Sandbox has not been prepared")
        proc = subprocess.run(
            command,
            cwd=self.sandbox_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        return CommandResult(command, proc.returncode, proc.stdout, proc.stderr)

    def diff(self) -> str:
        if self.sandbox_root is None:
            raise SandboxError("Sandbox has not been prepared")
        proc = subprocess.run(
            ["git", "diff", "--color=never"],
            cwd=self.sandbox_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode not in (0, 1):
            raise SandboxError(f"git diff failed: {proc.stderr.strip()}")
        return proc.stdout

    # -- Utility -------------------------------------------------------
    def _run_checked(self, args: List[str], *, cwd: Path) -> None:
        proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise SandboxError(
                f"Command {' '.join(args)} failed with {proc.returncode}: {proc.stderr.strip()}"
            )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run expand-mode commands inside a safe sandbox")
    parser.add_argument(
        "--run",
        metavar="CMD",
        required=True,
        help="Command to execute inside the sandbox",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep the sandbox directory for inspection",
    )
    parser.add_argument(
        "--show-diff",
        action="store_true",
        help="Print the git diff generated inside the sandbox",
    )
    parser.add_argument(
        "--immutable",
        nargs="*",
        default=list(DEFAULT_IMMUTABLE_PATHS),
        help="Relative paths that should be marked read-only in the sandbox",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON summary instead of plain text",
    )
    return parser.parse_args(argv)


def build_environment() -> MutableMapping[str, str]:
    env = os.environ.copy()
    # Signal to downstream scripts that we are running inside the safe expander.
    env.setdefault("SENTIENTOS_SANDBOX", "1")
    return env


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    env = build_environment()

    command = ["bash", "-lc", args.run]

    with Sandbox(
        repo_root=repo_root,
        keep=args.keep,
        immutable_paths=args.immutable,
    ) as sandbox:
        result = sandbox.run(command, env=env)
        payload = {
            "sandbox_root": str(sandbox.sandbox_root),
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

        if args.show_diff:
            payload["diff"] = sandbox.diff()

        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print("Sandbox root:", payload["sandbox_root"])
            print("Return code:", payload["returncode"])
            if result.stdout:
                print("--- stdout ---")
                print(result.stdout.rstrip())
            if result.stderr:
                print("--- stderr ---")
                print(result.stderr.rstrip())
            if args.show_diff:
                diff = payload.get("diff", "")
                if diff:
                    print("--- diff ---")
                    print(diff.rstrip())

        return 0 if result.returncode == 0 else result.returncode


if __name__ == "__main__":
    sys.exit(main())
