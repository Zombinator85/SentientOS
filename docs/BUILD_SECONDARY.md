# SentientOSsecondary CUDA Build Guide

SentientOSsecondary packages the Windows + CUDA build chain that powers the
`llama.cpp` based secondary runtime.  The tree now lives directly inside the
repository under `SentientOSsecondary/llama.cpp` so CI and devcontainers can
build without Git LFS.  This guide documents how to validate the layout and
produce a release build of the `llama-server` target on Windows.

## 1. Prerequisites

1. Visual Studio 2022 with the **Desktop development with C++** workload.
2. NVIDIA CUDA Toolkit 12.2 (or newer that remains compatible with
   `llama.cpp`).
3. Python 3.10+ (the helper script uses the standard library only).
4. CMake 3.26+ on your PATH.
5. `cmake` generator integration for Visual Studio (installed by default when
   you install VS 2022).

## 2. Validate the vendored tree

Run the lightweight validation helper to make sure the committed vendor tree is
still intact:

```powershell
PS> python tools/bootstrap_secondary.py
```

The script confirms that `SentientOSsecondary/llama.cpp` and the embedded asset
pipeline exist.  If any files are missing (for example after a partial clone),
reset the directory from git history before continuing.

## 4. Configure the Windows + CUDA build

The secondary build uses the upstream `llama.cpp` toolchain with CUDA enabled
and the server target turned on.  From a **Developer PowerShell for VS 2022**
window run:

```powershell
PS> cd SentientOSsecondary/llama.cpp
PS> cmake -S . -B ..\build -G "Visual Studio 17 2022" `
        -DLLAMA_CUDA=ON `
        -DLLAMA_BUILD_SERVER=ON `
        -DLLAMA_CUBLAS=ON `
        -DLLAMA_EMBED_SERVER=ON
```

This command reuses the shipped build directory.  It regenerates the Visual
Studio solution while preserving the embedded asset pipeline.

### Embedded asset regeneration

If you change any of the web UI files, regenerate the embedded headers before
rebuilding:

```powershell
PS> cmake --build ..\build --target server_embed
```

The generated headers (for example `common_embed.h` and `theme_dark.css.hpp`)
ship in Git LFS so other environments can build without the web toolchain.

## 5. Build the runtime binaries

```powershell
PS> cmake --build ..\build --config Release --target llama-server
PS> cmake --build ..\build --config Release --target llama
```

The build outputs the following key artifacts in
`SentientOSsecondary\build\bin\Release`:

- `llama-server.exe`
- `llama.dll`

When the build completes without errors you have a validated secondary runtime
ready to serve SentientOS.

## 6. Launch the CUDA secondary server

Start the server with the mistral model path configured in
`config/master_files.json`:

```powershell
PS> ..\build\bin\Release\llama-server.exe `
        --model "C:\SentientOS\sentientos_data\models\mistral-7b\mistral-7b-instruct-v0.2.Q4_K_M.gguf" `
        --host 127.0.0.1 `
        --port 8080
```

Wrap the command in a batch file or PowerShell profile snippet if you want a
shortcut launcher.  Adjust the model location if you store GGUF files outside
the default `C:\SentientOS\sentientos_data\models` directory.

## 7. Troubleshooting

- **Git LFS pointer error** – Re-run `git lfs pull` until the helper script no
  longer reports pointer metadata.
- **CUDA compilation failures** – Confirm the Developer PowerShell session is
  using the same architecture (x64) as the Visual Studio generator.  CUDA 12.2+
  is required for modern NVIDIA drivers.
- **Missing embedded headers** – Run `cmake --build ..\build --target
  server_embed` to regenerate the headers.
- **Model path mismatches** – Update `config/master_files.json` with the
  absolute Windows path to your GGUF model.  The shipped configuration expects
  the mistral-7b model under `C:\SentientOS\sentientos_data\models`.

With these steps the SentientOSsecondary module becomes a first-class, auditable
component of the SentientOS deployment pipeline.

## 8. Verification and Troubleshooting

### Confirm the CUDA runtime

1. Open an **x64 Native Tools Command Prompt for VS 2022**.
2. Run `nvidia-smi` and confirm the driver reports the expected GPU.
3. From the same prompt, run `nvcc --version` to ensure the CUDA toolkit is on
   your `PATH`.

If either command fails, repair the NVIDIA driver or reinstall the CUDA toolkit
before continuing. The automated verification step relies on cuBLAS to load the
model into VRAM.

### Run the automated CUDA verification

The helper script now bundles a smoke test that launches `llama-server`, waits
for `ggml_init_cublas()` to announce the detected GPU, and sends a short
completion request. The script tears the server down automatically after the
response completes.

```powershell
PS> python -m scripts.prepare_secondary_build --verify-cuda
```

Key flags you can use to customise the run:

- `--model PATH` – override the default Mistral GGUF path.
- `--n-predict 128` – request a longer sample.
- `--verify-port 8090` – change the temporary HTTP port in case 8088 is busy.

The script prints the first chunk of generated text and exits non-zero if the
CUDA runtime fails to initialise or the HTTP request does not succeed.

### Rebuild after asset or embed failures

If `llama-server.exe` reports missing embedded headers or stale assets, rerun
the helper in build mode to regenerate both the embedded bundle and the server
binary:

```powershell
PS> python -m scripts.prepare_secondary_build --build
```

Add `--skip-embed` only if you are certain the embedded web assets are already
up to date. You can also invoke the embed step directly:

```powershell
PS> cmake --build ..\build --config Release --target server_embed
```

Once the assets build cleanly, rerun the verification step to ensure CUDA is
still initialised correctly.
