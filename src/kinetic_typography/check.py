"""Find what a person would see is wrong with a scene, and report the styles it applied.

Every finding names the group to fix, so an agent can act on it without looking at a frame.
"""

from .scene import Scene, Word, quads_overlap

MIN_READ = 0.3  # seconds a word must stay readable
SETTLE = 0.25  # seconds after a word starts, when it must be fully in frame
SHOWN = 0.5  # opacity from which a word counts as readable
SHOWING = 0.05  # opacity from which a word counts as in the way


def check(scene: Scene, names: list[str]) -> dict:
    """Overlaps, words clipped by the frame edge, words shown too briefly, and the styles applied.

    names gives each group's place in the plan, like "sections[0].groups[3]".
    """
    where = {id(word): name for group, name in zip(scene.groups, names) for word in group.words}
    found = {"overlaps": _overlaps(scene, where), "clipped": [], "brief": []}
    for group in scene.groups:
        for word in group.words:
            clipped_by = clipped(scene, word)
            if clipped_by:
                found["clipped"].append({**_about(word, where), **clipped_by})
            shown = _shown_for(scene, word)
            if shown < MIN_READ:
                found["brief"].append({**_about(word, where), "shown": round(shown, 2)})
    words = [word for group in scene.groups for word in group.words]
    styled = [w for w in words if w.spec.level or w.spec.size != 1]
    return {
        "clean": not any(found.values()),
        **found,
        "styles": {
            "words": len(words),
            **{level: sum(w.spec.level == level for w in words) for level in ("hero", "weight", "tone")},
            "styled": [
                {**_about(w, where), "level": w.spec.level, "size": round(w.spec.size, 3), "bold": w.spec.bold,
                 "italic": w.spec.italic, "color": list(w.spec.color)}  # fmt: skip
                for w in styled
            ],
        },
    }


def _about(word: Word, where: dict) -> dict:
    return {"group": where[id(word)], "word": word.text, "at": round(word.start, 2)}


def _overlaps(scene: Scene, where: dict) -> list[dict]:
    """Words that land, where they rest, on a word of another group still showing. One per pair of groups."""
    found = []
    for index in range(len(scene.groups)):
        for word, other in lands_on(scene, index):
            found.append({**_about(word, where), "lands_on": where[id(other)], "on_word": other.text})
    return found


def lands_on(scene: Scene, index: int) -> list[tuple[Word, Word]]:
    """For each older group that a word of group `index` lands on, the first such pair of words."""
    found = []
    words = scene.groups[index].words
    for older in scene.groups[:index]:
        pairs = ((word, other) for word in words for other in older.words if other.opacity(word.start) > SHOWING)
        pair = next(((word, other) for word, other in pairs if quads_overlap(word.corners(None), other.corners(word.start))), None)
        if pair:
            found.append(pair)
    return found


def clipped(scene: Scene, word: Word) -> dict | None:
    """How far the word reaches past the frame edge just after it lands, if it does."""
    t = word.start + SETTLE
    xs, ys = zip(*scene.on_screen(word, t))
    past = {"left": -min(xs), "right": max(xs) - scene.look.width, "top": -min(ys), "bottom": max(ys) - scene.look.height}
    edge = max(past, key=past.get)
    return {"edge": edge, "by": round(past[edge])} if past[edge] > 0.5 else None


def _shown_for(scene: Scene, word: Word) -> float:
    """How long the word stays readable, counted up to MIN_READ, frame by frame."""
    step = 1 / scene.look.fps
    t = max(0.0, word.start - 0.5)
    while t < scene.duration and word.opacity(t) <= SHOWN:  # find when it shows
        if t > word.end + 0.5:
            return 0.0
        t += step
    first = t
    while t < scene.duration and t - first < MIN_READ and word.opacity(t) > SHOWN:
        t += step
    return min(t, scene.duration) - first
