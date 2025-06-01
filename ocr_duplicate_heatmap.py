"""Generate heatmap image from OCR log data with bbox positions."""
import json
import os
from pathlib import Path

try:
    from PIL import Image  # type: ignore
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover - optional
    Image = None
    np = None

LOG = Path(os.getenv("OCR_RELAY_LOG", "logs/ocr_relay.jsonl"))


def generate_heatmap(out_path: Path, width: int = 1280, height: int = 720) -> bool:
    if Image is None or np is None:
        return False
    heat = np.zeros((height, width), dtype=float)
    if not LOG.exists():
        return False
    for line in LOG.read_text(encoding="utf-8").splitlines():
        try:
            data = json.loads(line)
        except Exception:
            continue
        bbox = data.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        x1, y1, x2, y2 = [int(v) for v in bbox]
        x1 = max(0, min(width - 1, x1))
        x2 = max(0, min(width - 1, x2))
        y1 = max(0, min(height - 1, y1))
        y2 = max(0, min(height - 1, y2))
        heat[y1:y2, x1:x2] += data.get("count", 1)
    if not heat.any():
        return False
    heat_img = (heat / heat.max() * 255).astype("uint8")
    img = Image.fromarray(heat_img, mode="L")
    img.save(out_path)
    return True


if __name__ == "__main__":  # pragma: no cover - manual
    generate_heatmap(Path("ocr_heatmap.png"))
