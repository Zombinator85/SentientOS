"""Security reasoning utilities for SentientOS.

This package builds on the cathedral's audit covenant by adding
threat modeling, commit scanning, and validation harnesses inspired by
Aardvark's workflow.
"""

from .threat_model import ThreatModel, ThreatAgent, build_threat_model
from .commit_scanner import Finding, scan_repository
from .validation_harness import ValidationHarness, ValidationResult

__all__ = [
    "ThreatModel",
    "ThreatAgent",
    "build_threat_model",
    "Finding",
    "scan_repository",
    "ValidationHarness",
    "ValidationResult",
]
