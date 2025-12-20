from __future__ import annotations

import argparse
import json
from pathlib import Path

from huggingface_hub import HfApi

from hf_intake import discovery, escrow, manifest
from hf_intake.classifier import classify


def _load_candidate_from_args(args: argparse.Namespace, api: HfApi) -> discovery.CandidateModel:
    if not args.revision:
        info = api.model_info(args.repo)
        revision = info.sha
        license_id = (info.cardData or {}).get("license") or info.license
    else:
        revision = args.revision
        info = api.model_info(args.repo, revision=revision)
        license_id = (info.cardData or {}).get("license") or info.license
    license_text = discovery._resolve_license_text(args.repo, revision, api)  # noqa: SLF001
    model_card = discovery._resolve_model_card(args.repo, revision, api)  # noqa: SLF001
    return discovery.CandidateModel(
        repo_id=args.repo,
        revision=revision,
        license_id=license_id or "unknown",
        gguf_files=[args.artifact],
        license_text=license_text,
        model_card=model_card,
    )


def command_discover(args: argparse.Namespace) -> None:
    models = discovery.discover_text_models(api=HfApi())
    print(json.dumps([model.to_source_record(model.gguf_files[0]) for model in models], indent=2))


def command_escrow(args: argparse.Namespace) -> None:
    api = HfApi()
    candidate = _load_candidate_from_args(args, api)
    result = escrow.escrow_artifact(candidate, args.artifact, Path(args.escrow_root), api=api)
    requirements = classify(result.artifact_path, result.size_bytes)
    print(
        json.dumps(
            {
                "model": result.model_id,
                "artifact": str(result.artifact_path),
                "sha256": result.sha256,
                "size_bytes": result.size_bytes,
                "requirements": requirements.as_dict(),
            },
            indent=2,
        )
    )


def command_manifest(args: argparse.Namespace) -> None:
    manifest.generate_manifest(Path(args.escrow_root), Path(args.output), manifest_version=args.version)
    manifest.validate_manifest(Path(args.output))
    print(f"Manifest written to {args.output}")


def command_validate(args: argparse.Namespace) -> None:
    manifest.validate_manifest(Path(args.path))
    print(f"Manifest validated: {args.path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HF intake to escrow pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover_parser = subparsers.add_parser("discover", help="Discover eligible HF models")
    discover_parser.set_defaults(func=command_discover)

    escrow_parser = subparsers.add_parser("escrow", help="Download and escrow a HF artifact")
    escrow_parser.add_argument("repo", help="HF repository id, e.g., meta-llama/Llama-3-8b-Instruct")
    escrow_parser.add_argument("artifact", help="Exact artifact filename to escrow (must be GGUF)")
    escrow_parser.add_argument("escrow_root", help="Destination escrow root directory")
    escrow_parser.add_argument("--revision", help="Pinned HF revision/commit", default=None)
    escrow_parser.set_defaults(func=command_escrow)

    manifest_parser = subparsers.add_parser("manifest", help="Generate deterministic manifest from escrow")
    manifest_parser.add_argument("escrow_root", help="Escrow root directory")
    manifest_parser.add_argument("output", help="Manifest file path")
    manifest_parser.add_argument("--version", help="Override manifest version string", default=None)
    manifest_parser.set_defaults(func=command_manifest)

    validate_parser = subparsers.add_parser("validate", help="Validate a generated manifest")
    validate_parser.add_argument("path", help="Path to manifest json")
    validate_parser.set_defaults(func=command_validate)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
