from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import argparse
import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Iterable, Sequence

LFS_POINTER_HEADER = b"version https://git-lfs.github.com/spec/v1"


def _default_model_path() -> Path:
    return (
        _repo_root()
        / "sentientos_data"
        / "models"
        / "mistral-7b"
        / "mistral-7b-instruct-v0.2.Q4_K_M.gguf"
    )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _is_lfs_pointer(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(len(LFS_POINTER_HEADER))
    except FileNotFoundError:
        return False
    return head == LFS_POINTER_HEADER


def _extract_archive(archive: Path, destination: Path, force: bool) -> Path:
    if _is_lfs_pointer(archive):
        raise SystemExit(
            "Git LFS payload for SentientOSsecondary.zip is missing. "
            "Run `git lfs pull` before extracting."
        )

    if destination.exists():
        if force:
            shutil.rmtree(destination)
        else:
            print(f"Destination {destination} already exists; skipping extraction.")
            return destination

    with zipfile.ZipFile(archive) as payload:
        members = [
            Path(info.filename)
            for info in payload.infolist()
            if info.filename and not info.filename.startswith("__MACOSX")
        ]
        roots = {parts[0] for parts in (m.parts for m in members) if parts}

        if len(roots) == 1:
            root_name = next(iter(roots))
            payload.extractall(archive.parent)
            extracted_root = archive.parent / root_name
            if extracted_root != destination:
                if destination.exists():
                    shutil.rmtree(destination)
                extracted_root.rename(destination)
        else:
            destination.mkdir(parents=True, exist_ok=True)
            payload.extractall(destination)

    print(f"Extracted SentientOSsecondary to {destination}")
    return destination


def _verify_structure(root: Path) -> None:
    server_cmake_candidates = [
        root / "llama.cpp" / "examples" / "server" / "CMakeLists.txt",
        root / "llama.cpp" / "tools" / "server" / "CMakeLists.txt",
    ]
    server_cmake = next((path for path in server_cmake_candidates if path.exists()), None)

    common_cmake = root / "llama.cpp" / "common" / "CMakeLists.txt"

    missing: list[str] = []
    if server_cmake is None:
        missing.append(str(server_cmake_candidates[0]))
    if not common_cmake.exists():
        missing.append(str(common_cmake))

    if missing:
        raise SystemExit(
            "SentientOSsecondary is missing expected build files:\n" + "\n".join(missing)
        )

    build_dir = root / "build"
    if not build_dir.exists():
        raise SystemExit(
            "SentientOSsecondary build directory is missing. "
            "Run the CUDA asset generation steps or refresh the archive."
        )

    print("SentientOSsecondary structure validated:")
    print(f"- llama.cpp root: {root / 'llama.cpp'}")
    print(f"- build directory: {build_dir}")
    if server_cmake is not None:
        print(f"- server CMake: {server_cmake}")
    print(f"- common CMake: {common_cmake}")


def _run_command(command: Sequence[object], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    rendered = " ".join(str(part) for part in command)
    print(f"$ {rendered}")
    try:
        subprocess.run([str(part) for part in command], cwd=cwd, env=env, check=True)
    except FileNotFoundError as exc:  # pragma: no cover - interactive guard
        raise SystemExit(f"Command not found: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:  # pragma: no cover - interactive guard
        raise SystemExit(
            f"Command failed with exit code {exc.returncode}: {rendered}"
        ) from exc


def _normalize_definitions(defines: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    for define in defines:
        if define.startswith("-D"):
            normalized.append(define)
        else:
            normalized.append(f"-D{define}")
    return normalized


def _run_cmake_build(root: Path, *, generator: str, arch: str, cmake_defines: Iterable[str], build_config: str, targets: list[str], skip_embed: bool) -> Path:
    if os.name != "nt":  # pragma: no cover - Windows-only workflow
        raise SystemExit("CMake build automation currently targets Windows hosts.")

    llama_root = root / "llama.cpp"
    build_dir = root / "build"

    configure_cmd: list[str] = [
        "cmake",
        "-S",
        str(llama_root),
        "-B",
        str(build_dir),
        "-G",
        generator,
    ]
    if arch:
        configure_cmd.extend(["-A", arch])

    default_defines = [
        "-DLLAMA_CUDA=ON",
        "-DLLAMA_CUBLAS=ON",
        "-DLLAMA_BUILD_SERVER=ON",
        "-DLLAMA_EMBED_SERVER=ON",
    ]
    configure_cmd.extend(default_defines)
    configure_cmd.extend(_normalize_definitions(cmake_defines))

    _run_command(configure_cmd)

    if not skip_embed:
        _run_command(
            [
                "cmake",
                "--build",
                str(build_dir),
                "--config",
                build_config,
                "--target",
                "server_embed",
            ]
        )

    build_cmd: list[str] = [
        "cmake",
        "--build",
        str(build_dir),
        "--config",
        build_config,
    ]
    if targets:
        build_cmd.extend(["--target", *targets])

    _run_command(build_cmd)
    return build_dir


def _poll_health(host: str, port: int, timeout: float) -> bool:
    url = f"http://{host}:{port}/health"
    request = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status == 200
    except urllib.error.URLError:
        return False


def _request_completion(host: str, port: int, *, prompt: str, n_predict: int, timeout: float) -> str:
    payload = json.dumps({
        "prompt": prompt,
        "n_predict": n_predict,
        "stream": False,
    }).encode("utf-8")

    request = urllib.request.Request(
        f"http://{host}:{port}/completion",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")

    data = json.loads(body)
    text: str | None = None

    if isinstance(data, dict):
        if isinstance(data.get("content"), str):
            text = data["content"]
        elif isinstance(data.get("completion"), str):
            text = data["completion"]
        elif isinstance(data.get("choices"), list) and data["choices"]:
            first_choice = data["choices"][0]
            if isinstance(first_choice, dict):
                maybe_text = first_choice.get("text")
                if isinstance(maybe_text, str):
                    text = maybe_text
                else:
                    message = first_choice.get("message")
                    if isinstance(message, dict):
                        maybe_content = message.get("content")
                        if isinstance(maybe_content, str):
                            text = maybe_content
                        else:
                            maybe_reasoning = message.get("reasoning_content")
                            if isinstance(maybe_reasoning, str):
                                text = maybe_reasoning

    if not text:
        raise SystemExit(
            "CUDA verification request succeeded but did not return any text content."
        )

    return text


def _verify_cuda_runtime(
    root: Path,
    *,
    build_config: str,
    model: Path,
    host: str,
    port: int,
    prompt: str,
    n_predict: int,
    threads: int,
    ctx_size: int,
    batch_size: int | None,
    gpu_layers: int | None,
    temperature: float | None,
    seed: int,
    timeout: int,
) -> None:
    if os.name != "nt":  # pragma: no cover - Windows-only workflow
        raise SystemExit("CUDA verification is only supported on Windows hosts.")

    if not model.exists():
        if _is_lfs_pointer(model):
            raise SystemExit(
                f"Model path points to a Git LFS placeholder: {model}. Run `git lfs pull`."
            )
        raise SystemExit(f"Model file not found: {model}")

    binary_dir = root / "build" / "bin" / build_config
    binary_candidates = [
        binary_dir / "llama-server.exe",
        binary_dir / "llama-server",
    ]
    server_binary = next((candidate for candidate in binary_candidates if candidate.exists()), None)
    if server_binary is None:
        raise SystemExit(
            "llama-server binary not found. Run with --build to compile the target first."
        )

    cmd: list[object] = [
        server_binary,
        "--host",
        host,
        "--port",
        port,
        "--no-webui",
        "--seed",
        seed,
    ]
    if threads:
        cmd.extend(["--threads", threads])
    if ctx_size:
        cmd.extend(["--ctx-size", ctx_size])
    if batch_size:
        cmd.extend(["--batch-size", batch_size])
    if gpu_layers is not None and gpu_layers >= 0:
        cmd.extend(["--n-gpu-layers", gpu_layers])
    if temperature is not None:
        cmd.extend(["--temp", temperature])
    cmd.extend(["--model", model])

    print("Launching llama-server for CUDA verification...")

    with subprocess.Popen(
        [str(part) for part in cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    ) as proc:
        assert proc.stdout is not None

        log_queue: queue.Queue[str] = queue.Queue()
        stop_event = threading.Event()

        def _pump_stdout() -> None:
            try:
                for line in proc.stdout:
                    log_queue.put(line.rstrip())
                    if stop_event.is_set():
                        continue
            finally:
                proc.stdout.close()

        reader = threading.Thread(target=_pump_stdout, name="llama-server-log", daemon=True)
        reader.start()

        log_lines: list[str] = []
        seen_cuda = False

        def _drain_logs() -> None:
            nonlocal seen_cuda
            while True:
                try:
                    line = log_queue.get_nowait()
                except queue.Empty:
                    break
                log_lines.append(line)
                print(f"[llama-server] {line}")
                lowered = line.lower()
                if "ggml_init_cublas" in lowered or "ggml_cuda" in lowered:
                    seen_cuda = True

        deadline = time.time() + timeout
        ready = False

        try:
            while time.time() < deadline:
                _drain_logs()
                if _poll_health(host, port, timeout=1.0):
                    ready = True
                    break
                if proc.poll() is not None:
                    _drain_logs()
                    raise SystemExit(
                        "llama-server exited before reporting readiness."
                    )
                time.sleep(0.5)

            _drain_logs()

            if not ready:
                raise SystemExit(
                    "Timed out waiting for llama-server to become ready."
                )

            if not seen_cuda:
                raise SystemExit(
                    "CUDA runtime did not initialise (ggml_init_cublas() was not observed in the logs)."
                )

            completion = _request_completion(
                host,
                port,
                prompt=prompt,
                n_predict=n_predict,
                timeout=float(timeout),
            )

            print("CUDA verification request completed successfully.")
            preview = completion[:512]
            print(f"Sample output (first {len(preview)} characters):\n{preview}")
        finally:
            stop_event.set()
            if proc.poll() is None:
                try:
                    if os.name == "nt" and hasattr(signal, "CTRL_BREAK_EVENT"):
                        proc.send_signal(signal.CTRL_BREAK_EVENT)
                        proc.wait(timeout=5)
                    if proc.poll() is None:
                        proc.terminate()
                except ValueError:
                    proc.terminate()
                except PermissionError:
                    proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            reader.join(timeout=5)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate or extract the SentientOSsecondary build payload."
    )
    parser.add_argument(
        "--extract",
        action="store_true",
        help="Extract the Git LFS archive before running validation.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-extract even if the destination already exists.",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=_repo_root() / "SentientOSsecondary",
        help="Override the extraction directory (defaults to SentientOSsecondary/).",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Configure and build the llama-server target after validation.",
    )
    parser.add_argument(
        "--cmake-generator",
        default="Visual Studio 17 2022",
        help="CMake generator to use when --build is specified.",
    )
    parser.add_argument(
        "--cmake-arch",
        default="x64",
        help="Architecture passed to CMake via -A when --build is specified.",
    )
    parser.add_argument(
        "--cmake-define",
        dest="cmake_defines",
        action="extend",
        nargs="+",
        default=[],
        help="Additional -D definitions forwarded to CMake configuration.",
    )
    parser.add_argument(
        "--build-config",
        default="Release",
        help="Build configuration passed to cmake --build (default: Release).",
    )
    parser.add_argument(
        "--build-target",
        dest="build_targets",
        action="extend",
        nargs="+",
        default=[],
        help="Targets forwarded to cmake --build. Defaults to llama-server and llama.",
    )
    parser.add_argument(
        "--skip-embed",
        action="store_true",
        help="Skip invoking the server_embed target before building other targets.",
    )
    parser.add_argument(
        "--verify-cuda",
        action="store_true",
        help="Run a short CUDA inference against llama-server after building.",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=_default_model_path(),
        help="Path to the GGUF model used for --verify-cuda.",
    )
    parser.add_argument(
        "--verify-host",
        default="127.0.0.1",
        help="Host binding used while running the verification server.",
    )
    parser.add_argument(
        "--verify-port",
        type=int,
        default=8088,
        help="Port used for the verification server.",
    )
    parser.add_argument(
        "--verify-timeout",
        type=int,
        default=180,
        help="Seconds to wait for server readiness and completion during verification.",
    )
    parser.add_argument(
        "--verify-prompt",
        default="SentientOSsecondary CUDA verification prompt.",
        help="Prompt sent to /completion during CUDA verification.",
    )
    parser.add_argument(
        "--n-predict",
        type=int,
        default=64,
        help="Number of tokens requested during CUDA verification.",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=6,
        help="Thread count forwarded to llama-server during verification.",
    )
    parser.add_argument(
        "--ctx-size",
        type=int,
        default=2048,
        help="Context window configured for the verification run.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=512,
        help="Batch size forwarded to llama-server during verification.",
    )
    parser.add_argument(
        "--gpu-layers",
        type=int,
        default=-1,
        help="GPU layer count forwarded to llama-server during verification (-1 to skip).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.8,
        help="Sampling temperature for the verification prompt.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed passed to llama-server for deterministic verification runs.",
    )
    args = parser.parse_args(argv)

    archive = _repo_root() / "SentientOSsecondary.zip"
    if not archive.exists():
        print(f"Archive not found: {archive}", file=sys.stderr)
        return 1

    destination = args.destination
    if args.extract:
        destination = _extract_archive(archive, destination, args.force)

    if not destination.exists():
        print(
            "Destination directory missing. Use --extract to unpack the archive first.",
            file=sys.stderr,
        )
        return 1

    _verify_structure(destination)

    build_targets = args.build_targets or ["llama-server", "llama"]

    if args.build or args.verify_cuda:
        _run_cmake_build(
            destination,
            generator=args.cmake_generator,
            arch=args.cmake_arch,
            cmake_defines=args.cmake_defines,
            build_config=args.build_config,
            targets=build_targets,
            skip_embed=args.skip_embed,
        )

    if args.verify_cuda:
        batch_size = args.batch_size if args.batch_size > 0 else None
        gpu_layers = args.gpu_layers if args.gpu_layers >= 0 else None
        temperature = args.temperature if args.temperature >= 0 else None

        _verify_cuda_runtime(
            destination,
            build_config=args.build_config,
            model=args.model,
            host=args.verify_host,
            port=args.verify_port,
            prompt=args.verify_prompt,
            n_predict=args.n_predict,
            threads=args.threads,
            ctx_size=args.ctx_size,
            batch_size=batch_size,
            gpu_layers=gpu_layers,
            temperature=temperature,
            seed=args.seed,
            timeout=args.verify_timeout,
        )

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
