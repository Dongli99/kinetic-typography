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


def draft_plan(audio: str, duration: float, phrases: list[Phrase], size: tuple[int, int] | None = None) -> Plan:
    """A section per run of phrases, a group per phrase, its words' emphasis as markup, and where each group sits.

    size is the frame's width and height, when it isn't the preset's.
    """
    words, sections = [], []
    for phrase in phrases:
        words += phrase.words
        if phrase.section or not sections:
            sections.append({"groups": []})
        sections[-1]["groups"].append({"text": _text(phrase)})
    look = {"width": size[0], "height": size[1]} if size else {}
    plan = Plan(audio, duration, words, sections, look=look, defaults={}, preset=PRESET)
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
    """Give each group the first spot on its list where it lands on no word still showing and nothing is clipped,
    or failing that, the least faulty one. `kinetic check` reports whatever is left."""
    groups = [(s, g) for s, section in enumerate(plan.sections) for g in range(len(section["groups"]))]
    turned = 0  # the sign of the last turn, so turns alternate instead of spiralling into older words
    for index, (s, g) in enumerate(groups):
        if index == 0:
            continue
        group = plan.sections[s]["groups"][g]
        spots = _spots(g, turned, len(group["text"].split()) == 1)
        best = None
        for spot in spots:
            fault = _fault(plan, group, index, spot)
            if best is None or fault < best[0]:
                best = (fault, spot)
            if fault == 0:
                break
        group["at"] = best[1]
        turned = group["at"].get("turn", 0) or turned


def _fault(plan: Plan, group: dict, index: int, spot: dict) -> int:
    """How bad a spot is: 0 if clear, 1 if only the group before is clipped, 2 if this group is, 3 if it overlaps.

    The camera leaving for this group can clip the last words of the one before, and in quick speech no spot
    avoids it, so that counts least. Words landing on words always count most.
    """
    group["at"] = spot
    scene = plan.make_scene()
    if lands_on(scene, index):
        return 3
    if any(clipped(scene, word) for word in scene.groups[index].words):
        return 2
    return 1 if any(clipped(scene, word) for word in scene.groups[index - 1].words) else 0


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
              {"side": "below", "gap": 200.0}, {"side": "right", "gap": 400.0}, {"side": "below", "gap": 600.0},
              {"side": "above", "gap": 600.0}, {"side": "left", "gap": 800.0}, {"side": "right", "gap": 1200.0}]  # fmt: skip
    return preferred + [spot for spot in others if spot not in preferred]
