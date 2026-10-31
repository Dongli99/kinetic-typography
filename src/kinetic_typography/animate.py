"""Work out how each word and the camera look at a moment in time."""

from dataclasses import dataclass

from .model import Camera, PlacedWord, Scene, Style

POP_FROM_SCALE = 0.82
RISE_DISTANCE = 0.14  # relative to font size


@dataclass(frozen=True)
class WordState:
    opacity: float
    scale: float
    y_offset: float


def word_state(word: PlacedWord, scene: Scene, t: float, style: Style) -> WordState | None:
    """Return the word's appearance at time t, or None if it isn't visible yet."""
    appear_at = max(scene.start, word.start - style.lead_in)
    if t < appear_at or t >= scene.end:
        return None

    progress = min(1.0, (t - appear_at) / style.pop_duration)
    fade_out = min(1.0, (scene.end - t) / style.fade_out)
    return WordState(
        opacity=min(1.0, progress * 2) * fade_out,
        scale=POP_FROM_SCALE + (1 - POP_FROM_SCALE) * _ease_out_back(progress),
        y_offset=(1 - _ease_out_cubic(progress)) * RISE_DISTANCE * word.size,
    )


def camera_at(t: float) -> Camera:
    return Camera()


def _ease_out_cubic(p: float) -> float:
    return 1 - (1 - p) ** 3


def _ease_out_back(p: float) -> float:
    overshoot = 1.70158
    return 1 + (overshoot + 1) * (p - 1) ** 3 + overshoot * (p - 1) ** 2
