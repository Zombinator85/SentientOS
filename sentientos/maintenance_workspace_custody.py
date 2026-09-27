"""Backend-neutral deterministic custody for maintenance implementation workspaces.

This module deliberately knows nothing about Codex or local-model activation.  It
owns the common configuration contract and exposes the exact-base workspace and
change-custody operations used by implementation backends.
"""
from __future__ import annotations

import hashlib
import json
import fnmatch
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from sentientos import maintenance_task_journal as journal

CONFIG_SCHEMA = "sentientos.maintenance_workspace_custody_config:v1"
WORKTREE_SCHEMA = "sentientos.maintenance_implementation_worktree:v1"
CHANGE_SCHEMA = "sentientos.maintenance_implementation_change_manifest:v1"


def digest(value: Any) -> str:
    return str(journal.sha256_digest(value))


@dataclass(frozen=True)
class WorkspaceCustodyConfig:
    configuration_id: str
    repository_identity: str
    repository_root: Path
    external_workspace_root: Path
    external_state_root: Path
    git_executable: Path
    git_executable_digest: str | None = None
    maximum_instruction_bytes: int = 65_536
    process_timeout_seconds: float = 30.0
    configuration_constraints: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "WorkspaceCustodyConfig":
        allowed = set(cls.__dataclass_fields__) | {"schema_version", "configuration_digest"}
        if set(value) != allowed or value.get("schema_version") != CONFIG_SCHEMA:
            raise ValueError("workspace_custody_configuration_invalid")
        kwargs = {key: value[key] for key in cls.__dataclass_fields__}
        for key in ("repository_root", "external_workspace_root", "external_state_root", "git_executable"):
            raw = Path(str(kwargs[key])).expanduser()
            if raw.is_symlink():
                raise ValueError("workspace_custody_symlink")
            kwargs[key] = raw.resolve(strict=key in {"repository_root", "git_executable"})
        kwargs["configuration_constraints"] = tuple(kwargs["configuration_constraints"])
        config = cls(**kwargs)
        if value["configuration_digest"] != config.to_dict()["configuration_digest"]:
            raise ValueError("workspace_custody_configuration_digest_invalid")
        config.validate()
        return config

    def validate(self) -> None:
        repo = self.repository_root.resolve(strict=True)
        git_dir = (repo / ".git").resolve(strict=True)
        for root in (self.external_workspace_root, self.external_state_root):
            if root.is_symlink():
                raise ValueError("workspace_custody_symlink")
            resolved = root.resolve(strict=False)
            if resolved == repo or repo in resolved.parents or resolved == git_dir or git_dir in resolved.parents:
                raise ValueError("workspace_custody_inside_repository")
        executable = self.git_executable.resolve(strict=True)
        if not executable.is_file() or executable != self.git_executable:
            raise ValueError("git_executable_not_realpath")
        actual = "sha256:" + hashlib.sha256(executable.read_bytes()).hexdigest()
        if self.git_executable_digest not in (None, actual):
            raise ValueError("git_executable_digest_mismatch")
        if self.maximum_instruction_bytes < 1 or self.process_timeout_seconds <= 0:
            raise ValueError("workspace_custody_bounds_invalid")

    def to_dict(self) -> dict[str, Any]:
        body = {
            "schema_version": CONFIG_SCHEMA,
            **{
                key: str(value) if isinstance(value, Path) else list(value) if isinstance(value, tuple) else value
                for key, value in self.__dict__.items()
            },
            "configuration_digest": "",
        }
        body["configuration_digest"] = digest({key: value for key, value in body.items() if key != "configuration_digest"})
        return body


def prepare_worktree(config: WorkspaceCustodyConfig, lease: Mapping[str, Any], session_id: str, *, recovery: bool = False) -> dict[str, Any]:
    root=config.external_workspace_root/str(lease["task_id"])/session_id
    if config.repository_root in root.parents or config.external_state_root in root.parents or root.is_symlink(): raise ValueError("foreman_workspace_invalid")
    descriptor=config.external_state_root/"maintenance_worktrees"/(session_id+".json")
    if recovery and root.exists() and descriptor.exists():
        prior=json.loads(descriptor.read_text()); head=_run(config,["rev-parse","HEAD"],root).stdout.strip()
        if prior.get("worktree_root")!=str(root) or prior.get("base_sha")!=lease["base_sha"] or head!=lease["base_sha"]: raise ValueError("foreman_workspace_invalid")
        return dict(prior)
    argv=[str(config.git_executable),"worktree","add","--detach",str(root),str(lease["base_sha"])]
    if root.exists():
        head=_run(config,["rev-parse","HEAD"],root).stdout.strip(); clean=_run(config,["status","--porcelain=v1","--untracked-files=all"],root).stdout
        if head!=lease["base_sha"] or clean: raise ValueError("foreman_workspace_invalid")
        status="reused"
    else:
        root.parent.mkdir(parents=True,exist_ok=True); completed=subprocess.run(argv,cwd=config.repository_root,text=True,capture_output=True,shell=False,timeout=config.process_timeout_seconds)
        if completed.returncode: raise ValueError("foreman_workspace_invalid:"+completed.stderr[:200])
        status="created"
    head=_run(config,["rev-parse","HEAD"],root).stdout.strip(); clean=_run(config,["status","--porcelain=v1","--untracked-files=all"],root).stdout
    files=_run(config,["ls-files"],root).stdout.splitlines()
    creation={"schema_version":WORKTREE_SCHEMA,"worktree_id":"mwt_"+hashlib.sha256(journal.canonical_json_bytes({"t":lease["task_id"],"s":session_id})).hexdigest()[:32],"worktree_digest":"","task_id":lease["task_id"],"lease_id":lease["lease_id"],"lease_digest":lease["lease_digest"],"session_id":session_id,"repository_identity":config.repository_identity,"source_repository_root":str(config.repository_root),"worktree_root":str(root),"workspace_root_identity":digest(str(config.external_workspace_root)),"base_sha":lease["base_sha"],"git_executable_identity":{"path":str(config.git_executable),"digest":_path_digest(config.git_executable)},"creation_argv_digest":digest(argv),"initial_head":head,"initial_cleanliness_proof":{"porcelain":clean},"initial_tracked_file_manifest_digest":digest(files),"creation_status":status,"retained_for_validation":True}
    creation["worktree_digest"]=digest({k:v for k,v in creation.items() if k!="worktree_digest"}); write_json(descriptor,creation,immutable=False); return creation


