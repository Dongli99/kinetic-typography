"""The plan file: every creative decision about a video, as JSON a person or agent can edit.

`words` is the record of what was said and when. `sections` is the direction: groups of those
words, in order, written as text with markup. `look` and `defaults` say how they appear and move.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .build import build
from .effects import ALIGNS, EffectError, check_hints, resolve
from .model import Phrase, Word
from .scene import FAMILIES, GroupSpec, Look, Scene, WordSpec, fonts_for

PLAN_VERSION = 2
LEVELS = ("hero", "weight", "tone")
MARKS = (("**", "hero"), ("*", "weight"), ("_", "tone"))  # longest first
SIZE = re.compile(r"\^(\d+(?:\.\d+)?)$")
TRIM_CHARS = " ,.;:—-\"“”‘()[]…*_"

LOOK_DEFAULTS = {
    "width": 1080,
    "height": 1080,
    "fps": 30,
    "font": "Archivo Black",
    "upper": True,
    "align": "center",
    "size": 64,
    "line_gap": 0.28,
    "background": [17, 17, 17],
    "ink": [245, 245, 240],
    "emphasis": {
        "hero": {"size": 1.7, "color": [255, 210, 31]},
        "weight": {"size": 1.35, "color": [255, 210, 31]},
        "tone": {"color": [160, 160, 155]},
    },
}
TREATMENT = {"size": 1.0, "bold": False, "italic": False, "color": None}  # what a level may change
DEFAULT_SLOTS = {
    "place": "fit",
    "arrive": "pop",
    "retire": {"type": "fade", "after": 1, "dur": 0.08, "hold": 0.42},
    "camera": "still",
}
SLOT_NAMES = ("place", "arrive", "retire", "camera")
GROUP_FIELDS = ("text", "align", "at", "camera", "arrive", "retire")


class PlanError(ValueError):
    """A plan file that can't be rendered. The message names the field to fix."""


@dataclass
class Plan:
    audio: str
    duration: float
    words: list[Word]
    sections: list[dict]  # each {"groups": [{"text": ..., ...}]}
    look: dict = field(default_factory=dict)  # overrides of LOOK_DEFAULTS
    defaults: dict = field(default_factory=lambda: dict(DEFAULT_SLOTS))
    emphasis: dict = field(default_factory=lambda: {"source": "meaning"})

    def make_scene(self) -> Scene:
        look, treatments = _read_look(self.look)
        slots = _read_slots({**DEFAULT_SLOTS, **self.defaults})
        specs = _read_sections(self.sections, self.words, slots, look, treatments)
        return build(specs, slots, look, self.duration)


# ------------------------------------------------------------------ writing


def draft_plan(audio: str, duration: float, phrases: list[Phrase]) -> Plan:
    """A first draft: one section, a group per phrase, and the phrase's emphasis as weight."""
    words, groups = [], []
    for phrase in phrases:
        tokens = []
        for index, word in enumerate(phrase.words):
            words.append(word)
            shown = word.text.replace("’", "'").strip(TRIM_CHARS) or word.text
            tokens.append(f"*{shown}*" if index == phrase.emphasis else shown)
        groups.append({"text": " ".join(tokens)})
    return Plan(audio, duration, words, [{"groups": groups}])


