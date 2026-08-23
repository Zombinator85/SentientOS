"""Operator-confirmed custody of one preselected five-wheel dependency bundle."""
from __future__ import annotations

import builtins
import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from sentientos.exact_artifact_acquisition import ExactArtifactError, StreamResponse, stream_exact
from sentientos.exact_artifact_acquisition import https_transport as _https_transport
from sentientos.local_runtime_dependencies import PLAN_SCHEMA, semantic_digest, validate_dependency_catalog

AUTHORIZATION_SCHEMA = "sentientos.local_runtime_dependency_acquisition_authorization:v1"
ARTIFACT_RECEIPT_SCHEMA = "sentientos.local_runtime_dependency_artifact_acquisition_receipt:v1"
BUNDLE_RECEIPT_SCHEMA = "sentientos.local_runtime_dependency_bundle_acquisition_receipt:v1"
ACTION = "acquire_runtime_dependency_bundle"
DEPENDENCY_HOSTS = frozenset({"files.pythonhosted.org"})
REQUIRED_PACKAGES = frozenset({"typing-extensions", "numpy", "diskcache", "jinja2", "markupsafe"})
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
CHUNK_SIZE = 1024 * 1024
Transport = Callable[[str], StreamResponse]
DiskUsageProvider = Callable[[str | os.PathLike[str]], Any]


class DependencyAcquisitionError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def default_dependency_escrow_root() -> Path:
    data = os.environ.get("SENTIENTOS_DATA_DIR")
    return (Path(data) if data else Path.home() / ".sentientos") / "runtime-dependencies"


def receipt_semantic_digest(receipt: Mapping[str, Any]) -> str:
    """Digest semantic fields; timestamps and the digest field are excluded."""
    return semantic_digest({k: v for k, v in receipt.items() if k not in {"retrieved_at", "receipt_semantic_digest"}})


def _canon(package: object) -> str:
    return str(package).lower().replace("_", "-")


def _check_components(path: Path, *, allow_missing: bool) -> None:
    current = Path(path.anchor)
    for component in path.parts[1:] if path.is_absolute() else path.parts:
        current /= component
        try:
            current.lstat()
        except FileNotFoundError:
            if allow_missing:
                continue
            raise DependencyAcquisitionError("unsafe_dependency_escrow_path")
        if current.is_symlink() or not current.is_dir():
            raise DependencyAcquisitionError("unsafe_dependency_escrow_path")


def _filename(value: object) -> str:
    name = str(value)
    if not name or Path(name).is_absolute() or Path(name).name != name or name in {".", ".."}:
        raise DependencyAcquisitionError("invalid_dependency_artifact_filename")
    return name


def _source(value: object) -> str:
    url = str(value); parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in DEPENDENCY_HOSTS or parsed.username or parsed.password
            or not parsed.path.endswith(".whl") or "/simple" in parsed.path.lower() or parsed.query or parsed.fragment):
        raise DependencyAcquisitionError("untrusted_dependency_source")
    return url


