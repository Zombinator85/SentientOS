"""Structural verifier for curator promotion and pure deployment consumption."""
from __future__ import annotations

import ast
from pathlib import Path


def _calls(source: str) -> set[str]:
    tree = ast.parse(source)
    return {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)


def _call_names(node: ast.AST) -> list[str]:
    calls: list[tuple[int, int, str]] = []
    for item in ast.walk(node):
        if not isinstance(item, ast.Call):
            continue
        name = item.func.id if isinstance(item.func, ast.Name) else item.func.attr if isinstance(item.func, ast.Attribute) else ""
        calls.append((item.lineno, item.col_offset, name))
    return [name for _, _, name in sorted(calls)]


def _assigned_value(tree: ast.Module, name: str) -> ast.expr | None:
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name):
            return node.value
    return None


def _is_dir_fd_capability(value: ast.expr | None, function_name: str) -> bool:
    return bool(
        isinstance(value, ast.Compare)
        and len(value.ops) == 1
        and isinstance(value.ops[0], ast.In)
        and len(value.comparators) == 1
        and isinstance(value.left, ast.Attribute)
        and isinstance(value.left.value, ast.Name)
        and value.left.value.id == "os"
        and value.left.attr == function_name
        and isinstance(value.comparators[0], ast.Attribute)
        and isinstance(value.comparators[0].value, ast.Name)
        and value.comparators[0].value.id == "os"
        and value.comparators[0].attr == "supports_dir_fd"
    )


