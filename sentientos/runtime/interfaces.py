"""Interfaces and type hints for SentientOS runtime cycles."""

from __future__ import annotations

from typing import Any, List, Mapping, MutableMapping, TypedDict


CycleInput = Mapping[str, Any]


class InnerWorldIdentity(TypedDict, total=False):
    summary: str
    events: List[Mapping[str, Any]]
    self_concept: Mapping[str, str]


class InnerWorldReport(TypedDict, total=False):
    cycle_id: int
    qualia: Mapping[str, float]
    identity: InnerWorldIdentity
    metacog: List[Mapping[str, Any]]
    meta: List[Mapping[str, Any]]
    ethics: Mapping[str, Any]
    timestamp: float


class SimulationReport(TypedDict, total=False):
    simulated: bool
    hypothetical_state: Mapping[str, Any]
    report: InnerWorldReport


class CycleOutput(TypedDict, total=False):
    cycle_state: MutableMapping[str, Any]
    innerworld: InnerWorldReport
    simulation: SimulationReport
    ethics: Mapping[str, Any]
    innerworld_history_summary: Mapping[str, Any]
    innerworld_reflection: Mapping[str, Any]
    narrative_chapters: list[Mapping[str, Any]]
    identity_summary: Mapping[str, Any]
