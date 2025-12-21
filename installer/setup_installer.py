from __future__ import annotations
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()


import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from cathedral_const import PUBLIC_LOG, log_json
from hf_intake import manifest as manifest_module
from logging_config import get_log_dir
from sentient_banner import print_banner, print_closing


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOCK_FILE = REPO_ROOT / "requirements-lock.txt"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
ENV_FILE = REPO_ROOT / ".env"
SAMPLES_DIR = REPO_ROOT / "installer" / "example_data"
DEFAULT_MANIFEST = REPO_ROOT / "manifests" / "manifest-v1.json"
INSTALL_LOG = get_log_dir() / "installer.log"


def _log(event: str, status: str, note: str = "") -> None:
    """Write an install event to the log."""
    log_json(
        INSTALL_LOG,
        {
            "time": time.time(),
            "event": event,
            "status": status,
            "note": note,
        },
    )


def check_python_version() -> None:
    if sys.version_info < (3, 10):
        msg = "Python 3.10+ required"
        print(msg)
        _log("python_version", "failed", msg)
        sys.exit(1)
    print(f"Python version: {sys.version.split()[0]}")
    _log("python_version", "ok")


def ensure_logs() -> None:
    """Create required log directories."""
    log_dir = get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    PUBLIC_LOG.parent.mkdir(parents=True, exist_ok=True)
    _log("ensure_logs", "ok")


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_manifest_artifacts(manifest_path: Path, *, escrow_root: Path | None = None) -> list[Path]:
    """Verify escrowed artifacts against the manifest without network I/O."""

    manifest_module.validate_manifest(manifest_path)
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    models = data.get("models") or []
    if not models:
        raise RuntimeError("manifest contains no models")
    escrow_base = escrow_root or manifest_path.parent
    verified: list[Path] = []
    for model in models:
        artifact = model.get("artifact", {})
        escrow_rel = artifact.get("escrow_path")
        sha = artifact.get("sha256")
        if not escrow_rel or not sha:
            raise RuntimeError("manifest entry missing escrow_path or sha256")
        escrow_path = (escrow_base / escrow_rel).resolve()
        if not escrow_path.exists():
            raise RuntimeError(f"escrow artifact missing: {escrow_path}")
        digest = _hash_file(escrow_path)
        if digest != sha:
            raise RuntimeError(f"checksum mismatch for {escrow_path}")
        verified.append(escrow_path)
    return verified


def install_dependencies(*, lock_path: Path = DEFAULT_LOCK_FILE) -> None:
    if not lock_path.exists():
        raise RuntimeError(f"Lock file not found: {lock_path}")
    lines = [ln.strip() for ln in lock_path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")]
    if not all("--hash=" in ln or "--hash" in ln for ln in lines):
        raise RuntimeError("Lock file must include hashes for deterministic install")
    print("Installing pinned Python dependencies (opt-in)...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(lock_path)])
        _log("dependencies", "ok", f"lock={lock_path.name}")
    except subprocess.CalledProcessError as e:
        _log("dependencies", "failed", str(e))
        raise


def copy_samples() -> None:
    dst = REPO_ROOT / "examples"
    try:
        if not dst.exists():
            shutil.copytree(SAMPLES_DIR, dst)
        else:
            for item in SAMPLES_DIR.iterdir():
                target = dst / item.name
                if not target.exists():
                    if item.is_dir():
                        shutil.copytree(item, target)
                    else:
                        shutil.copy2(item, target)
        _log("copy_samples", "ok")
    except Exception as e:
        _log("copy_samples", "failed", str(e))
        raise


def create_env() -> None:
    try:
        if not ENV_FILE.exists() and ENV_EXAMPLE.exists():
            shutil.copy2(ENV_EXAMPLE, ENV_FILE)
        _log("create_env", "ok")
    except Exception as e:
        _log("create_env", "failed", str(e))
        raise


def check_microphone() -> None:
    try:
        import sounddevice as sd  # type: ignore[import-untyped]  # optional audio dependency

        devices = sd.query_devices()
        if not devices:
            print("No microphone devices detected.")
        else:
            print("Available audio devices:")
            for idx, d in enumerate(devices):
                if d.get("max_input_channels", 0) > 0:
                    print(f"  [{idx}] {d['name']}")
        _log("microphone", "ok")
    except Exception as e:
        print(f"Microphone check failed: {e}")
        _log("microphone", "failed", str(e))


def smoke_test() -> None:
    """Run a quick verification of the environment."""

    print("Running smoke test...")
    try:
        subprocess.check_call([sys.executable, "verify_audits.py", "--help"])
        subprocess.call([sys.executable, "-m", "pytest", "-q"])  # allow failures
        log_json(PUBLIC_LOG, {"event": "install_test", "status": "ok"})
        print("log_json test passed.")
        _log("smoke_test", "ok")
    except Exception as e:  # pragma: no cover - environment dependent
        print(f"Smoke test failed: {e}")
        _log("smoke_test", "failed", str(e))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SentientOS installer")
    parser.add_argument(
        "--with-avatar",
        action="store_true",
        help="Install the Godot-based avatar runtime and demo scene",
    )
    parser.add_argument(
        "--install-deps",
        action="store_true",
        help="Explicitly install pinned dependencies from the lock file",
    )
    parser.add_argument(
        "--lock-file",
        default=str(DEFAULT_LOCK_FILE),
        help="Path to the pinned dependency lock file",
    )
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="Path to the manifest used for offline verification",
    )
    parser.add_argument(
        "--escrow-root",
        default=str(REPO_ROOT),
        help="Base directory for escrowed artifacts referenced by the manifest",
    )
    return parser.parse_args(argv)


def install_avatar_runtime() -> None:
    hook = REPO_ROOT / "install_godot_avatar_runtime.sh"
    if not hook.exists():
        print("Avatar runtime hook not found; skipping.")
        _log("avatar_runtime", "missing")
        return

    print("Installing Godot avatar runtime...")
    try:
        subprocess.check_call(["bash", str(hook), str(REPO_ROOT)])
        launcher = REPO_ROOT / "tools" / "avatar_runtime" / "avatar-demo.sh"
        if launcher.exists():
            print(f"Avatar demo launcher available at {launcher}")
        _log("avatar_runtime", "ok")
    except subprocess.CalledProcessError as exc:
        _log("avatar_runtime", "failed", str(exc))
        raise


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    print_banner()
    check_python_version()
    ensure_logs()

    manifest_path = Path(args.manifest)
    escrow_root = Path(args.escrow_root)
    verify_manifest_artifacts(manifest_path, escrow_root=escrow_root)

    print("SentientOS setup starting (offline, deterministic)...")
    if args.install_deps:
        install_dependencies(lock_path=Path(args.lock_file))
    copy_samples()
    create_env()
    if args.with_avatar:
        install_avatar_runtime()
    check_microphone()
    smoke_test()
    print("Setup complete. Launching onboarding dashboard...")
    try:
        import onboarding_dashboard  # type: ignore[import-untyped]  # optional GUI

        onboarding_dashboard.launch()
    except Exception:
        print("onboarding_dashboard not available. Setup finished.")
    print("INSTALLATION COMPLETE. You may now launch the main script.")
    _log("complete", "ok")
    print_closing()


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception as e:  # pragma: no cover
        _log("complete", "failed", str(e))
        raise
