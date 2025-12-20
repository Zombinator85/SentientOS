from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict


class ClassificationError(RuntimeError):
    """Raised when hardware requirements cannot be determined deterministically."""


QUANTIZATION_RAM_GB: Dict[str, int] = {
    "q2": 6,
    "q3": 6,
    "q4": 8,
    "q5": 12,
    "q6": 16,
    "q8": 24,
    "f16": 32,
}


@dataclass
class HardwareRequirements:
    architecture: str
    avx: bool
    avx2: bool
    avx512: bool
    ram_gb_min: int
    gpu: bool
    quantization: str

    def as_dict(self) -> dict:
        return {
            "architecture": self.architecture,
            "avx": self.avx,
            "avx2": self.avx2,
            "avx512": self.avx512,
            "ram_gb_min": self.ram_gb_min,
            "gpu": self.gpu,
            "quantization": self.quantization,
        }


def _detect_quantization(name: str) -> str:
    normalized = name.lower()
    match = re.search(r"q(\d)(?=[^0-9a-z]|$)", normalized)
    if match:
        return f"q{match.group(1)}"
    if "f16" in normalized:
        return "f16"
    raise ClassificationError(f"Unable to detect quantization in {name}")


def classify(artifact_path: Path, size_bytes: int) -> HardwareRequirements:
    quantization = _detect_quantization(artifact_path.name)
    ram_gb = QUANTIZATION_RAM_GB.get(quantization)
    if ram_gb is None:
        raise ClassificationError(f"Unknown quantization level: {quantization}")

    estimated_runtime_ram = max(ram_gb, math.ceil((size_bytes * 2) / (1024**3)))
    requires_avx2 = quantization not in {"q2", "q3"}
    requires_avx512 = quantization in {"q8", "f16"}

    return HardwareRequirements(
        architecture="x86_64",
        avx=not requires_avx2,
        avx2=requires_avx2,
        avx512=requires_avx512,
        ram_gb_min=estimated_runtime_ram,
        gpu="cuda" in artifact_path.name.lower(),
        quantization=quantization,
    )
