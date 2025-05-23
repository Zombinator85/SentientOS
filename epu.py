EPU_EMOTIONS = [
    "joy", "love", "awe", "gratitude", "admiration", "contentment", "affection", "elation",
    "relief", "serenity", "ecstasy", "limerence", "bliss", "playfulness", "amusement", "pride",
    "longing", "nostalgia", "saudade", "hiraeth", "sehnsucht", "desire", "lust", "hope", "anticipation",
    "fascination", "curiosity", "ambition", "motivation", "veneration", "trust", "connectedness",
    "compassion", "empathy", "sympathy", "nurturing", "tenderness", "reassurance", "forgiveness", "devotion",
    "vulnerability", "generosity", "acceptance", "humility", "support", "resilience", "sincerity", "protectiveness",
    "sadness", "sorrow", "grief", "melancholy", "ennui", "loneliness", "regret", "remorse", "guilt", "shame", "embarrassment",
    "fear", "anxiety", "dread", "apprehension", "nervousness"
]

class EPU:
    """Minimal emotion processing unit."""

    def __init__(self):
        self.last_audio = None
        self.last_video = None
        self.last_text = None
        self.fused = {"label": "neutral", "score": 1.0}

    def update_audio(self, label: str, score: float) -> None:
        self.last_audio = {"label": label, "score": float(score)}
        self._fuse()

    def update_video(self, label: str, score: float) -> None:
        self.last_video = {"label": label, "score": float(score)}
        self._fuse()

    def update_text(self, label: str, score: float) -> None:
        self.last_text = {"label": label, "score": float(score)}
        self._fuse()

    def _fuse(self) -> None:
        scores = []
        labels = []
        for src in [self.last_audio, self.last_video, self.last_text]:
            if src:
                scores.append(src["score"])
                labels.append(src["label"])
        if scores:
            best = labels[scores.index(max(scores))]
            self.fused = {"label": best, "score": max(scores)}
        else:
            self.fused = {"label": "neutral", "score": 1.0}

    def get_epu_state(self):
        return {
            "audio_emotion": self.last_audio,
            "video_emotion": self.last_video,
            "text_emotion": self.last_text,
            "epu_fused": self.fused,
        }
