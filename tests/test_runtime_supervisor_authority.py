from pathlib import Path
import pytest
from scripts.verify_runtime_supervisor_authority import verify
pytestmark = pytest.mark.no_legacy_skip
def test_runtime_supervisor_authority_boundary() -> None:
    assert verify(Path.cwd()) == []
