"""The automatic first draft: phrases made into a plan with lines, placement and emphasis.

Placement is a rule plus a search. The rule says where each group would like to go, and the
overlap and clipping checks reject a spot, so the next one in the group's list is tried.
Everything it decides is written into the plan, where an agent can change it.
"""

from itertools import accumulate

from .check import clipped, lands_on
from .model import Phrase
from .plan import MARK, TRIM_CHARS, Plan

PRESET = "gap"
SECTION_GAP = 400.0  # pixels between sections, so the camera travels
TURN = 90.0


def draft_plan(audio: str, duration: float, phrases: list[Phrase]) -> Plan:
    """A section per run of phrases, a group per phrase, its words' emphasis as markup, and where each group sits."""
    words, sections = [], []
    for phrase in phrases:
        words += phrase.words
        if phrase.section or not sections:
            sections.append({"groups": []})
        sections[-1]["groups"].append({"text": _text(phrase)})
    plan = Plan(audio, duration, words, sections, defaults={}, preset=PRESET)
    _place(plan)
    return plan


def _text(phrase: Phrase) -> str:
    """The phrase as markup: each word with its level's mark, and a / between lines."""
    tokens = []
    for word, level in zip(phrase.words, phrase.levels or [None] * len(phrase.words)):
        shown = word.text.replace("’", "'").strip(TRIM_CHARS) or word.text
        tokens.append(f"{MARK[level]}{shown}{MARK[level]}" if level else shown)
    for end in reversed(list(accumulate(phrase.lines))[:-1]):
        tokens.insert(end, "/")
    return " ".join(tokens)


def _place(plan: Plan) -> None:
    """Give each group the first spot on its list where it lands on no word still showing and isn't clipped."""
    groups = [(s, g) for s, section in enumerate(plan.sections) for g in range(len(section["groups"]))]
    turned = 0  # the sign of the last turn, so turns alternate instead of spiralling into older words
    for index, (s, g) in enumerate(groups):
        if index == 0:
            continue
        group = plan.sections[s]["groups"][g]
        spots = _spots(g, turned, len(group["text"].split()) == 1)
        for spot in spots:
            group["at"] = spot
            scene = plan.make_scene()
            if not lands_on(scene, index) and not any(clipped(scene, word) for word in scene.groups[index].words):
                break
        else:
            group["at"] = spots[0]  # nowhere is clear: `kinetic check` will report it
        turned = group["at"].get("turn", 0) or turned


def _spots(g: int, turned: float, single: bool) -> list[dict]:
    """Where a group would like to go, best first: the rule's choice, then the alternatives."""
    turn = -TURN if turned > 0 else TURN
    if g == 0:  # a new section: travel, and turn the page
        return [{"side": side, "gap": SECTION_GAP * k, "turn": t} for k in (1, 2) for side in ("below", "right")
                for t in (turn, -turn)]  # fmt: skip
    beside = {"side": "right"}  # a single word continues the line
    below = {"side": "below"}
    across = {"side": "right", "turn": turn}
    if single:
        preferred = [beside, below]
    elif g % 3 == 2:
        preferred = [across, below]
    else:
        preferred = [below, across]
    others = [{"side": "below", "align": "right"}, {"side": "right", "turn": -turn}, {"side": "left", "turn": turn},
              {"side": "below", "gap": 200.0}, {"side": "right", "gap": 400.0}, {"side": "below", "gap": 600.0}]  # fmt: skip
    return preferred + [spot for spot in others if spot not in preferred]
