"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import shutil
from pathlib import Path


ENV_FILE = Path(".env")
ENV_EXAMPLE = Path(".env.example")


def check_gpu() -> bool:
    """Return True if torch reports a CUDA capable device."""
    try:
        import torch  # pragma: no cover - optional dependency
        return bool(getattr(torch, "cuda", None) and torch.cuda.is_available())
    except Exception:
        return False


def _update_env(key: str, value: str, env_path: Path = ENV_FILE) -> None:
    """Set or update a key=value pair in the given .env file."""
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    elif ENV_EXAMPLE.exists():
        lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    else:
        lines = []
    updated = False
    for i, ln in enumerate(lines):
        if ln.startswith(key + "="):
            lines[i] = f"{key}={value}"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def ensure_binary(name: str) -> None:
    """Raise FileNotFoundError if binary is missing."""
    if shutil.which(name) is None:
        raise FileNotFoundError(f"Required binary '{name}' not found in PATH")


def ensure_model(path: str) -> None:
    """Raise FileNotFoundError if the model path is set but missing."""
    if path and not Path(path).exists():
        raise FileNotFoundError(f"Required model not found: {path}")


def main() -> None:  # pragma: no cover - CLI
    gpu = check_gpu()
    mode = os.getenv("INFERENCE_MODE")
    if not gpu and not mode:
        choice = input(
            "GPU not detected. Use cloud inference instead? [y/N] "
        ).strip().lower()
        mode = "cloud" if choice.startswith("y") else "local"
        _update_env("INFERENCE_MODE", mode)
    elif gpu and not mode:
        mode = "local"
        _update_env("INFERENCE_MODE", mode)
    print(f"GPU available: {gpu}. Inference mode: {mode or 'unspecified'}")

    # Ensure core dependencies
    ensure_binary("ffmpeg")
    ensure_model(os.getenv("LOCAL_MODEL_PATH", ""))


if __name__ == "__main__":
    main()
