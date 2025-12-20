# Hugging Face Intake → Escrow → Manifest Pipeline

This directory contains the curator-only tooling that quarantines Hugging Face
access from the installer. The installer only consumes escrowed artifacts and
pinned manifests; it **never** talks to Hugging Face or re-interprets licenses.

## Components
- **Discovery (`hf_intake.discovery`)** — curator-only scan for text generation
  models that expose GGUF artifacts and ship with redistributable licenses.
- **Escrow (`hf_intake.escrow`)** — downloads a pinned artifact, hashes it,
  and stores an immutable copy alongside LICENSE, model card, and SOURCE
  metadata.
- **Hardware classification (`hf_intake.classifier`)** — deterministic rules
  that mark CPU/GPU requirements, quantization, and AVX flags from the escrowed
  file name and size.
- **Manifest (`hf_intake.manifest`)** — turns escrow state into a deterministic
  manifest under `manifests/manifest-YYYY-MM-DD.json` and validates checksums
  on disk.
- **CLI (`hf_intake.cli`)** — orchestration entrypoint for curators; the
  installer never calls it.

## Invariants
- No "latest" downloads — every artifact is revision pinned and hash-anchored.
- No overwrites — escrow refuses to replace existing files.
- Manifest URLs always point at escrowed content-addressed artifacts; Hugging
  Face URLs are rejected at validation time.
- Validation fails closed for missing licenses, checksums, or ambiguous
  hardware requirements.

## Quickstart (Curator Only)
- Discover candidates: `python -m hf_intake.cli discover`
- Escrow a model: `python -m hf_intake.cli escrow <repo> <artifact.gguf> <escrow_root> [--revision <sha>]`
- Generate & validate manifest: `python -m hf_intake.cli manifest escrow/ manifests/manifest-YYYY-MM-DD.json`
- Validate an existing manifest: `python -m hf_intake.cli validate manifests/manifest-YYYY-MM-DD.json`

The installer should only read the manifest and fetch the escrowed artifact; it
should not perform any live HF queries or license reasoning.