def main() -> int:
    escrow = Path("hf_intake/escrow.py").read_text(encoding="utf-8")
    discovery = Path("hf_intake/discovery.py").read_text(encoding="utf-8")
    promotion = Path("hf_intake/production_catalog.py").read_text(encoding="utf-8")
    catalog = Path("sentientos/local_model_catalog.py").read_text(encoding="utf-8")
    selector = Path("sentientos/local_model_selection.py").read_text(encoding="utf-8")
    findings: list[str] = []
    promotion_tree = ast.parse(promotion)
    promotion_calls = _calls(promotion)
    promote = _function(promotion_tree, "promote_manifest")
    promote_calls = _call_names(promote)
    if "validate_manifest" in promote_calls or "validate_manifest_data" not in promote_calls:
        findings.append("promotion_missing_snapshot_manifest_validation")
    if promote_calls.index("_read_json_evidence") > promote_calls.index("validate_manifest_data"):
        findings.append("promotion_validates_before_safe_manifest_snapshot")
    if sum(name == "_read_json_evidence" for name in promote_calls) != 1 or "_read_at" not in promote_calls:
        findings.append("promotion_manifest_or_source_snapshot_count_changed")
    if "read_text" in promote_calls or "read_bytes" in promote_calls:
        findings.append("promotion_uses_unsafe_path_read")
    if "_hash" not in promotion_calls:
        findings.append("promotion_missing_independent_hash")
    if "source_artifact_filename" not in discovery or "artifact_filename" not in discovery:
        findings.append("escrow_source_identity_not_separate")
    if "write_source_record(source_path, candidate, escrow_path.name, artifact_filename)" not in escrow:
        findings.append("escrow_does_not_preserve_upstream_artifact_path")
    promotion_attributes = {node.attr for node in ast.walk(promotion_tree) if isinstance(node, ast.Attribute)}
    if "_read_checksum_sidecar" not in promotion_calls or 'getattr(os, "O_NOFOLLOW", 0)' not in promotion:
        findings.append("promotion_missing_checksum_or_nofollow_custody")
    if "os.replace" in promotion or "os.rename" in promotion or "linkat" not in promotion:
        findings.append("publication_not_no_clobber")
    writer = _function(promotion_tree, "write_promoted_catalog")
    writer_calls = _call_names(writer)
    read_guard = _function(promotion_tree, "_require_read_custody")
    publication_guard = _function(promotion_tree, "_require_publication_custody")
    read_capability = "_READ_DIR_FD_CAPABLE"
    mkdir_capability = "_PUBLICATION_MKDIR_DIR_FD_CAPABLE"
    if not _is_dir_fd_capability(_assigned_value(promotion_tree, read_capability), "open"):
        findings.append("read_dir_fd_capability_not_derived_from_open_only")
    if not _is_dir_fd_capability(_assigned_value(promotion_tree, mkdir_capability), "mkdir"):
        findings.append("publication_mkdir_dir_fd_capability_not_separate")
    read_names = {node.id for node in ast.walk(read_guard) if isinstance(node, ast.Name)}
    publication_names = {node.id for node in ast.walk(publication_guard) if isinstance(node, ast.Name)}
    if read_capability not in read_names or mkdir_capability in read_names:
        findings.append("curator_read_custody_not_isolated_from_mkdir_capability")
    if mkdir_capability not in publication_names:
        findings.append("publication_custody_missing_mkdir_capability")
    if {"_O_TMPFILE", "_LINKAT"} & read_names:
        findings.append("curator_read_custody_requires_publication_primitives")
    if "_require_read_custody" not in _call_names(publication_guard):
        findings.append("publication_custody_does_not_extend_read_custody")
    if "mkdir" in writer_calls or "mkstemp" in writer_calls or writer_calls.index("_prepare_publication_parent") > writer_calls.index("open"):
        findings.append("publication_parent_not_prepared_before_staging")
    if ("_revalidate_chain" not in writer_calls or "_link_staged_inode" not in writer_calls
            or writer_calls.index("_revalidate_chain") > writer_calls.index("_link_staged_inode")):
        findings.append("publication_parent_not_revalidated_before_link")
    prepare = _function(promotion_tree, "_prepare_publication_parent")
    prepare_calls = _call_names(prepare)
    if "mkdir" not in prepare_calls or "open" not in prepare_calls or "fstat" not in prepare_calls:
        findings.append("publication_missing_descriptor_relative_descent")
    structural_tokens = ("dir_fd=parent_fd", "_O_TMPFILE", "_AT_EMPTY_PATH", "_AT_SYMLINK_FOLLOW",
                         'f"/proc/self/fd/{staged_fd}"', "_link_staged_inode(fd, parent_fd",
                         "staged_identity", "published_identity != staged_identity", "published != payload",
                         "os.fsync(parent_fd)", "residual entry preserved", "dir_fd=descriptor",
                         "_open_regular_at(parent_fd")
    findings.extend(f"publication_descriptor_custody_missing:{token}" for token in structural_tokens if token not in promotion)
    if ("os.open(output_path" in promotion or "tempfile.mkstemp" in promotion or "os.unlink(temporary)" in promotion
            or "os.unlink(output_path.name" in promotion):
        findings.append("publication_regressed_to_full_path_operation")
    link_call = _function(promotion_tree, "_call_linkat")
    link_call_source = ast.get_source_segment(promotion, link_call) or ""
    if (link_call_source.count("_AT_SYMLINK_FOLLOW") != 1
            or 'f"/proc/self/fd/{staged_fd}"' not in link_call_source
            or "old_path" in [argument.arg for argument in link_call.args.args]):
        findings.append("publication_procfs_fd_route_not_strictly_bound")
    if len([node for node in ast.walk(promotion_tree) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name) and node.func.id == "_call_linkat"]) != 2:
        findings.append("arbitrary_source_path_may_reach_linkat")
    if "source_filename = artifact_path" in promotion:
        findings.append("promotion_reconstructs_source_filename")
    if "validate_local_model_catalog" not in _calls(selector):
        findings.append("selector_missing_catalog_validator")
    forbidden_catalog = {"open", "stat", "exists", "is_file", "urlopen", "requests", "socket", "Llama"}
    used_catalog = _calls(catalog)
    findings.extend(f"catalog_forbidden_call:{name}" for name in sorted(used_catalog & forbidden_catalog))
    forbidden_imports = {"requests", "httpx", "huggingface_hub", "socket", "llama_cpp", "subprocess"}
    for path, source in (("catalog", catalog), ("selector", selector)):
        tree = ast.parse(source)
        imports = {alias.name.split(".")[0] for node in ast.walk(tree)
                   if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names}
        findings.extend(f"{path}_forbidden_import:{name}" for name in sorted(imports & forbidden_imports))
    required_catalog = ("TRUSTED_ARTIFACT_HOSTS", "huggingface.co", "is_immutable_source_revision",
                        "validate_execution_routes", "artifact_content_address")
    findings.extend(f"catalog_missing:{token}" for token in required_catalog if token not in catalog)
    function = _function(ast.parse(selector), "plan_local_model_selection_catalog")
    function_source = ast.get_source_segment(selector, function) or ""
    if "escrow_path" in function_source or "validate_manifest" in function_source or {"open", "read_bytes", "read_text"} & set(_call_names(function)):
        findings.append("production_selector_consumes_curator_identity")
    print("local_model_catalog_boundary_verified" if not findings else "local_model_catalog_boundary_failed: " + ", ".join(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
