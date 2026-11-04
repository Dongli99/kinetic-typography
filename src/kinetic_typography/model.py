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
