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
    """Words shown together, as a group of lines."""

    words: tuple[Word, ...]
    lines: tuple[int, ...] = ()  # words per line; () for one line
    levels: tuple[str | None, ...] = ()  # each word's emphasis: hero, weight, tone or None
    section: bool = False  # starts a new section
