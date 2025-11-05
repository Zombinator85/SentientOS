import json
import os
import platform
import subprocess
import sys
from pathlib import Path


LOG_BASE = Path(os.getenv("SENTIENTOS_LOG_DIR") or "logs")
LOG_FILE = LOG_BASE / "gpu_autosetup.log"
BACKEND_FILE = LOG_BASE / "gpu_backend.json"


def _log(message: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as handle:
        handle.write(message + "\n")


def detect_gpu() -> tuple[str, str]:
    try:
        out = subprocess.check_output([
            "nvidia-smi",
            "--query-gpu=name",
            "--format=csv,noheader",
        ], stderr=subprocess.STDOUT)
        decoded = out.decode().strip()
        if decoded:
            print(f"[SentientOS] Detected NVIDIA GPU: {decoded}")
            _log(f"gpu=NVIDIA:{decoded}")
            return "cuda", f"{decoded} (CUDA)"
    except Exception:
        pass
    try:
        out = subprocess.check_output(["rocm-smi"], stderr=subprocess.STDOUT)
        decoded = out.decode()
        if "Radeon" in decoded:
            print("[SentientOS] Detected AMD GPU via ROCm")
            _log("gpu=AMD:Radeon")
            return "rocm", "AMD Radeon (ROCm)"
    except Exception:
        pass
    if "Apple" in platform.platform():
        print("[SentientOS] Detected Apple platform (Metal backend)")
        _log("gpu=Apple:Metal")
        return "metal", "Apple Silicon (Metal)"
    print("[SentientOS] No discrete GPU detected; defaulting to CPU backend")
    _log("gpu=CPU")
    return "cpu", "CPU"


def install_llama_cpp(backend: str) -> None:
    urls = {
        "cuda": "https://abetlen.github.io/llama-cpp-python/whl/cu124",
        "rocm": "https://abetlen.github.io/llama-cpp-python/whl/rocm5",
        "metal": "https://abetlen.github.io/llama-cpp-python/whl/metal",
        "cpu": "https://pypi.org/simple",
    }
    print(f"[SentientOS] Installing llama-cpp-python for backend: {backend}")
    _log(f"llama_cpp_backend={backend}")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "llama-cpp-python",
            "--extra-index-url",
            urls[backend],
        ],
        check=False,
    )


if __name__ == "__main__":
    _log(f"platform={platform.platform()}")
    _log(f"python={sys.version.split()[0]}")
    backend, description = detect_gpu()
    BACKEND_FILE.parent.mkdir(parents=True, exist_ok=True)
    BACKEND_FILE.write_text(
        json.dumps({"backend": backend, "description": description}),
        encoding="utf-8",
    )
    install_llama_cpp(backend)
    print("[SentientOS] GPU setup complete. Restart daemon to apply.")
    print(f"[SentientOS] GPU Backend: {description}")
    print(f"[SentientOS] Environment headless: {os.getenv('SENTIENTOS_HEADLESS', '')}")
    print(f"[SentientOS] Auto-approve: {os.getenv('LUMOS_AUTO_APPROVE', '')}")
    _log(
        "env="
        + ",".join(
            f"{key}={os.getenv(key, '')}"
            for key in ("SENTIENTOS_HEADLESS", "LUMOS_AUTO_APPROVE")
        )
    )
