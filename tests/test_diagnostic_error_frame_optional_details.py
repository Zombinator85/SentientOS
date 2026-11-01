from __future__ import annotations

import pytest

from sentientos.diagnostics.error_frame import FailedPhase, frame_exception

pytestmark = pytest.mark.no_legacy_skip


def test_missing_optional_exception_metadata_is_preserved_as_null() -> None:
    frame = frame_exception(FileNotFoundError("missing"), failed_phase=FailedPhase.IMPORT)

    assert frame.technical_details["missing_path"] is None
