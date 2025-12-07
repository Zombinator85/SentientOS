"""Stage-3 screenshot planning primitives for SSA form orchestration.

These structures describe deterministic screenshot requests for each logical
SSA page without invoking any browser automation. They exist solely to be
consumed by future orchestration layers.
"""
from __future__ import annotations

from typing import List


class ScreenshotRequest:
    def __init__(self, page: str):
        self.page = page

    def as_dict(self) -> dict:
        return {"page": self.page, "type": "screenshot"}


class ScreenshotPlan:
    def __init__(self, requests: List[ScreenshotRequest]):
        self.requests = requests

    def as_list(self) -> list:
        return [r.as_dict() for r in self.requests]


def build_screenshot_request(page: str) -> ScreenshotRequest:
    return ScreenshotRequest(page)
