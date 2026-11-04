"""Data passed between the pipeline stages: words -> phrases -> plan."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Word:
    """A script word and when it is spoken, in seconds."""

    text: str
    start: float
    end: float


@dataclass(frozen=True)
class Phrase:
    words: tuple[Word, ...]
    emphasis: int | None = None  # index into words


@dataclass(frozen=True)
class Style:
    width: int = 1080
    height: int = 1080
    fps: int = 30
    margin: float = 90.0
    max_font_size: float = 190.0
    emphasis_scale: float = 1.35
    line_gap: float = 0.28  # relative to font size
    background: tuple[int, int, int] = (17, 17, 17)
    foreground: tuple[int, int, int] = (245, 245, 240)
    accent: tuple[int, int, int] = (255, 210, 31)
    lead_in: float = 0.0  # seconds a word starts appearing before it is spoken
    pop_duration: float = 0.18
    fade_out: float = 0.08
    hold: float = 0.5  # seconds a phrase stays after its last word