def changed_manifest(config: WorkspaceCustodyConfig, lease: Mapping[str, Any], worktree: Mapping[str, Any]) -> dict[str, Any]:
    root=Path(str(worktree["worktree_root"])); base=str(lease["base_sha"]); head=_run(config,["rev-parse","HEAD"],root).stdout.strip()
    status=_run(config,["status","--porcelain=v1","--untracked-files=all"],root).stdout.splitlines(); paths=[line[3:] for line in status if line]
    stats=_run(config,["diff","--numstat","HEAD","--",*paths],root).stdout.splitlines() if paths else []
    additions=deletions=0
    for stat in stats:
        added,deleted,*_=stat.split("\t"); additions+=int(added) if added.isdigit() else 0; deletions+=int(deleted) if deleted.isdigit() else 0
    entries=[]
    for relative in paths:
        path=(root/relative).resolve(); kind="missing" if not path.exists() else "symlink" if path.is_symlink() else "file" if path.is_file() else "directory"
        entries.append({"path":relative,"status":"changed","tracked":not any(item.startswith("?? "+relative) for item in status),"file_type":kind,"byte_size":path.stat().st_size if path.exists() and not path.is_dir() else 0,"content_digest":_path_digest(path) if path.exists() and path.is_file() and not path.is_symlink() and path.stat().st_size<1_000_000 else None,"symlink_escapes_worktree":path.is_symlink() and root not in path.resolve().parents})
    admitted=list(lease["admitted_subject_paths"]); forbidden=list(lease.get("forbidden_path_patterns",()))
    outside=[path for path in paths if not any(path==allowed.rstrip("/") or path.startswith(allowed.rstrip("/")+"/") for allowed in admitted)]
    findings=[]
    if len(paths)>int(lease["maximum_file_count"]): findings.append("file_count_exceeded")
    if additions+deletions>int(lease["maximum_changed_line_count"]): findings.append("changed_line_count_exceeded")
    result={"schema_version":CHANGE_SCHEMA,"task_id":lease["task_id"],"session_id":worktree["session_id"],"worktree_id":worktree["worktree_id"],"initial_head":base,"terminal_head":head,"changed_paths":paths,"entries":entries,"aggregate_file_count":len(paths),"aggregate_changed_line_count":additions+deletions,"additions":additions,"deletions":deletions,"out_of_scope_paths":outside,"forbidden_paths":[path for path in paths if any(fnmatch.fnmatch(path,pattern) for pattern in forbidden)],"budget_findings":findings,"manifest_digest":""}
    result["manifest_digest"]=digest({k:v for k,v in result.items() if k!="manifest_digest"}); write_json(config.external_state_root/"maintenance_change_manifests"/(str(worktree["session_id"])+".json"),result,immutable=False)
    patch=_run(config,["diff","--binary","HEAD","--"],root).stdout.encode(); patch_path=config.external_state_root/"maintenance_patches"/(str(worktree["session_id"])+".patch"); patch_path.parent.mkdir(parents=True,exist_ok=True); patch_path.write_bytes(patch)
    result["patch_digest"]="sha256:"+hashlib.sha256(patch).hexdigest(); result["patch_path"]=str(patch_path); return result


def _run(config: WorkspaceCustodyConfig, arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(config.git_executable),*arguments],cwd=cwd,text=True,input="",capture_output=True,shell=False,timeout=config.process_timeout_seconds,check=False)


def _path_digest(path: Path) -> str | None:
    try:
        if path.is_file() and not path.is_symlink(): return "sha256:"+hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError: return None
    return None


def write_json(path: Path, value: Mapping[str, Any], immutable: bool = True) -> str:
    data = journal.canonical_json_bytes(value) + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if immutable and path.exists():
        if path.is_symlink() or path.read_bytes() != data:
            raise ValueError("immutable_artifact_conflict")
        return digest(value)
    if immutable:
        import os
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
    else:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(path)
    return digest(value)
