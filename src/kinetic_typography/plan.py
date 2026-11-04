"""The plan file: every creative decision about a video, as JSON a person or agent can edit."""

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .build import build
from .model import Phrase, Style, Word
from .scene import GroupSpec, Look, Scene, WordSpec

PLAN_VERSION = 1
TRIM_CHARS = " ,.;:—-\"“”‘()[]…"


class PlanError(ValueError):
    """A plan file that can't be rendered. The message names the field to fix."""


@dataclass(frozen=True)
class Plan:
    audio: str
    duration: float
    phrases: list[Phrase]
    style: dict = field(default_factory=dict)  # overrides of Style's defaults

    def make_style(self) -> Style:
        values = {key: tuple(value) if isinstance(value, list) else value for key, value in self.style.items()}
        return Style(**values)

    def make_scene(self) -> Scene:
        """One phrase at a time, centered and sized to fill the frame, with its emphasis in the accent."""
        style = self.make_style()
        look = Look(style.width, style.height, style.fps, line_gap=style.line_gap, background=style.background)
        groups = [
            GroupSpec(
                tuple(
                    WordSpec(display_text(word.text), word.start, word.end, style.emphasis_scale, style.accent)
                    if index == phrase.emphasis
                    else WordSpec(display_text(word.text), word.start, word.end, 1.0, style.foreground)
                    for index, word in enumerate(phrase.words)
                ),
                align="center",
            )
            for phrase in self.phrases
        ]
        slots = {
            "place": {"type": "fit", "margin": style.margin, "max_size": style.max_font_size},
            "arrive": {"type": "pop", "dur": style.pop_duration, "lead": style.lead_in},
            # Version 1's hold is when a phrase is gone; the effect's is when it starts leaving.
            "retire": {"type": "fade", "after": 1, "dur": style.fade_out, "hold": max(0.0, style.hold - style.fade_out)},
            "camera": "still",
        }
        return build(groups, slots, look, self.duration)


def display_text(token: str) -> str:
    return token.replace("’", "'").strip(TRIM_CHARS).upper()


def save_plan(plan: Plan, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    audio = Path(plan.audio).resolve()
    try:
        audio_text = str(audio.relative_to(Path(path).resolve().parent))
    except ValueError:
        audio_text = str(audio)
    data = {
        "version": PLAN_VERSION,
        "audio": audio_text,
        "duration": round(plan.duration, 3),
        "style": plan.style,
        "phrases": [
            {
                "emphasis": phrase.emphasis,
                "words": [
                    {"text": word.text, "start": round(word.start, 3), "end": round(word.end, 3)}
                    for word in phrase.words
                ],
            }
            for phrase in plan.phrases
        ],
    }
    Path(path).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def load_plan(path: str) -> Plan:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PlanError(f"{path} is not valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise PlanError("The plan must be a JSON object.")
    if data.get("version") != PLAN_VERSION:
        raise PlanError(f"version: expected {PLAN_VERSION}, got {data.get('version')!r}")

    audio = data.get("audio")
    if not isinstance(audio, str) or not audio:
        raise PlanError("audio: expected a file path")
    duration = data.get("duration")
    if not _is_number(duration) or duration <= 0:
        raise PlanError(f"duration: expected a positive number of seconds, got {duration!r}")

    style = data.get("style", {})
    if not isinstance(style, dict):
        raise PlanError("style: expected an object")
    known = {item.name for item in fields(Style)}
    for key in style:
        if key not in known:
            raise PlanError(f"style.{key}: unknown setting. Known settings: {', '.join(sorted(known))}")

    raw_phrases = data.get("phrases")
    if not isinstance(raw_phrases, list) or not raw_phrases:
        raise PlanError("phrases: expected a non-empty list")
    phrases = [_read_phrase(raw, f"phrases[{index}]") for index, raw in enumerate(raw_phrases)]

    resolved = Path(audio) if Path(audio).is_absolute() else Path(path).resolve().parent / audio
    plan = Plan(str(resolved), float(duration), phrases, style)
    try:
        plan.make_style()
    except (TypeError, ValueError) as error:
        raise PlanError(f"style: {error}") from error
    return plan


def _read_phrase(raw: object, where: str) -> Phrase:
    if not isinstance(raw, dict):
        raise PlanError(f"{where}: expected an object")
    raw_words = raw.get("words")
    if not isinstance(raw_words, list) or not raw_words:
        raise PlanError(f"{where}.words: expected a non-empty list")
    words = []
    for index, word in enumerate(raw_words):
        at = f"{where}.words[{index}]"
        if not isinstance(word, dict) or not isinstance(word.get("text"), str) or not word["text"].strip():
            raise PlanError(f"{at}.text: expected non-empty text")
        start, end = word.get("start"), word.get("end")
        if not _is_number(start) or not _is_number(end) or start < 0 or end < start:
            raise PlanError(f"{at}: expected 0 <= start <= end, got start={start!r} end={end!r}")
        words.append(Word(word["text"], float(start), float(end)))
    emphasis = raw.get("emphasis")
    if emphasis is not None and (type(emphasis) is not int or not 0 <= emphasis < len(words)):
        raise PlanError(f"{where}.emphasis: expected null or a word index below {len(words)}, got {emphasis!r}")
    return Phrase(tuple(words), emphasis)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def style_defaults() -> dict:
    return asdict(Style())
