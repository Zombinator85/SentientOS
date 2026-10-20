"""Read-only verification for persisted production campaign reports."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .production_self_reflection_campaign import ProductionSelfReflectionCampaign


def verify_persisted_campaign_report(
        campaign_root: Path) -> Mapping[str, Any]:
    """Verify an existing campaign report without recovering or writing custody."""
    campaign = ProductionSelfReflectionCampaign.open_for_read_only_inspection(
        Path(campaign_root)
    )
    return campaign.verify_report()
