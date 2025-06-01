"""Generate tag cloud image from last week's reflections."""
import datetime
import os
from pathlib import Path

try:
    from wordcloud import WordCloud  # type: ignore
except Exception:  # pragma: no cover - optional
    WordCloud = None

LOG_DIR = Path(os.getenv("REFLECTION_LOG_DIR", "logs/self_reflections"))


def generate_cloud(out_path: Path) -> bool:
    if WordCloud is None:
        return False
    cutoff = datetime.date.today() - datetime.timedelta(days=7)
    texts = []
    for fp in LOG_DIR.glob("*.log"):
        try:
            day = datetime.date.fromisoformat(fp.stem)
        except Exception:
            continue
        if day < cutoff:
            continue
        texts.extend(fp.read_text(encoding="utf-8").splitlines())
    if not texts:
        return False
    wc = WordCloud(width=800, height=400, background_color="white")
    wc.generate(" ".join(texts))
    wc.to_file(out_path)
    return True


if __name__ == "__main__":  # pragma: no cover - manual
    path = Path("tag_cloud.png")
    if generate_cloud(path):
        print(path)
