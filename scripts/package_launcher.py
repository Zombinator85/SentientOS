"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from logging_config import get_log_path
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

LOG_FILE = get_log_path("package_launcher.log")


def log(msg: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


def regenerate_entry() -> None:
    script = Path("scripts/fix_entrypoint_banners.py")
    if script.exists():
        subprocess.call([sys.executable, str(script), "cathedral_launcher.py"])


def run(cmd: list[str]) -> int:
    try:
        subprocess.check_call(cmd)
        return 0
    except subprocess.CalledProcessError as exc:
        log(f"packaging_failed:{exc}")
        regenerate_entry()
        return 1


def package_windows() -> int:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--distpath",
        "dist",
        "--name",
        "cathedral_launcher",
        "cathedral_launcher.py",
    ]
    res = run(cmd)
    if res == 0:
        log("packaged_windows_ok")
    return res


def notarize_mac(app_path: Path) -> None:
    if not shutil.which("codesign"):
        log("codesign_missing")
        return
    try:
        subprocess.check_call(["codesign", "--force", "--deep", "--sign", "-", str(app_path)])
    except subprocess.CalledProcessError as exc:
        log(f"codesign_failed:{exc}")
        return
    if shutil.which("xcrun") and os.environ.get("APPLE_ID") and os.environ.get("APPLE_PASSWORD"):
        zip_path = shutil.make_archive(str(app_path), "zip", root_dir=app_path)
        try:
            subprocess.check_call([
                "xcrun",
                "altool",
                "--notarize-app",
                "--primary-bundle-id",
                "sentientos.cathedral",
                "--username",
                os.environ["APPLE_ID"],
                "--password",
                os.environ["APPLE_PASSWORD"],
                "--file",
                zip_path,
            ])
            log("notarization_ok")
        except subprocess.CalledProcessError as exc:
            log(f"notarization_failed:{exc}")
    else:
        log("notarization_skipped")


def package_mac() -> int:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--windowed",
        "--distpath",
        "dist",
        "--name",
        "cathedral_launcher",
        "cathedral_launcher.py",
    ]
    res = run(cmd)
    if res == 0:
        app = Path("dist") / "cathedral_launcher.app"
        if app.exists():
            notarize_mac(app)
        log("packaged_mac_ok")
    return res


def package_linux() -> int:
    return package_windows()


def main() -> int:
    parser = argparse.ArgumentParser(description="Bundle cathedral launcher")
    parser.add_argument(
        "--platform",
        choices=["auto", "windows", "mac"],
        default="auto",
        help="Target platform",
    )
    args = parser.parse_args()

    Path("dist").mkdir(exist_ok=True)

    plat = args.platform
    if plat == "auto":
        if sys.platform.startswith("win"):
            plat = "windows"
        elif sys.platform == "darwin":
            plat = "mac"
        else:
            plat = "linux"

    if plat == "windows":
        return package_windows()
    if plat == "mac":
        return package_mac()
    return package_linux()


if __name__ == "__main__":
    raise SystemExit(main())
