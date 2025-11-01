from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

LFS_POINTER_HEADER = b"version https://git-lfs.github.com/spec/v1"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _is_lfs_pointer(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(len(LFS_POINTER_HEADER))
    except FileNotFoundError:
        return False
    return head == LFS_POINTER_HEADER


def _extract_archive(archive: Path, destination: Path, force: bool) -> Path:
    if _is_lfs_pointer(archive):
        raise SystemExit(
            "Git LFS payload for SentientOSsecondary.zip is missing. "
            "Run `git lfs pull` before extracting."
        )

    if destination.exists():
        if force:
            shutil.rmtree(destination)
        else:
            print(f"Destination {destination} already exists; skipping extraction.")
            return destination

    with zipfile.ZipFile(archive) as payload:
        members = [
            Path(info.filename)
            for info in payload.infolist()
            if info.filename and not info.filename.startswith("__MACOSX")
        ]
        roots = {parts[0] for parts in (m.parts for m in members) if parts}

        if len(roots) == 1:
            root_name = next(iter(roots))
            payload.extractall(archive.parent)
            extracted_root = archive.parent / root_name
            if extracted_root != destination:
                if destination.exists():
                    shutil.rmtree(destination)
                extracted_root.rename(destination)
        else:
            destination.mkdir(parents=True, exist_ok=True)
            payload.extractall(destination)

    print(f"Extracted SentientOSsecondary to {destination}")
    return destination


def _verify_structure(root: Path) -> None:
    expected = [
        root / "llama.cpp" / "examples" / "server" / "CMakeLists.txt",
        root / "llama.cpp" / "common" / "CMakeLists.txt",
    ]
    missing = [str(path) for path in expected if not path.exists()]
    if missing:
        raise SystemExit(
            "SentientOSsecondary is missing expected build files:\n" + "\n".join(missing)
        )

    build_dir = root / "build"
    if not build_dir.exists():
        raise SystemExit(
            "SentientOSsecondary build directory is missing. "
            "Run the CUDA asset generation steps or refresh the archive."
        )

    print("SentientOSsecondary structure validated:")
    print(f"- llama.cpp root: {root / 'llama.cpp'}")
    print(f"- build directory: {build_dir}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate or extract the SentientOSsecondary build payload."
    )
    parser.add_argument(
        "--extract",
        action="store_true",
        help="Extract the Git LFS archive before running validation.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-extract even if the destination already exists.",
    )
    parser.add_argument(
        "--destination",
        type=Path,
        default=_repo_root() / "SentientOSsecondary",
        help="Override the extraction directory (defaults to SentientOSsecondary/).",
    )
    args = parser.parse_args(argv)

    archive = _repo_root() / "SentientOSsecondary.zip"
    if not archive.exists():
        print(f"Archive not found: {archive}", file=sys.stderr)
        return 1

    destination = args.destination
    if args.extract:
        destination = _extract_archive(archive, destination, args.force)

    if not destination.exists():
        print(
            "Destination directory missing. Use --extract to unpack the archive first.",
            file=sys.stderr,
        )
        return 1

    _verify_structure(destination)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
