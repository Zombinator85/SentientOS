from __future__ import annotations

import pytest

from scripts.verify_context_hygiene_prompt_boundaries import _identifier_contains_forbidden_field

pytestmark = pytest.mark.no_legacy_skip


def test_identifier_check_handles_missing_source_path() -> None:
    assert _identifier_contains_forbidden_field("api_key") == "api_key"
