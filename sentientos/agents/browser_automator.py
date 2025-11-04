"""Lightweight browser automation harness."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, Mapping, MutableMapping, Optional

from sentientos.metrics import MetricsRegistry


@dataclass
class SocialConfig:
    enable: bool = False
    allow_interactive_web: bool = False
    domains_allowlist: Iterable[str] = field(default_factory=tuple)
    daily_action_budget: int = 0
    require_quorum_for_post: bool = True


class BrowserActionError(RuntimeError):
    pass


class BrowserAutomator:
    def __init__(
        self,
        config: SocialConfig,
        *,
        driver_factory: Callable[[], object] | None = None,
        metrics: MetricsRegistry | None = None,
        panic_flag: Callable[[], bool] | None = None,
    ) -> None:
        self._config = config
        self._driver_factory = driver_factory or (lambda: _DummyDriver())
        self._driver = self._driver_factory()
        self._metrics = metrics or MetricsRegistry()
        self._panic_flag = panic_flag or (lambda: False)
        self._action_window: list[float] = []
        self._last_action: Mapping[str, object] | None = None

    @property
    def enabled(self) -> bool:
        return self._config.enable and not self._panic_flag()

    def open_url(self, url: str) -> None:
        self._require_enabled(url)
        self._driver.open(url)
        self._record_action("open", url)

    def click(self, selector: str) -> None:
        self._require_enabled(selector)
        self._driver.click(selector)
        self._record_action("click", selector)

    def type_text(self, selector: str, text: str) -> None:
        self._require_enabled(selector)
        if self._config.require_quorum_for_post and self._looks_public(selector):
            raise BrowserActionError("posting requires quorum")
        self._driver.type(selector, text)
        self._record_action("type", selector)

    def post(self, selector: str, text: str) -> None:
        self._require_enabled(selector)
        if self._config.require_quorum_for_post:
            raise BrowserActionError("quorum required for social posting")
        self._driver.type(selector, text)
        self._record_action("post", selector)

    def status(self) -> Mapping[str, object]:
        remaining = self._remaining_budget(time.time())
        return {
            "status": "healthy" if self.enabled else "disabled",
            "last_action": self._last_action,
            "budget_remaining": remaining,
        }

    def _record_action(self, kind: str, target: str) -> None:
        now = time.time()
        self._action_window.append(now)
        self._last_action = {"kind": kind, "target": target, "ts": now}
        labels = {"kind": kind}
        self._metrics.increment("sos_web_actions_total", labels=labels)
        if kind == "post":
            self._metrics.increment("sos_social_posts_total")
        elif kind in {"reply"}:
            self._metrics.increment("sos_social_replies_total")

    def _require_enabled(self, resource: str) -> None:
        if not self.enabled:
            raise BrowserActionError("social automation disabled")
        if not self._within_budget():
            raise BrowserActionError("social action budget exceeded")
        if not self._is_allowed_domain(resource):
            raise BrowserActionError("domain not allowlisted")

    def _within_budget(self) -> bool:
        now = time.time()
        self._action_window = [ts for ts in self._action_window if ts >= now - 86400.0]
        return len(self._action_window) < max(int(self._config.daily_action_budget), 0)

    def _remaining_budget(self, now: float) -> int:
        self._action_window = [ts for ts in self._action_window if ts >= now - 86400.0]
        return max(int(self._config.daily_action_budget) - len(self._action_window), 0)

    def _is_allowed_domain(self, resource: str) -> bool:
        for domain in self._config.domains_allowlist:
            if domain and domain in resource:
                return True
        return False

    def _looks_public(self, selector: str) -> bool:
        return any(token in selector.lower() for token in {"tweet", "post", "publish"})


class _DummyDriver:
    def open(self, url: str) -> None:  # pragma: no cover - trivial behaviour
        self.last = ("open", url)

    def click(self, selector: str) -> None:  # pragma: no cover
        self.last = ("click", selector)

    def type(self, selector: str, text: str) -> None:  # pragma: no cover
        self.last = ("type", selector, text)


__all__ = ["BrowserAutomator", "BrowserActionError", "SocialConfig"]

