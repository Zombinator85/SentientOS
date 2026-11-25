#!/usr/bin/env python3
"""Create a private, create-only key for matched task commitments."""
from __future__ import annotations

import argparse
import hashlib
import os
import secrets
import stat
import sys
from pathlib import Path


def create_key(path: Path) -> str:
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("task_commitment_key_requires_posix_private_custody")
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise ValueError("task_commitment_key_parent_invalid")
    directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    payload = secrets.token_hex(32).encode("ascii")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
        try:
            metadata = os.fstat(descriptor)
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                    or metadata.st_mode & 0o077):
                raise ValueError("task_commitment_key_file_not_private")
            view = memoryview(payload)
            while view:
                written = os.write(descriptor, view)
                if written <= 0:
                    raise OSError("task_commitment_key_short_write")
                view = view[written:]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    digest = create_key(args.output)
    print(f"created_private_task_commitment_key:{args.output}")
    print(f"task_commitment_key_file_sha256:{digest}")
    print("key_material_printed:false")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as exc:
        print(f"task_commitment_key_error:{exc}", file=sys.stderr)
        raise SystemExit(2)