def save_plan(plan: Plan, path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    audio = Path(plan.audio).resolve()
    try:
        audio_text = str(audio.relative_to(Path(path).resolve().parent))
    except ValueError:
        audio_text = str(audio)
    head = {
        "version": PLAN_VERSION,
        "audio": audio_text,
        "duration": round(plan.duration, 3),
        "emphasis": plan.emphasis,
        "look": plan.look,
        "defaults": plan.defaults,
    }
    # One word and one group per line keeps the file short to read and easy to edit.
    lines = [f" {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)}," for key, value in head.items()]
    lines.append(' "sections": [')
    sections = []
    for section in plan.sections:
        groups = ",\n".join(f"   {json.dumps(g, ensure_ascii=False)}" for g in section["groups"])
        sections.append(f'  {{"groups": [\n{groups}\n  ]}}')
    lines.append(",\n".join(sections))
    lines.append(" ],")
    lines.append(' "words": [')
    words = [
        json.dumps({"text": w.text, "start": round(w.start, 3), "end": round(w.end, 3)}, ensure_ascii=False)
        for w in plan.words
    ]
    lines.append(",\n".join(f"  {w}" for w in words))
    lines.append(" ]")
    Path(path).write_text("{\n" + "\n".join(lines) + "\n}\n", encoding="utf-8")


# ------------------------------------------------------------------ reading


def load_plan(path: str) -> Plan:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PlanError(f"{path} is not valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise PlanError("The plan must be a JSON object.")
    if data.get("version") == 1:
        raise PlanError(
            "version: this is a version 1 plan, and this tool reads version 2. "
            "Run `kinetic plan` again to write a new one, then redo any edits."
        )
    if data.get("version") != PLAN_VERSION:
        raise PlanError(f"version: expected {PLAN_VERSION}, got {data.get('version')!r}")
    _only(data, ("version", "audio", "duration", "emphasis", "look", "defaults", "sections", "words"), "")

    audio = data.get("audio")
    if not isinstance(audio, str) or not audio:
        raise PlanError("audio: expected a file path")
    duration = data.get("duration")
    if not _is_number(duration) or duration <= 0:
        raise PlanError(f"duration: expected a positive number of seconds, got {duration!r}")
    emphasis = data.get("emphasis", {"source": "meaning"})
    if not isinstance(emphasis, dict):
        raise PlanError("emphasis: expected an object")
    _only(emphasis, ("source",), "emphasis")
    if emphasis.get("source", "meaning") != "meaning":
        raise PlanError(
            f"emphasis.source: only \"meaning\" is available, got {emphasis['source']!r}. "
            "Reading emphasis from the voice isn't built yet."
        )
    for key in ("look", "defaults"):
        if not isinstance(data.get(key, {}), dict):
            raise PlanError(f"{key}: expected an object")
    sections = data.get("sections")
    if not isinstance(sections, list) or not sections:
        raise PlanError("sections: expected a non-empty list")
    raw_words = data.get("words")
    if not isinstance(raw_words, list) or not raw_words:
        raise PlanError("words: expected a non-empty list")
    words = [_read_word(raw, f"words[{index}]") for index, raw in enumerate(raw_words)]

    resolved = Path(audio) if Path(audio).is_absolute() else Path(path).resolve().parent / audio
    plan = Plan(str(resolved), float(duration), words, sections, data.get("look", {}), data.get("defaults", {}), emphasis)
    try:
        plan.make_scene()  # every mistake surfaces here, not halfway through a render
    except EffectError as error:
        raise PlanError(str(error)) from error
    return plan


def _read_word(raw: object, where: str) -> Word:
    if not isinstance(raw, dict) or not isinstance(raw.get("text"), str) or not raw["text"].strip():
        raise PlanError(f"{where}.text: expected non-empty text")
    _only(raw, ("text", "start", "end"), where)
    start, end = raw.get("start"), raw.get("end")
    if not _is_number(start) or not _is_number(end) or start < 0 or end < start:
        raise PlanError(f"{where}: expected 0 <= start <= end, got start={start!r} end={end!r}")
    return Word(raw["text"], float(start), float(end))


def _read_look(raw: dict) -> tuple[Look, dict]:
    _only(raw, tuple(LOOK_DEFAULTS), "look")
    values = {**LOOK_DEFAULTS, **raw}
    for key in ("width", "height", "fps"):
        if type(values[key]) is not int or values[key] < 1:
            raise PlanError(f"look.{key}: expected a whole number from 1, got {values[key]!r}")
    for key in ("size", "line_gap"):
        if not _is_number(values[key]) or values[key] < 0:
            raise PlanError(f"look.{key}: expected a number from 0, got {values[key]!r}")
    if values["font"] not in FAMILIES:
        raise PlanError(f"look.font: expected one of {', '.join(FAMILIES)}, got {values['font']!r}")
    if not isinstance(values["upper"], bool):
        raise PlanError(f"look.upper: expected true or false, got {values['upper']!r}")
    if values["align"] not in ALIGNS:
        raise PlanError(f"look.align: expected left, center or right, got {values['align']!r}")
    background, ink = _color(values["background"], "look.background"), _color(values["ink"], "look.ink")

    emphasis = values["emphasis"]
    if not isinstance(emphasis, dict):
        raise PlanError("look.emphasis: expected an object")
    _only(emphasis, LEVELS, "look.emphasis")
    fonts = fonts_for(values["font"])
    treatments = {}
    for level in LEVELS:
        where = f"look.emphasis.{level}"
        given = {**LOOK_DEFAULTS["emphasis"], **emphasis}[level]
        if not isinstance(given, dict):
            raise PlanError(f"{where}: expected an object")
        _only(given, tuple(TREATMENT), where)
        treatment = {**TREATMENT, **given}
        if not _is_number(treatment["size"]) or treatment["size"] <= 0:
            raise PlanError(f"{where}.size: expected a positive number, got {treatment['size']!r}")
        for key in ("bold", "italic"):
            if not isinstance(treatment[key], bool):
                raise PlanError(f"{where}.{key}: expected true or false, got {treatment[key]!r}")
            if treatment[key] and not fonts.has(**{key: True}):
                others = [name for name in FAMILIES if fonts_for(name).has(**{key: True})]
                raise PlanError(f"{where}.{key}: {values['font']} has no {key} style. Fonts that do: {', '.join(others)}")
        treatment["color"] = ink if treatment["color"] is None else _color(treatment["color"], f"{where}.color")
        if treatment == {**TREATMENT, "color": ink}:
            raise PlanError(f"{where}: this looks the same as unmarked text, so {level} words wouldn't stand out")
        treatments[level] = treatment
    treatments[None] = {**TREATMENT, "color": ink}
    look = Look(values["width"], values["height"], values["fps"], float(values["size"]), float(values["line_gap"]),
                background, values["font"])  # fmt: skip
    return look, {"upper": values["upper"], "align": values["align"], **treatments}


def _read_slots(raw: dict) -> dict:
    _only(raw, tuple(SLOT_NAMES), "defaults")
    for slot, spec in raw.items():
        resolve(slot, spec, f"defaults.{slot}")
    return raw


def _read_sections(sections: list, words: list[Word], slots: dict, look: Look, treatments: dict) -> list[GroupSpec]:
    place, camera = (_name(slots[slot]) for slot in ("place", "camera"))
    specs, cursor = [], 0
    for s_index, section in enumerate(sections):
        where = f"sections[{s_index}]"
        if not isinstance(section, dict) or not isinstance(section.get("groups"), list) or not section["groups"]:
            raise PlanError(f"{where}.groups: expected a non-empty list")
        _only(section, ("groups",), where)
        for g_index, group in enumerate(section["groups"]):
            at = f"{where}.groups[{g_index}]"
            if not isinstance(group, dict) or not isinstance(group.get("text"), str):
                raise PlanError(f"{at}.text: expected text")
            _only(group, GROUP_FIELDS, at)
            if group.get("align", "left") not in ALIGNS:
                raise PlanError(f"{at}.align: expected left, center or right, got {group['align']!r}")
            check_hints("place", place, group.get("at", {}), f"{at}.at")
            check_hints("camera", camera, group.get("camera", {}), f"{at}.camera")
            for slot in ("arrive", "retire"):
                if slot in group:
                    resolve(slot, group[slot], f"{at}.{slot}")
            marked, lines, cursor = _read_text(group["text"], words, cursor, f"{at}.text")
            shown = []
            for word, text, level, size in marked:
                treatment = treatments[level]
                text = text.upper() if treatments["upper"] else text
                shown.append(WordSpec(text, word.start, word.end, treatment["size"] * size, tuple(treatment["color"]),
                                      treatment["bold"], treatment["italic"], level))  # fmt: skip
            specs.append(
                GroupSpec(
                    tuple(shown), lines if len(lines) > 1 else None, group.get("align", treatments["align"]),
                    section=s_index > 0 and g_index == 0, at=group.get("at", {}), camera=group.get("camera", {}),
                    arrive=group.get("arrive"), retire=group.get("retire"),
                )
            )  # fmt: skip
    if cursor < len(words):
        rest = " ".join(w.text for w in words[cursor : cursor + 6])
        raise PlanError(f"sections: words[{cursor}] onward aren't in any group, from \"{rest}\"")
    return specs


def _read_text(text: str, words: list[Word], cursor: int, where: str):
    """Match a group's text to the next spoken words, reading its markup.

    Returns (word, shown text, level, size) for each spoken word, the words per line, and the new cursor.
    """
    marked, lines, count = [], [], 0
    pending: list[tuple[str, str | None, float | None]] = []  # pieces of the spoken word being matched
    level = None  # the mark currently open
    tokens = text.split()
    if not tokens:
        raise PlanError(f"{where}: expected at least one word")
    for token in tokens:
        if token == "/":
            if pending:
                raise PlanError(f"{where}: a line break splits the spoken word \"{words[cursor].text}\"")
            if count == 0:
                raise PlanError(f"{where}: a line break needs words on both sides")
            lines.append(count)
            count = 0
            continue
        body = token
        for mark, name in MARKS:
            if body.startswith(mark) and len(body) > len(mark):
                if level is not None:
                    raise PlanError(f"{where}: {token!r} opens {name} inside {level}. A word takes one level")
                level, body = name, body[len(mark) :]
                break
        size, body = _size(body, token, where)
        closed = False
        if level is not None:
            mark = dict((n, m) for m, n in MARKS)[level]
            if body.endswith(mark) and len(body) > len(mark):
                body, closed = body[: -len(mark)], True
        elif any(body.endswith(m) and len(body) > len(m) for m, _ in MARKS):
            raise PlanError(f"{where}: {token!r} closes a mark that was never opened")
        if size is None:
            size, body = _size(body, token, where)
        if "^" in body:
            raise PlanError(f"{where}: {token!r}: a ^ needs a size after it, like word^1.5")
        pending.append((body, level, size))
        if closed:
            level = None

        if cursor >= len(words):
            if _norm(body):
                raise PlanError(f"{where}: {body!r} comes after the last spoken word")
            continue  # trailing punctuation, which joins the last word below
        want = _norm(words[cursor].text)
        have = [piece for p in pending for piece in _norm(p[0])]
        if want == [] and have == []:  # a spoken word with no letters or digits, like "&"
            have, want = [" ".join(p[0] for p in pending).lower()], [words[cursor].text.lower()]
        if have == want:
            marked.append(_finish(pending, words[cursor], where))
            cursor, count, pending = cursor + 1, count + 1, []
        elif have != want[: len(have)]:
            spoken = words[cursor]
            raise PlanError(
                f"{where}: {' '.join(p[0] for p in pending)!r} doesn't match the next spoken word, "
                f"{spoken.text!r} (words[{cursor}] at {spoken.start:.2f}s)"
            )
    if level is not None:
        raise PlanError(f"{where}: a {level} mark is opened but never closed")
    if pending:
        if any(_norm(p[0]) for p in pending) or not marked:
            raise PlanError(f"{where}: the group ends partway through the spoken word {words[cursor].text!r}")
        word, shown, word_level, word_size = marked[-1]  # trailing punctuation joins the last word
        marked[-1] = (word, " ".join([shown] + [p[0] for p in pending]), word_level, word_size)
    if count == 0:
        raise PlanError(f"{where}: a line break needs words on both sides")
    return marked, tuple(lines + [count]), cursor


def _size(body: str, token: str, where: str) -> tuple[float | None, str]:
    match = SIZE.search(body)
    if not match:
        return None, body
    size = float(match.group(1))
    if size <= 0 or match.start() == 0:
        raise PlanError(f"{where}: {token!r} needs a positive size after a word, like word^1.5")
    return size, body[: match.start()]


def _finish(pending: list, word: Word, where: str) -> tuple[Word, str, str | None, float]:
    """One spoken word from its pieces, which must agree on their markup."""
    levels = {p[1] for p in pending if _norm(p[0])} or {pending[0][1]}
    if len(levels) > 1:
        raise PlanError(
            f"{where}: the markup covers only part of the spoken word {word.text!r}. Mark all of it or none of it"
        )
    sizes = {p[2] for p in pending if p[2] is not None}
    if len(sizes) > 1:
        raise PlanError(f"{where}: the spoken word {word.text!r} has more than one size")
    return word, " ".join(p[0] for p in pending), levels.pop(), sizes.pop() if sizes else 1.0


def _norm(text: str) -> list[str]:
    """What has to match between the shown text and the spoken word: letters and digits."""
    return re.sub(r"[^a-z0-9 ]", "", text.lower().replace("-", " ").replace("—", " ")).split()


def _name(spec: str | dict) -> str:
    return spec if isinstance(spec, str) else spec["type"]


def _only(raw: dict, known: tuple, where: str) -> None:
    for key in raw:
        if key not in known:
            prefix = f"{where}." if where else ""
            raise PlanError(f"{prefix}{key}: unknown field. Known: {', '.join(known)}")


def _color(value: object, where: str) -> tuple[int, int, int]:
    if not (isinstance(value, list) and len(value) == 3 and all(type(c) is int and 0 <= c <= 255 for c in value)):
        raise PlanError(f"{where}: expected [red, green, blue] from 0 to 255, got {value!r}")
    return tuple(value)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
