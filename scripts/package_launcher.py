from __future__ import annotations
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


def package() -> int:
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
    try:
        subprocess.check_call(cmd)
        log("packaged_ok")
        return 0
    except subprocess.CalledProcessError as exc:
        log(f"packaging_failed:{exc}")
        regenerate_entry()
        return 1


def main() -> int:
    Path("dist").mkdir(exist_ok=True)
    return package()


if __name__ == "__main__":
    raise SystemExit(main())
