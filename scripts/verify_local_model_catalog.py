"""Structural verifier for curator promotion and pure deployment consumption."""
from __future__ import annotations

import ast
from pathlib import Path


def _calls(source: str) -> set[str]:
    tree = ast.parse(source)
    return {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}


def main() -> int:
    escrow = Path("hf_intake/escrow.py").read_text(encoding="utf-8")
    discovery = Path("hf_intake/discovery.py").read_text(encoding="utf-8")
    promotion = Path("hf_intake/production_catalog.py").read_text(encoding="utf-8")
    catalog = Path("sentientos/local_model_catalog.py").read_text(encoding="utf-8")
    selector = Path("sentientos/local_model_selection.py").read_text(encoding="utf-8")
    findings: list[str] = []
    promotion_calls = _calls(promotion)
    if "validate_manifest" not in promotion_calls:
        findings.append("promotion_missing_full_manifest_validation")
    if "_hash" not in promotion_calls:
        findings.append("promotion_missing_independent_hash")
    if "source_artifact_filename" not in discovery or "artifact_filename" not in discovery:
        findings.append("escrow_source_identity_not_separate")
    if "write_source_record(source_path, candidate, escrow_path.name, artifact_filename)" not in escrow:
        findings.append("escrow_does_not_preserve_upstream_artifact_path")
    promotion_attributes = {node.attr for node in ast.walk(ast.parse(promotion)) if isinstance(node, ast.Attribute)}
    if "_read_checksum_sidecar" not in promotion_calls or 'getattr(os, "O_NOFOLLOW", 0)' not in promotion:
        findings.append("promotion_missing_checksum_or_nofollow_custody")
    if "os.replace" in promotion or "os.rename" in promotion or "link" not in promotion_attributes:
        findings.append("publication_not_no_clobber")
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
    function = next(node for node in ast.parse(selector).body
                    if isinstance(node, ast.FunctionDef) and node.name == "plan_local_model_selection_catalog")
    function_source = ast.get_source_segment(selector, function) or ""
    if "escrow_path" in function_source or "validate_manifest" in function_source:
        findings.append("production_selector_consumes_curator_identity")
    print("local_model_catalog_boundary_verified" if not findings else "local_model_catalog_boundary_failed: " + ", ".join(findings))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
