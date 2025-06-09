import os, sys, subprocess, time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from privilege_lint import BANNER_ASCII, FUTURE_IMPORT


def test_precommit_speed(tmp_path: Path) -> None:
    script = Path('scripts/precommit_privilege.sh')
    src = Path('dummy.py')
    src.write_text("\n".join(BANNER_ASCII + [FUTURE_IMPORT]), encoding='utf-8')
    start = time.time()
    subprocess.run(['bash', str(script)], check=True, env={**os.environ, 'LUMOS_AUTO_APPROVE':'1'})
    first = time.time() - start
    start = time.time()
    subprocess.run(['bash', str(script)], check=True, env={**os.environ, 'LUMOS_AUTO_APPROVE':'1'})
    second = time.time() - start
    os.remove('dummy.py')
    assert second < 1

