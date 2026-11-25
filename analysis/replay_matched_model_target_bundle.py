"""Replay a pinned rootless matched-target evidence bundle through WSL.

This performs source, schema, manifest, history-boundary, and optional runtime
preview verification only. It never loads a model or requests inference.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
import datetime
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_MANIFEST_BYTES = 8 * 1024 * 1024
MAX_BUNDLE_FILES = 10_000
MAX_BUNDLE_FILE_BYTES = 64 * 1024 * 1024
MAX_BUNDLE_TOTAL_BYTES = 256 * 1024 * 1024


def _canonical_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _read_json(path: Path, *, limit: int = MAX_MANIFEST_BYTES) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("bundle_json_file_invalid")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("bundle_json_object_required")
    return value


def _safe_relative(value: Any) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("bundle_path_invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value != path.as_posix():
        raise ValueError("bundle_path_invalid")
    return path


def _manifest_rows(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = manifest.get("files")
    if (manifest.get("schema_version") !=
            "sentientos.rootless_matched_model_target_pair_source_bundle:v1"
            or not isinstance(rows, list) or not rows
            or len(rows) > MAX_BUNDLE_FILES
            or type(manifest.get("pinned_source_file_count")) is not int):
        raise ValueError("bundle_manifest_schema_invalid")
    semantic = {key: value for key, value in manifest.items()
        if key != "bundle_manifest_digest"}
    if manifest.get("bundle_manifest_digest") != _canonical_digest(semantic):
        raise ValueError("bundle_manifest_digest_mismatch")
    result: dict[str, Mapping[str, Any]] = {}
    total = 0
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("bundle_file_row_invalid")
        rel = _safe_relative(row.get("path")).as_posix()
        size = row.get("size_bytes")
        digest = row.get("sha256")
        if (rel in result or type(size) is not int or not 0 <= size <=
                MAX_BUNDLE_FILE_BYTES or not isinstance(digest, str)
                or len(digest) != 64 or any(c not in "0123456789abcdef"
                    for c in digest)):
            raise ValueError("bundle_file_row_invalid")
        total += size
        if total > MAX_BUNDLE_TOTAL_BYTES:
            raise ValueError("bundle_total_size_over_bound")
        result[rel] = row
    if (manifest.get("bundle_file_count") != len(result)
            or manifest.get("pinned_source_file_count") != sum(
                "plan_normalized_sha256" in row for row in result.values())):
        raise ValueError("bundle_manifest_counts_invalid")
    return result


def _extract_verified_bundle(*, archive: Path, manifest: Mapping[str, Any],
        rows: Mapping[str, Mapping[str, Any]], destination: Path) -> None:
    if (archive.is_symlink() or not archive.is_file()
            or archive.stat().st_size > MAX_ARCHIVE_BYTES):
        raise ValueError("bundle_archive_invalid")
    names_seen: set[str] = set()
    total = 0
    with zipfile.ZipFile(archive, "r") as bundle:
        infos = bundle.infolist()
        expected_names = set(rows) | {"source_bundle_manifest.json"}
        if (len(infos) != len(expected_names)
                or {info.filename for info in infos} != expected_names):
            raise ValueError("bundle_archive_member_set_mismatch")
        for info in infos:
            rel = _safe_relative(info.filename).as_posix()
            if rel in names_seen or info.is_dir():
                raise ValueError("bundle_archive_member_invalid")
            names_seen.add(rel)
            mode = (info.external_attr >> 16) & 0o170000
            if mode not in (0, stat.S_IFREG):
                raise ValueError("bundle_archive_member_type_invalid")
            if info.file_size > MAX_BUNDLE_FILE_BYTES:
                raise ValueError("bundle_archive_member_over_bound")
            total += info.file_size
            if total > MAX_BUNDLE_TOTAL_BYTES + MAX_MANIFEST_BYTES:
                raise ValueError("bundle_archive_total_over_bound")
            raw = bundle.read(info)
            if len(raw) != info.file_size:
                raise ValueError("bundle_archive_member_size_mismatch")
            if rel == "source_bundle_manifest.json":
                try:
                    embedded = json.loads(raw.decode("utf-8"))
                except (UnicodeError, json.JSONDecodeError) as exc:
                    raise ValueError("bundle_embedded_manifest_invalid") from exc
                if embedded != dict(manifest):
                    raise ValueError("bundle_embedded_manifest_mismatch")
                continue
            row = rows[rel]
            if (len(raw) != row["size_bytes"]
                    or hashlib.sha256(raw).hexdigest() != row["sha256"]):
                raise ValueError("bundle_member_sha256_mismatch:" + rel)
            normalized_digest = row.get("plan_normalized_sha256")
            if normalized_digest is not None:
                normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
                if hashlib.sha256(normalized).hexdigest() != normalized_digest:
                    raise ValueError("bundle_source_pin_mismatch:" + rel)
            path = destination / Path(*PurePosixPath(rel).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as target:
                target.write(raw)


def _load_pair_context(root: Path, rows: Mapping[str, Mapping[str, Any]],
        manifest: Mapping[str, Any]) -> tuple[str, str, dict[str, Any]]:
    pairs = [rel for rel in rows if rel.endswith(
        "/matched_model_target_pair_v2.json")]
    if len(pairs) != 1:
        raise ValueError("bundle_pair_artifact_count_invalid")
    pair = _read_json(root / Path(*PurePosixPath(pairs[0]).parts))
    if pair.get("pair_digest") != manifest.get("campaign_pair_digest"):
        raise ValueError("bundle_pair_digest_binding_mismatch")
    members = pair.get("members")
    if not isinstance(members, Mapping):
        raise ValueError("bundle_pair_members_invalid")
    plans = []
    for member in members.values():
        if not isinstance(member, Mapping):
            raise ValueError("bundle_pair_member_invalid")
        ref = member.get("plan_file")
        if not isinstance(ref, Mapping):
            raise ValueError("bundle_plan_ref_invalid")
        rel = _safe_relative(ref.get("path")).as_posix()
        plan_path = root / Path(*PurePosixPath(rel).parts)
        plan = _read_json(plan_path)
        recipe = plan.get("model_identity_recipe")
        if not isinstance(recipe, Mapping):
            raise ValueError("bundle_model_recipe_missing")
        manifest_digest = recipe.get("manifest_sha256")
        manifest_path = PurePosixPath(str(recipe.get("resolved_manifest_path", "")))
        if (not manifest_path.is_absolute()
                or manifest_path.name != str(manifest_digest) + ".json"
                or manifest_path.parent.name != "ollama-model-manifests"
                or manifest_path.parent.parent.name != "rootless-experimental"
                or manifest_path.parent.parent.parent.name != "sentientos-data"):
            raise ValueError("bundle_model_manifest_path_invalid")
        plans.append((plan, manifest_path))
    if len(plans) != 2:
        raise ValueError("bundle_plan_count_invalid")
    workspaces = {str(path.parents[3]) for _, path in plans}
    if len(workspaces) != 1:
        raise ValueError("bundle_wsl_workspace_mismatch")
    return next(iter(workspaces)), pairs[0], pair


def _run_wsl_verifier(*, root_wsl: str, workspace: str,
        source_python: str, system_site_packages: str,
        wsl_distribution: str, script: str,
        script_args: list[str], error_code: str) -> dict[str, Any]:
    command = (f"cd {shlex.quote(root_wsl)} && "
        f"SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE={shlex.quote(workspace)} "
        f"PYTHONPATH={shlex.quote(system_site_packages)} "
        f"{shlex.quote(source_python)} {shlex.quote(script)} " +
        " ".join(shlex.quote(value) for value in script_args))
    args = ["wsl.exe"]
    if wsl_distribution:
        args.extend(("--distribution", wsl_distribution))
    args.extend(("--exec", "sh", "-lc", command))
    completed = subprocess.run(args, capture_output=True,
        text=True, encoding="utf-8", errors="replace", check=False)
    if completed.returncode != 0:
        raise ValueError(error_code + ":" + completed.stderr[-4000:])
    try:
        result = json.loads(completed.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise ValueError(error_code + "_output_invalid") from exc
    if not isinstance(result, Mapping):
        raise ValueError(error_code + "_result_invalid")
    return dict(result)


def _verify_runtime_previews(*, root: Path, root_wsl: str,
        pair: Mapping[str, Any], workspace: str,
        source_python: str, system_site_packages: str,
        wsl_distribution: str,
        preview_paths: tuple[Path, Path]) -> list[dict[str, Any]]:
    members = pair.get("members")
    target_keys = ("same_model_artifact_target",
        "different_model_artifact_target")
    if not isinstance(members, Mapping) or set(members) != set(target_keys):
        raise ValueError("bundle_runtime_preview_pair_members_invalid")
    evidence: list[dict[str, Any]] = []
    for target, source_path in zip(target_keys, preview_paths):
        if (source_path.is_symlink() or not source_path.is_file()
                or source_path.stat().st_size > MAX_MANIFEST_BYTES):
            raise ValueError("bundle_runtime_preview_input_invalid")
        preview = _read_json(source_path)
        semantic = {key: value for key, value in preview.items()
            if key != "audit_digest"}
        if (preview.get("audit_digest") !=
                _canonical_digest(semantic).removeprefix("sha256:")
                or preview.get("inference_performed") is not False
                or preview.get("learning_established") is not False
                or preview.get("authority") is not False):
            raise ValueError("bundle_runtime_preview_digest_or_scope_invalid")
        member = members[target]
        if (not isinstance(member, Mapping)
                or preview.get("campaign_id") != member.get("campaign_id")
                or preview.get("cycle_id") != member.get("cycle_id")
                or preview.get("plan_digest") != member.get("plan_digest")):
            raise ValueError("bundle_runtime_preview_pair_binding_invalid")
        preview_rel = "external-runtime-previews/" + target + ".json"
        preview_destination = root / Path(*PurePosixPath(preview_rel).parts)
        preview_destination.parent.mkdir(parents=True, exist_ok=True)
        with preview_destination.open("xb") as handle:
            handle.write(source_path.read_bytes())
        plan_ref = member.get("plan_file")
        preflight_ref = member.get("owner_report_file")
        if (not isinstance(plan_ref, Mapping)
                or not isinstance(preflight_ref, Mapping)):
            raise ValueError("bundle_runtime_preview_source_references_invalid")
        plan_rel = _safe_relative(plan_ref.get("path")).as_posix()
        preflight_rel = _safe_relative(preflight_ref.get("path")).as_posix()
        verification = _run_wsl_verifier(root_wsl=root_wsl,
            workspace=workspace, source_python=source_python,
            system_site_packages=system_site_packages,
            wsl_distribution=wsl_distribution,
            script="work/preview_planned_cycle_runtime_owner.py",
            script_args=["--plan", plan_rel,
                "--preflight", preflight_rel,
                "--verify-report", preview_rel],
            error_code="pinned_runtime_preview_verifier_failed")
        if (verification.get("status") != "verified"
                or verification.get("campaign_id") != member.get("campaign_id")
                or verification.get("cycle_id") != member.get("cycle_id")
                or verification.get("plan_digest") != member.get("plan_digest")
                or verification.get("report_digest") != preview.get("audit_digest")
                or verification.get("implementation_matches_current") is not True
                or verification.get("owner_payload_digest_verified") is not True
                or verification.get("inference_performed") is not False
                or verification.get("learning_established") is not False
                or verification.get("authority") is not False):
            raise ValueError("pinned_runtime_preview_verification_mismatch")
        evidence.append({
            "target": target,
            "campaign_id": verification["campaign_id"],
            "cycle_id": verification["cycle_id"],
            "preview_digest": verification["report_digest"],
            "plan_digest": verification["plan_digest"],
            "implementation_digest": verification["implementation_digest"],
            "implementation_matches_current": True,
            "owner_payload_digest_verified": True,
            "verification_scope": verification["verification_scope"],
            "report_origin_attested": False,
            "inference_performed": False,
            "learning_established": False,
            "authority": False,
        })
    return evidence


def _validate_replay_receipt(*, receipt_path: Path, archive: Path,
        manifest: Mapping[str, Any]) -> dict[str, Any]:
    if (archive.is_symlink() or not archive.is_file()
            or archive.stat().st_size > MAX_ARCHIVE_BYTES):
        raise ValueError("bundle_archive_invalid")
    receipt = _read_json(receipt_path)
    if receipt.get("schema_version") != (
            "sentientos.rootless_matched_model_target_pair_portable_replay:v2"):
        raise ValueError("bundle_replay_receipt_schema_invalid")
    semantic = {key: value for key, value in receipt.items()
        if key != "verification_digest"}
    if receipt.get("verification_digest") != _canonical_digest(semantic):
        raise ValueError("bundle_replay_receipt_digest_mismatch")
    bindings = receipt.get("bindings")
    if (not isinstance(bindings, Mapping)
            or bindings.get("source_bundle_manifest_digest")
                != manifest.get("bundle_manifest_digest")
            or bindings.get("source_bundle_archive_sha256")
                != hashlib.sha256(archive.read_bytes()).hexdigest()
            or not isinstance(bindings.get("source_bundle_archive_path"), str)
            or PurePosixPath(bindings["source_bundle_archive_path"]).name
                != archive.name):
        raise ValueError("bundle_replay_receipt_bundle_binding_mismatch")
    verification = receipt.get("verification_result")
    if (not isinstance(verification, Mapping)
            or verification.get("status") != "verified"
            or verification.get("pair_digest")
                != manifest.get("campaign_pair_digest")
            or verification.get("inference_performed") is not False
            or verification.get("learning_established") is not False
            or verification.get("authority") is not False):
        raise ValueError("bundle_replay_receipt_result_invalid")
    return receipt


def _windows_to_wsl(path: Path) -> str:
    drive, tail = os.path.splitdrive(str(path.resolve(strict=True)))
    if not drive or not tail.startswith(("\\", "/")):
        raise ValueError("bundle_temp_path_not_on_windows_drive")
    return "/mnt/" + drive[0].lower() + tail.replace("\\", "/")


def replay(*, archive: Path, manifest_path: Path, wsl_distribution: str,
        receipt_path: Path, wsl_python: str | None,
        system_site_packages: str,
        runtime_preview_paths: tuple[Path, Path] | None = None) -> dict[str, Any]:
    manifest = _read_json(manifest_path)
    rows = _manifest_rows(manifest)
    receipt = _validate_replay_receipt(receipt_path=receipt_path,
        archive=archive, manifest=manifest)
    with zipfile.ZipFile(archive, "r") as bundle:
        try:
            archive_manifest = json.loads(bundle.read(
                "source_bundle_manifest.json").decode("utf-8"))
        except (KeyError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("bundle_embedded_manifest_invalid") from exc
    if archive_manifest != manifest:
        raise ValueError("bundle_embedded_manifest_mismatch")
    with tempfile.TemporaryDirectory(prefix="sentientos-pinned-pair-replay-") as temporary:
        root = Path(temporary)
        _extract_verified_bundle(archive=archive, manifest=manifest,
            rows=rows, destination=root)
        workspace, pair_rel, pair = _load_pair_context(root, rows, manifest)
        source_python = wsl_python or (
            workspace + "/.venv-cognition-cycle/bin/python")
        root_wsl = _windows_to_wsl(root)
        command = (f"cd {shlex.quote(root_wsl)} && "
            f"SENTIENTOS_ROOTLESS_EXPERIMENT_WORKSPACE={shlex.quote(workspace)} "
            f"PYTHONPATH={shlex.quote(system_site_packages)} "
            f"{shlex.quote(source_python)} "
            f"work/verify_rootless_matched_model_target_pair.py "
            f"--pair {shlex.quote(pair_rel)}")
        args = ["wsl.exe"]
        if wsl_distribution:
            args.extend(("--distribution", wsl_distribution))
        args.extend(("--exec", "sh", "-lc", command))
        completed = subprocess.run(args, capture_output=True,
            text=True, encoding="utf-8", errors="replace", check=False)
        if completed.returncode != 0:
            raise ValueError("pinned_pair_verifier_failed:" +
                completed.stderr[-4000:])
        try:
            result = json.loads(completed.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as exc:
            raise ValueError("pinned_pair_verifier_output_invalid") from exc
        if (not isinstance(result, Mapping)
                or result.get("status") != "verified"
                or result.get("pair_digest") != manifest.get(
                    "campaign_pair_digest")
                or result.get("same_implementation_source_count")
                    != manifest.get("pinned_source_file_count")
                or result.get("inference_performed") is not False
                or result.get("learning_established") is not False
                or result.get("authority") is not False):
            raise ValueError("pinned_pair_verifier_result_mismatch")
        runtime_preview_verifications = (
            _verify_runtime_previews(root=root, root_wsl=root_wsl,
                pair=pair, workspace=workspace,
                source_python=source_python,
                system_site_packages=system_site_packages,
                wsl_distribution=wsl_distribution,
                preview_paths=runtime_preview_paths)
            if runtime_preview_paths is not None else None)
        replay_result = {
            "status": "verified",
            "bundle_manifest_digest": manifest["bundle_manifest_digest"],
            "prior_verification_receipt_digest": receipt[
                "verification_digest"],
            "campaign_pair_digest": manifest["campaign_pair_digest"],
            "pinned_source_file_count": manifest[
                "pinned_source_file_count"],
            "verification_result": dict(result),
            "model_loaded": False,
            "inference_performed": False,
            "learning_established": False,
            "authority": False,
        }
        if runtime_preview_verifications is not None:
            replay_result["runtime_preview_verifications"] = (
                runtime_preview_verifications)
        return replay_result


def _persist_receipt(path: Path, result: Mapping[str, Any], *,
        archive: Path) -> dict[str, Any]:
    if (path.exists() or path.is_symlink() or not path.parent.is_dir()
            or path.parent.absolute() != path.parent.resolve(strict=True)):
        raise ValueError("replay_receipt_destination_invalid")
    semantic = {
        "schema_version": "sentientos.rootless_matched_model_target_bundle_replay:v1",
        "created_at_utc": datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
        "bundle_archive_sha256": hashlib.sha256(
            archive.read_bytes()).hexdigest(),
        "launcher_sha256": hashlib.sha256(
            Path(__file__).read_bytes()).hexdigest(),
        "bundle_manifest_digest": result["bundle_manifest_digest"],
        "prior_verification_receipt_digest": result[
            "prior_verification_receipt_digest"],
        "verification_result": dict(result["verification_result"]),
        "model_loaded": False,
        "inference_performed": False,
        "learning_established": False,
        "authority": False,
    }
    if "runtime_preview_verifications" in result:
        semantic["runtime_preview_verifications"] = result[
            "runtime_preview_verifications"]
    rendered = json.dumps({**semantic,
        "receipt_digest": _canonical_digest(semantic)},
        sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(rendered)
        handle.flush()
        os.fsync(handle.fileno())
    return json.loads(rendered)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--manifest", type=Path,
        help="Defaults to the bundle's sibling .manifest.json")
    parser.add_argument("--receipt", type=Path,
        help="Defaults to matched_model_target_pair_portable_replay_v2.json beside the bundle")
    parser.add_argument("--wsl-distribution", default="Ubuntu-24.04")
    parser.add_argument("--wsl-python",
        help="Defaults to .venv-cognition-cycle/bin/python under the pinned data workspace")
    parser.add_argument("--system-site-packages",
        default="/usr/lib/python3/dist-packages",
        help="WSL path providing jsonschema to the cognition-cycle virtual environment")
    parser.add_argument("--output", type=Path,
        help="Optional create-only JSON receipt for this replay")
    parser.add_argument("--left-runtime-preview", type=Path,
        help="Optional same-model target runtime preview to verify against pinned source")
    parser.add_argument("--right-runtime-preview", type=Path,
        help="Optional different-model target runtime preview to verify against pinned source")
    args = parser.parse_args()
    manifest_path = args.manifest or args.bundle.with_suffix(".manifest.json")
    receipt_path = args.receipt or (args.bundle.parent /
        "matched_model_target_pair_portable_replay_v2.json")
    try:
        if ((args.left_runtime_preview is None) !=
                (args.right_runtime_preview is None)):
            raise ValueError("both_runtime_preview_inputs_required")
        result = replay(archive=args.bundle, manifest_path=manifest_path,
            wsl_distribution=args.wsl_distribution,
            receipt_path=receipt_path,
            wsl_python=args.wsl_python,
            system_site_packages=args.system_site_packages,
            runtime_preview_paths=(
                (args.left_runtime_preview, args.right_runtime_preview)
                if args.left_runtime_preview is not None else None))
        if args.output is not None:
            receipt = _persist_receipt(args.output, result,
                archive=args.bundle)
            result = {**result, "replay_receipt_path": str(args.output),
                "replay_receipt_digest": receipt["receipt_digest"]}
    except (OSError, ValueError, zipfile.BadZipFile,
            json.JSONDecodeError) as exc:
        print("portable_pair_replay_error:" + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
