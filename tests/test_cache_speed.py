import os
import sys
import subprocess
from pathlib import Path


from sentientos.privilege_lint import BANNER_ASCII, FUTURE_IMPORT


def test_precommit_cache(tmp_path: Path) -> None:
    script = Path('scripts/precommit_privilege.sh')
    src = Path('dummy.py')
    stamp = Path('.git/.privilege_lint.gitcache')
    src.write_text("\n".join(BANNER_ASCII + [FUTURE_IMPORT]), encoding='utf-8')
    if stamp.exists():
        stamp.unlink()
    try:
        subprocess.run(['bash', str(script)], check=True, env={**os.environ, 'LUMOS_AUTO_APPROVE':'1'})
        result = subprocess.run(['bash', str(script)], check=True, capture_output=True, text=True, env={**os.environ, 'LUMOS_AUTO_APPROVE':'1'})
        assert 'cache hit' in result.stdout
    finally:
        src.unlink(missing_ok=True)
        stamp.unlink(missing_ok=True)

