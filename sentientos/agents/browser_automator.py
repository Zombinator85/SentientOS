"""Lightweight browser automation harness."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, Mapping, MutableMapping, Optional

import affective_context as ac
from sentientos.autonomy.audit import AutonomyActionLogger
from sentientos.metrics import MetricsRegistry
from sentientos.sensor_provenance import default_provenance_for_constraint


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
        audit_logger: AutonomyActionLogger | None = None,
        council_prompt: Callable[[str, str], bool] | None = None,
    ) -> None:
        self._config = config
        self._driver_factory = driver_factory or (lambda: _DummyDriver())
        self._driver = self._driver_factory()
        self._metrics = metrics or MetricsRegistry()
        self._panic_flag = panic_flag or (lambda: False)
        self._action_window: list[float] = []
        self._last_action: Mapping[str, object] | None = None
        self._audit = audit_logger
        self._council_prompt = council_prompt

    @property
    def enabled(self) -> bool:
        return self._config.enable and not self._panic_flag()

    def open_url(self, url: str) -> None:
        self._require_enabled(url, "open")
        self._driver.open(url)
        self._record_action("open", url)
        self._log("open", "performed", target=url)

    def click(self, selector: str) -> None:
        self._require_enabled(selector, "click")
        self._driver.click(selector)
        self._record_action("click", selector)
        self._log("click", "performed", target=selector)

    def type_text(self, selector: str, text: str) -> None:
        self._require_enabled(selector, "type")
        if self._config.require_quorum_for_post and self._looks_public(selector):
            self._log("type", "blocked", target=selector, reason="quorum_required")
            raise BrowserActionError("posting requires quorum")
        self._driver.type(selector, text)
        self._record_action("type", selector)
        self._log("type", "performed", target=selector)

    def post(self, selector: str, text: str) -> None:
        self._require_enabled(selector, "post")
        if self._config.require_quorum_for_post and not self._request_council("post", selector):
            self._log("post", "blocked", target=selector, reason="council_veto")
            raise BrowserActionError("council_veto")
        self._driver.type(selector, text)
        self._record_action("post", selector)
        self._log("post", "performed", target=selector)

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

    def _request_council(self, action: str, target: str) -> bool:
        if self._council_prompt is None:
            return False
        try:
            approved = self._council_prompt(action, target)
        except Exception:
            return False
        return bool(approved)

    def _log(self, action: str, status: str, **details: object) -> None:
        if not self._audit:
            return
        overlay = ac.capture_affective_context(
            "browser_action",
            overlay={"blocked": 1.0 if status == "blocked" else 0.35, "curiosity": 0.45},
        )
        constraint_id = f"autonomy::browser::{action}"
        provenance = default_provenance_for_constraint(constraint_id)
        assumptions = ("domains_allowlisted", "quorum_required" if self._config.require_quorum_for_post else "quorum_relaxed")
        environment = {"panic": bool(self._panic_flag()), **details}
        self._audit.log(
            "browser",
            action,
            status,
            affective_overlay=overlay,
            constraint_id=constraint_id,
            constraint_justification="browser automation must remain constraint-legible and reviewable",
            sensor_provenance=provenance,
            assumptions=assumptions,
            environment=environment,
            pressure_reason=details.get("reason", status),
            **details,
        )

    def _require_enabled(self, resource: str, action: str) -> None:
        if not self.enabled:
            self._log(action, "blocked", target=resource, reason="disabled")
            raise BrowserActionError("social automation disabled")
        if not self._within_budget():
            self._log(action, "blocked", target=resource, reason="budget_exceeded")
            raise BrowserActionError("social action budget exceeded")
        if not self._is_allowed_domain(resource):
            self._log(action, "blocked", target=resource, reason="domain_not_allowlisted")
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
