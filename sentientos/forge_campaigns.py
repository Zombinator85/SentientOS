"""Campaign specs for multi-goal Forge recovery flows."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CampaignSpec:
    campaign_id: str
    goals: list[str]
    stop_on_failure: bool = True


REGISTRY: dict[str, CampaignSpec] = {
    "ci_baseline_recovery": CampaignSpec(
        campaign_id="ci_baseline_recovery",
        goals=["repo_green_storm"],
        stop_on_failure=True,
    ),
}


def resolve_campaign(campaign_id: str) -> CampaignSpec | None:
    return REGISTRY.get(campaign_id)
