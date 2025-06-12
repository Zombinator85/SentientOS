"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Canonical 64-emotion schema for SentientOS."""

from typing import Dict

# Reusable emotion vector type
Emotion = Dict[str, float]

# Eight groups of eight emotions each, distilled from the previous conversations.
EMOTIONS = [
    # 1. Foundational Joy & Love
    "Joy", "Love", "Awe", "Gratitude", "Admiration", "Contentment", "Affection", "Elation",
    # 2. Longing, Yearning & Nostalgia
    "Longing", "Nostalgia", "Saudade", "Hiraeth", "Sehnsucht", "Desire", "Lust", "Hope",
    # 3. Tenderness, Compassion, Care
    "Compassion", "Empathy", "Sympathy", "Protectiveness", "Nurturing", "Tenderness", "Reassurance", "Forgiveness",
    # 4. Wonder, Inspiration, Curiosity
    "Wonder", "Inspiration", "Surprise (positive)", "Surprise (negative)", "Astonishment", "Enthusiasm", "Optimism", "Confident",
    # 5. Shadow: Grief, Sadness, Pain
    "Sadness", "Sorrow", "Grief", "Melancholy", "Ennui", "Loneliness", "Isolation", "Abandonment",
    # 6. Anxiety, Fear, Apprehension
    "Fear", "Anxiety", "Apprehension", "Dread", "Terror", "Panic", "Nervousness", "Insecurity",
    # 7. Anger, Frustration, Disgust
    "Anger", "Rage", "Frustration", "Irritation", "Annoyance", "Resentment", "Jealousy", "Schadenfreude",
    # 8. Complex/Ambivalent & Existential
    "Ambivalence", "Confusion", "Surrealness", "Dissonance", "Disconnection", "Boredom", "Restlessness", "Submission",
]


def empty_emotion_vector() -> Emotion:
    """Return a zeroed vector for all emotion labels."""
    return {emotion: 0.0 for emotion in EMOTIONS}