def validate_binding(plan: Mapping[str, Any], catalog: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(plan, Mapping) or plan.get("schema_version") != PLAN_SCHEMA:
        raise DependencyAcquisitionError("invalid_dependency_plan")
    if plan.get("status") != "selected":
        raise DependencyAcquisitionError("dependency_plan_not_selected")
    if plan.get("runtime_dependency_custody_ready") is not True:
        raise DependencyAcquisitionError("invalid_dependency_plan")
    copy = dict(plan); claimed = copy.pop("dependency_plan_digest", None)
    if claimed != semantic_digest(copy):
        raise DependencyAcquisitionError("invalid_dependency_plan")
    try:
        validated = validate_dependency_catalog(catalog)
    except (KeyError, TypeError, ValueError) as exc:
        raise DependencyAcquisitionError("invalid_dependency_catalog") from exc
    if plan.get("dependency_catalog_digest") != validated["catalog_digest"]:
        raise DependencyAcquisitionError("dependency_catalog_digest_mismatch")
    bundle = next((b for b in validated["environment_bundles"] if b["environment_id"] == plan.get("environment_id")), None)
    if bundle is None:
        raise DependencyAcquisitionError("dependency_environment_mismatch")
    if plan.get("bundle_digest") != bundle["bundle_digest"]:
        raise DependencyAcquisitionError("bundle_digest_mismatch")
    ids = plan.get("artifact_ids"); artifacts = plan.get("artifacts")
    if not isinstance(ids, list) or not isinstance(artifacts, list) or ids != bundle["artifact_ids"] or len(ids) != 5 or len(set(ids)) != 5:
        raise DependencyAcquisitionError("dependency_artifact_identity_mismatch")
    rebound: list[dict[str, Any]] = []
    identity = ("artifact_id", "package_name", "package_version", "artifact_filename", "artifact_sha256", "artifact_size_bytes")
    for artifact_id, planned in zip(ids, artifacts):
        canonical = validated["artifacts_by_id"].get(artifact_id)
        if canonical is None:
            raise DependencyAcquisitionError("dependency_artifact_missing_from_catalog")
        if not isinstance(planned, Mapping) or any(planned.get(k) != canonical.get(k) for k in identity):
            raise DependencyAcquisitionError("dependency_artifact_identity_mismatch")
        _filename(canonical["artifact_filename"]); _source(canonical["artifact_url"])
        rebound.append(canonical)
    if {_canon(a["package_name"]) for a in rebound} != REQUIRED_PACKAGES:
        raise DependencyAcquisitionError("dependency_artifact_identity_mismatch")
    return validated, rebound


def authorization_for(plan: Mapping[str, Any], escrow_root: Path | str, *, operator_confirmed: bool) -> dict[str, Any]:
    artifacts = plan.get("artifacts", [])
    value = {"schema_version": AUTHORIZATION_SCHEMA, "action": ACTION,
             "dependency_plan_digest": plan.get("dependency_plan_digest"),
             "dependency_catalog_digest": plan.get("dependency_catalog_digest"), "bundle_digest": plan.get("bundle_digest"),
             "environment_id": plan.get("environment_id"), "artifact_ids": plan.get("artifact_ids"),
             "artifact_sha256_values": [a.get("artifact_sha256") for a in artifacts],
             "artifact_size_bytes_values": [a.get("artifact_size_bytes") for a in artifacts],
             "escrow_root": str(Path(escrow_root).expanduser().absolute()), "operator_confirmed": operator_confirmed}
    value["authorization_digest"] = semantic_digest(value)
    return value


def https_transport(url: str) -> StreamResponse:
    try:
        return _https_transport(url, initial_hosts=DEPENDENCY_HOSTS, redirect_hosts=DEPENDENCY_HOSTS,
                                redirect_error="dependency_redirect_host_rejected")
    except ExactArtifactError as exc:
        raise DependencyAcquisitionError(exc.code) from exc


def _read_json_nofollow(path: Path) -> dict[str, Any]:
    with builtins.open(path, "r", encoding="utf-8", opener=lambda p, f: os.open(p, f | getattr(os, "O_NOFOLLOW", 0))) as source:
        value = json.load(source)
    if not isinstance(value, dict): raise ValueError
    return value


def _artifact_receipt_static(entry: Mapping[str, Any]) -> dict[str, Any]:
    digest = entry["artifact_sha256"]
    return {"schema_version": ARTIFACT_RECEIPT_SCHEMA, "status": "acquired_verified",
            "artifact_id": entry["artifact_id"], "package_name": entry["package_name"],
            "package_version": entry["package_version"], "artifact_filename": entry["artifact_filename"],
            "expected_sha256": digest, "observed_sha256": digest,
            "expected_size_bytes": entry["artifact_size_bytes"], "observed_size_bytes": entry["artifact_size_bytes"],
            "content_address": f"sha256:{digest}",
            "verified_relative_path": str(Path("sha256") / digest / entry["artifact_filename"]),
            "canonical_source_url": entry["artifact_url"], "artifact_verified": True,
            "cache_hit": False, "network_performed": True, "download_performed": True,
            "host_mutation_performed": True, "package_install_performed": False,
            "subprocess_performed": False, "runtime_import_performed": False,
            "model_load_performed": False, "commissioning_performed": False,
            "runtime_execution_authority_granted": False}


def _existing_artifact(final: Path, entry: Mapping[str, Any]) -> dict[str, Any] | None:
    if not final.exists(): return None
    _check_components(final, allow_missing=False)
    if {p.name for p in final.iterdir()} != {entry["artifact_filename"], "acquisition-receipt.json"}:
        raise DependencyAcquisitionError("existing_dependency_escrow_conflict")
    artifact, receipt_path = final / entry["artifact_filename"], final / "acquisition-receipt.json"
    if artifact.is_symlink() or receipt_path.is_symlink() or not artifact.is_file() or not receipt_path.is_file():
        raise DependencyAcquisitionError("existing_dependency_escrow_conflict")
    try:
        digest = hashlib.sha256()
        with builtins.open(artifact, "rb", opener=lambda p, f: os.open(p, f | getattr(os, "O_NOFOLLOW", 0))) as source:
            for chunk in iter(lambda: source.read(CHUNK_SIZE), b""): digest.update(chunk)
        receipt = _read_json_nofollow(receipt_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise DependencyAcquisitionError("existing_dependency_escrow_conflict") from exc
    checks = _artifact_receipt_static(entry)
    hosts = receipt.get("sanitized_network_destination_hosts")
    redirects = receipt.get("redirect_count")
    allowed_keys = set(checks) | {"sanitized_network_destination_hosts", "redirect_count", "receipt_semantic_digest"}
    if (artifact.stat().st_size != entry["artifact_size_bytes"] or digest.hexdigest() != entry["artifact_sha256"]
            or receipt.get("receipt_semantic_digest") != receipt_semantic_digest(receipt)
            or set(receipt) != allowed_keys or any(receipt.get(k) != v for k, v in checks.items())
            or not isinstance(hosts, list) or not hosts or any(host not in DEPENDENCY_HOSTS for host in hosts)
            or not isinstance(redirects, int) or isinstance(redirects, bool) or redirects < 0):
        raise DependencyAcquisitionError("existing_dependency_escrow_conflict")
    result = dict(receipt); result.update(status="dependency_artifact_already_present_verified", cache_hit=True,
        network_performed=False, download_performed=False, host_mutation_performed=False)
    return result


def _bundle_static(plan: Mapping[str, Any], entries: list[dict[str, Any]], receipts: list[dict[str, Any]],
                   authorization_digest: str) -> dict[str, Any]:
    return {"schema_version": BUNDLE_RECEIPT_SCHEMA, "status": "acquired_verified",
            "dependency_plan_digest": plan["dependency_plan_digest"],
            "dependency_catalog_digest": plan["dependency_catalog_digest"], "bundle_digest": plan["bundle_digest"],
            "environment_id": plan["environment_id"], "authorization_digest": authorization_digest,
            "artifact_ids": list(plan["artifact_ids"]),
            "artifacts": [{"artifact_id": entry["artifact_id"], "package_name": entry["package_name"],
                "package_version": entry["package_version"], "artifact_filename": entry["artifact_filename"],
                "content_address": f"sha256:{entry['artifact_sha256']}",
                "artifact_receipt_semantic_digest": receipt["receipt_semantic_digest"],
                "verified_relative_path": str(Path("sha256") / entry["artifact_sha256"] / entry["artifact_filename"])}
                for entry, receipt in zip(entries, receipts)],
            "artifact_count": 5, "total_expected_bytes": sum(e["artifact_size_bytes"] for e in entries),
            "total_observed_bytes": sum(e["artifact_size_bytes"] for e in entries), "bundle_verified": True,
            "dependency_bundle_availability_status": "acquired_verified", "runtime_dependency_custody_ready": True,
            "package_install_performed": False, "subprocess_performed": False, "runtime_import_performed": False,
            "model_load_performed": False, "commissioning_performed": False,
            "runtime_execution_authority_granted": False}


def _verify_bundle_receipt(receipt: Mapping[str, Any], plan: Mapping[str, Any], entries: list[dict[str, Any]],
                           artifact_receipts: list[dict[str, Any]], authorization_digest: str) -> dict[str, Any]:
    expected = _bundle_static(plan, entries, artifact_receipts, authorization_digest)
    operational = {"network_performed", "download_performed", "cache_hit_count", "downloaded_count"}
    if (set(receipt) != set(expected) | operational | {"receipt_semantic_digest"}
            or any(receipt.get(key) != value for key, value in expected.items())
            or receipt.get("receipt_semantic_digest") != receipt_semantic_digest(receipt)):
        raise DependencyAcquisitionError("existing_dependency_escrow_conflict")
    cache_hits, downloaded = receipt.get("cache_hit_count"), receipt.get("downloaded_count")
    if (not isinstance(cache_hits, int) or isinstance(cache_hits, bool) or not isinstance(downloaded, int)
            or isinstance(downloaded, bool) or cache_hits < 0 or downloaded < 0 or cache_hits + downloaded != 5
            or receipt.get("network_performed") is not (downloaded > 0)
            or receipt.get("download_performed") is not (downloaded > 0)):
        raise DependencyAcquisitionError("existing_dependency_escrow_conflict")
    return dict(receipt)


def _write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    receipt["receipt_semantic_digest"] = receipt_semantic_digest(receipt)
    with path.open("x", encoding="utf-8") as output:
        json.dump(receipt, output, sort_keys=True, separators=(",", ":")); output.write("\n"); output.flush(); os.fsync(output.fileno())
    os.chmod(path, 0o600)


def acquire_dependency_bundle(plan: Mapping[str, Any], *, catalog: Mapping[str, Any], escrow_root: Path | str,
                              authorization: Mapping[str, Any] | None = None, execute: bool = False,
                              transport: Transport = https_transport,
                              disk_usage_provider: DiskUsageProvider = shutil.disk_usage) -> dict[str, Any]:
    """Inspect or acquire exactly the catalog-rebound bundle; never install it."""
    _, entries = validate_binding(plan, catalog)
    root = Path(escrow_root).expanduser().absolute(); _check_components(root, allow_missing=True)
    bindings = {"dependency_plan_digest": plan["dependency_plan_digest"],
                "dependency_catalog_digest": plan["dependency_catalog_digest"], "bundle_digest": plan["bundle_digest"],
                "environment_id": plan["environment_id"]}
    expected_auth = authorization_for(plan, root, operator_confirmed=True)
    bindings["authorization_digest"] = expected_auth["authorization_digest"]
    cached: dict[str, dict[str, Any]] = {}
    for entry in entries:
        hit = _existing_artifact(root / "sha256" / entry["artifact_sha256"], entry)
        if hit: cached[entry["artifact_id"]] = hit
    bundle_dir = root / "bundles" / plan["bundle_digest"]
    if bundle_dir.exists():
        if len(cached) != 5: raise DependencyAcquisitionError("existing_dependency_escrow_conflict")
        try: receipt = _read_json_nofollow(bundle_dir / "dependency-bundle-acquisition-receipt.json")
        except (OSError, ValueError, json.JSONDecodeError) as exc: raise DependencyAcquisitionError("existing_dependency_escrow_conflict") from exc
        ordered_receipts = [cached[entry["artifact_id"]] for entry in entries]
        result = _verify_bundle_receipt(receipt, plan, entries, ordered_receipts, expected_auth["authorization_digest"])
        result.update(status="dependency_bundle_already_present_verified", network_performed=False,
                                               download_performed=False, cache_hit_count=5, downloaded_count=0)
        return result
    missing = [a for a in entries if a["artifact_id"] not in cached]
    inspection = {"status": "inspection_ready", **bindings, "artifact_count": 5,
                  "missing_artifact_count": len(missing), "missing_expected_bytes": sum(a["artifact_size_bytes"] for a in missing),
                  "network_performed": False, "download_performed": False, "host_mutation_performed": False,
                  "dependency_bundle_availability_status": "not_acquired"}
    if not execute: return inspection
    if authorization is None or dict(authorization) != expected_auth:
        raise DependencyAcquisitionError("invalid_dependency_acquisition_authorization")
    ancestor = root
    while not ancestor.exists(): ancestor = ancestor.parent
    if disk_usage_provider(ancestor).free < inspection["missing_expected_bytes"]:
        raise DependencyAcquisitionError("insufficient_dependency_escrow_space")
    root.mkdir(mode=0o700, parents=True, exist_ok=True); (root / "sha256").mkdir(mode=0o700, exist_ok=True)
    results: list[dict[str, Any]] = []
    for entry in entries:
        if entry["artifact_id"] in cached:
            results.append(cached[entry["artifact_id"]]); continue
        final = root / "sha256" / entry["artifact_sha256"]
        staging = Path(tempfile.mkdtemp(prefix=".dependency-", dir=root)); artifact = staging / entry["artifact_filename"]
        try:
            response = transport(entry["artifact_url"])
            with artifact.open("xb", buffering=0) as output:
                os.chmod(artifact, 0o600)
                try: observed, observed_hash = stream_exact(response, output, expected_size=entry["artifact_size_bytes"],
                    expected_sha256=entry["artifact_sha256"], size_error="dependency_artifact_size_mismatch",
                    hash_error="dependency_artifact_hash_mismatch")
                except ExactArtifactError as exc: raise DependencyAcquisitionError(exc.code) from exc
                os.fsync(output.fileno())
            response.stream.close()
            relative = str(Path("sha256") / entry["artifact_sha256"] / entry["artifact_filename"])
            receipt = {**_artifact_receipt_static(entry), "observed_sha256": observed_hash,
                "observed_size_bytes": observed, "verified_relative_path": relative,
                "sanitized_network_destination_hosts": list(response.destination_hosts), "redirect_count": response.redirect_count}
            _write_receipt(staging / "acquisition-receipt.json", receipt)
            fd = os.open(staging, os.O_RDONLY); os.fsync(fd); os.close(fd)
            try: staging.rename(final)
            except OSError:
                winner = _existing_artifact(final, entry)
                if winner is None: raise DependencyAcquisitionError("existing_dependency_escrow_conflict")
                receipt = winner
            results.append(receipt)
        except DependencyAcquisitionError: raise
        except (OSError, ValueError) as exc: raise DependencyAcquisitionError("dependency_acquisition_write_error") from exc
        finally:
            if staging.exists(): shutil.rmtree(staging)
    if len(results) != 5: raise DependencyAcquisitionError("dependency_bundle_incomplete")
    bundle = {**_bundle_static(plan, entries, results, expected_auth["authorization_digest"]),
        "network_performed": any(not r["cache_hit"] for r in results), "download_performed": any(not r["cache_hit"] for r in results),
        "cache_hit_count": sum(bool(r["cache_hit"]) for r in results), "downloaded_count": sum(not r["cache_hit"] for r in results),
    }
    staging = Path(tempfile.mkdtemp(prefix=".bundle-", dir=root))
    try:
        _write_receipt(staging / "dependency-bundle-acquisition-receipt.json", bundle)
        (root / "bundles").mkdir(mode=0o700, exist_ok=True)
        try: staging.rename(bundle_dir)
        except OSError:
            if not bundle_dir.exists(): raise
            # A peer won; recurse through the strict existing-bundle verifier.
            return acquire_dependency_bundle(plan, catalog=catalog, escrow_root=root, authorization=authorization,
                                             execute=True, transport=transport, disk_usage_provider=disk_usage_provider)
        return bundle
    except DependencyAcquisitionError: raise
    except OSError as exc: raise DependencyAcquisitionError("dependency_acquisition_write_error") from exc
    finally:
        if staging.exists(): shutil.rmtree(staging)


def verify_dependency_bundle_custody(plan: Mapping[str, Any], *, catalog: Mapping[str, Any],
                                     escrow_root: Path | str) -> dict[str, Any]:
    """Fully revalidate the five local artifacts and bundle receipt, without network or mutation."""
    _, entries = validate_binding(plan, catalog)
    root = Path(escrow_root).expanduser().absolute()
    receipts: list[dict[str, Any]] = []
    paths: list[Path] = []
    for entry in entries:
        final = root / "sha256" / entry["artifact_sha256"]
        receipt = _existing_artifact(final, entry)
        if receipt is None:
            raise DependencyAcquisitionError("dependency_bundle_not_verified")
        receipts.append(receipt); paths.append(final / entry["artifact_filename"])
    try:
        bundle = _read_json_nofollow(root / "bundles" / plan["bundle_digest"] /
                                     "dependency-bundle-acquisition-receipt.json")
        verified = _verify_bundle_receipt(bundle, plan, entries, receipts,
            authorization_for(plan, root, operator_confirmed=True)["authorization_digest"])
    except (OSError, ValueError, json.JSONDecodeError, DependencyAcquisitionError) as exc:
        raise DependencyAcquisitionError("dependency_bundle_not_verified") from exc
    return {"receipt": verified, "entries": entries, "wheel_paths": paths}
