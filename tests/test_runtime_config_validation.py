from __future__ import annotations

import pytest

from sentientos.config import ConfigValidationError, RuntimeConfig, validate_runtime_config


def test_social_interactive_web_requires_allowlist() -> None:
    config = RuntimeConfig()
    config.social.enable = True
    config.social.allow_interactive_web = True
    config.social.domains_allowlist = ()

    with pytest.raises(ConfigValidationError, match="domains_allowlist"):
        validate_runtime_config(config)


def test_social_interactive_web_requires_enable() -> None:
    config = RuntimeConfig()
    config.social.enable = False
    config.social.allow_interactive_web = True
    config.social.domains_allowlist = ("example.com",)

    with pytest.raises(ConfigValidationError, match="social\\.enable"):
        validate_runtime_config(config)
