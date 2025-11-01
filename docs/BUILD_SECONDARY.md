# SentientOSsecondary CUDA Build Guide

SentientOSsecondary packages the Windows + CUDA build chain that powers the
`llama.cpp` based secondary runtime.  The assets live in
`SentientOSsecondary.zip`, which is tracked through Git LFS so the binary build
artifacts stay out of the main Git history.  This guide documents how to unpack
those assets, verify the layout, and produce a release build of the
`llama-server` target on Windows.

> **Note**
> The repository snapshot that ships with this guide only stores Git LFS
> pointers.  Make sure you have network access to the Git LFS remote before
> attempting the extraction and build steps below.

## 1. Prerequisites

1. Git LFS (`git lfs install`), with credentials that can download the private
   SentientOS LFS objects.
2. Visual Studio 2022 with the **Desktop development with C++** workload.
3. NVIDIA CUDA Toolkit 12.2 (or newer that remains compatible with
   `llama.cpp`).
4. Python 3.10+ (the helper script uses the standard library only).
5. CMake 3.26+ on your PATH.
6. `cmake` generator integration for Visual Studio (installed by default when
   you install VS 2022).

## 2. Fetch the Git LFS payloads

```powershell
# From the repository root
PS> git lfs install
PS> git lfs pull
```

You should now see large binary downloads for:

- `SentientOSsecondary.zip`
- `sentientos_data/models/mixtral-8x7b/mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf`

## 3. Extract and validate SentientOSsecondary

The helper script `scripts/prepare_secondary_build.py` guarantees the zip was
fetched correctly and unpacks it into `SentientOSsecondary/`.

```powershell
PS> python -m scripts.prepare_secondary_build --extract
```

The script performs three checks:

1. Confirms the zip is an actual binary payload (not an unfetched LFS pointer).
2. Extracts or refreshes the `SentientOSsecondary/` directory.
3. Verifies that key build files exist, including:
   - `SentientOSsecondary/llama.cpp/examples/server/CMakeLists.txt`
   - `SentientOSsecondary/llama.cpp/common/CMakeLists.txt`
   - `SentientOSsecondary/build/` (populated with the pre-generated assets such
     as embedded web resources)

If any of the checks fail the script stops with a clear error message so you
can re-run `git lfs pull` or investigate the extraction path.

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

Start the server with the mixtral model path configured in
`config/master_files.json`:

```powershell
PS> ..\build\bin\Release\llama-server.exe `
        --model "C:\SentientOS\sentientos_data\models\mixtral-8x7b\mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf" `
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
  the mixtral-8x7b model under `C:\SentientOS\sentientos_data\models`.

With these steps the SentientOSsecondary module becomes a first-class, auditable
component of the SentientOS deployment pipeline.
