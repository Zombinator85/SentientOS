from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from .storage import ensure_mounts, get_data_root

LOGGER = logging.getLogger(__name__)

_MODEL_ENV = "SENTIENTOS_MODEL_PATH"
_MODEL_META_NAME = "model.json"


@dataclass
class LocalModel:
    """Simple wrapper around a locally hosted language model.

    The implementation is intentionally lightweight so it can run on systems
    without GPU acceleration. It can be swapped for a fully-fledged model by
    updating the ``generate`` method or by replacing the contents of the model
    directory referenced by ``SENTIENTOS_MODEL_PATH``.
    """

    model_dir: Path
    metadata: dict

    @classmethod
    def autoload(cls) -> "LocalModel":
        """Locate and load the configured local model.

        If no explicit model directory has been configured, an empty
        placeholder directory inside the SentientOS data root is created. The
        placeholder allows the rest of the platform to run in environments
        where a quantised model has not yet been provisioned.
        """

        ensure_mounts()
        candidate = os.environ.get(_MODEL_ENV)
        model_dir = Path(candidate) if candidate else get_data_root() / "models"
        model_dir.mkdir(parents=True, exist_ok=True)
        meta_path = model_dir / _MODEL_META_NAME
        metadata: dict
        if meta_path.exists():
            try:
                metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                LOGGER.warning("Failed to load model metadata: %s", exc)
                metadata = {}
        else:
            metadata = {}
            try:
                meta_path.write_text(json.dumps({"name": "placeholder"}), encoding="utf-8")
            except OSError:
                LOGGER.debug("Unable to write placeholder metadata for model directory", exc_info=True)
        LOGGER.info("Loaded local model from %s", model_dir)
        return cls(model_dir=model_dir, metadata=metadata)

    def generate(self, prompt: str, *, temperature: float = 0.7) -> str:
        """Produce a response to ``prompt`` using a deterministic heuristic.

        This keeps the system functional on development machines while a real
        model is being provisioned. It can be replaced by integrating a local
        inference server or a quantised transformer model that fits within the
        available VRAM.
        """

        prompt = prompt.strip()
        if not prompt:
            return "I am listening. What would you like to discuss?"
        summary = self.metadata.get("name", "SentientOS Local Model")
        return (
            f"[{summary}] I received your message: '{prompt}'. "
            "This placeholder model is ready to be swapped for a fully local LLM."
        )

    def describe(self) -> str:
        """Return a human readable summary of the loaded model."""

        name = self.metadata.get("name")
        if name:
            return f"Local model '{name}'"
        return "Local model placeholder"
