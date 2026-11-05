"""Effects for the four slots, in one registry.

An effect is a named function that writes keys onto the scene. Its parameters, defaults and
docstring are its documentation, and `resolve` validates a choice against them.

    place(ctx, groups, **params)          where every group rests
    arrive(ctx, word, **params)           how a word comes in
    retire(ctx, group, **params)          how a group leaves
    camera(ctx, camera, groups, **params) where the view goes
"""

import inspect
import json
from itertools import combinations

from .scene import Camera, Group, Word, rotate

SLOTS = {"place": 2, "arrive": 2, "retire": 2, "camera": 3}  # arguments before the parameters
EFFECTS: dict[str, dict] = {slot: {} for slot in SLOTS}
HINTS: dict[str, dict] = {slot: {} for slot in SLOTS}  # what each group may tell the effect
SLOT_DOCS = {
    "place": "Where every group rests. One choice for the whole video.",
    "arrive": "How each word comes in.",
    "retire": (
        "How each group leaves. It starts leaving `after` groups later, at the next section, or `hold` seconds "
        "after its last word, whichever is first. With none of these, it stays to the end."
    ),
    "camera": "Where the view goes. One choice for the whole video.",
}


class EffectError(ValueError):
    """A choice of effect that can't be used. The message names what to fix."""


def effect(slot: str, name: str, hints: dict | None = None):
    """Register an effect. Hints map each per-group hint to its default, or to a tuple of choices."""

    def register(fn):
        EFFECTS[slot][name] = fn
        HINTS[slot][name] = hints or {}
        return fn

    return register


def parameters(slot: str, name: str) -> dict:
    """An effect's parameters and their defaults."""
    params = list(inspect.signature(EFFECTS[slot][name]).parameters.values())[SLOTS[slot] :]
    return {p.name: p.default for p in params}


def resolve(slot: str, spec: str | dict, where: str = "") -> tuple:
    """'name' or {'type': name, ...params} -> (function, params), or an error naming the fix."""
    where = where or slot
    if isinstance(spec, str):
        name, params = spec, {}
    elif isinstance(spec, dict) and isinstance(spec.get("type"), str):
        params = dict(spec)
        name = params.pop("type")
    else:
        raise EffectError(f"{where}: expected an effect name or {{\"type\": name, ...}}, got {spec!r}")
    if name not in EFFECTS[slot]:
        raise EffectError(f"{where}: unknown {slot} effect {name!r}. Known: {', '.join(sorted(EFFECTS[slot]))}")
    _check(params, parameters(slot, name), f"{name} has no such parameter", where)
    return EFFECTS[slot][name], params


def check_hints(slot: str, name: str, hints: dict, where: str) -> None:
    """Hints a group gives the chosen effect, or an error naming the fix."""
    if not isinstance(hints, dict):
        raise EffectError(f"{where}: expected an object, got {hints!r}")
    if hints and not HINTS[slot][name]:
        raise EffectError(f"{where}: the {slot} effect {name} takes no hints, so these would do nothing")
    _check(hints, HINTS[slot][name], f"{name} takes no such hint", where)


def _check(values: dict, known: dict, unknown: str, where: str) -> None:
    for key, value in values.items():
        if key not in known:
            raise EffectError(f"{where}.{key}: {unknown}. Known: {', '.join(known) or 'none'}")
        default = known[key]
        number = isinstance(value, (int, float)) and not isinstance(value, bool)
        if isinstance(default, tuple) and value not in default:
            raise EffectError(f"{where}.{key}: expected one of {', '.join(default)}, got {value!r}")
        if isinstance(default, bool) and not isinstance(value, bool):
            raise EffectError(f"{where}.{key}: expected true or false, got {value!r}")
        if type(default) is int and (type(value) is not int or value < 1):
            raise EffectError(f"{where}.{key}: expected a whole number from 1, got {value!r}")
        if type(default) is float and not number:
            raise EffectError(f"{where}.{key}: expected a number, got {value!r}")
        if default is None and value is not None and not number:
            raise EffectError(f"{where}.{key}: expected a number or null, got {value!r}")


def describe() -> str:
    """The effect reference, in Markdown, from each effect's docstring, parameters and hints."""
    out = [
        "## Effects",
        "",
        "Generated from the tool itself, so it's always complete. Defaults are in brackets, and for a choice "
        "the first is the default.",
        "",
    ]
    for slot in SLOTS:
        out += [f"### {slot}", "", SLOT_DOCS[slot], ""]
        for name, fn in sorted(EFFECTS[slot].items()):
            doc = " ".join(inspect.getdoc(fn).split())
            params = ", ".join(f"`{key}` {_show(value)}" for key, value in parameters(slot, name).items())
            out.append(f"- **`{name}`**: {doc}")
            if params:
                out.append(f"  Parameters: {params}.")
            hints = HINTS[slot][name]
            if hints:
                field = "at" if slot == "place" else slot
                shown = ", ".join(f"`{key}` {_show(value)}" for key, value in hints.items())
                out.append(f"  Hints in a group's `{field}`: {shown}.")
        out.append("")
    return "\n".join(out)


def _show(default) -> str:
    if isinstance(default, tuple):
        return "(" + " or ".join(default) + ")"
    return f"({json.dumps(default)})"


# ------------------------------------------------------------------- place


@effect("place", "fit")
def place_fit(ctx, groups: list[Group], margin=90.0, max_size=190.0):
    """One group at a time in the middle, sized to fill the frame. It breaks lines itself unless they're given."""
    width, height = ctx.size[0] - 2 * margin, ctx.size[1] - 2 * margin
    for g in groups:
        best = None
        for lines in [g.spec.lines] if g.spec.lines else _partitions(len(g.words)):
            w, h = g.line_box(lines)
            size = min(max_size, width / w, height / h)
            score = size * (1 - 0.07 * (len(lines) - 1))  # prefer fewer lines
            if best is None or score > best[0]:
                best = (score, lines, size)
        g.set_lines(best[1], best[2])
        g.base.update(x=0.0, y=0.0, rot=0.0, scale=1.0)


def _partitions(count: int):
    """Every split of count words into consecutive lines, as line lengths."""
    for line_count in range(1, count + 1):
        for cuts in combinations(range(1, count), line_count - 1):
            edges = (0, *cuts, count)
            yield tuple(edges[i + 1] - edges[i] for i in range(line_count))


SIDES = ("below", "above", "right", "left")
ALIGNS = ("left", "center", "right")


@effect("place", "canvas", hints={"side": SIDES, "turn": 0.0, "gap": 0.0, "align": ALIGNS, "dx": 0.0, "dy": 0.0, "scale": 1.0})
def place_canvas(ctx, groups: list[Group], gap=36.0):
    """Each group attaches to a side of the one before, optionally turned and scaled.

    Its `at` hints are in the previous group's frame: side, turn in degrees, gap in pixels,
    align (of its edge with the previous group's), dx and dy offsets in pixels, and scale.
    """
    prev = None
    for g in groups:
        at = g.spec.at
        s = at.get("scale", 1.0)
        g.base["scale"] = s
        if prev is None:
            g.base.update(x=0.0, y=0.0, rot=float(at.get("turn", 0)))
            prev = g
            continue
        ps = prev.base["scale"]
        pw, ph = prev.w * ps, prev.h * ps
        side, space, align, turn = at.get("side", "below"), at.get("gap", gap), at.get("align", "left"), at.get("turn", 0)
        # The group's footprint in the previous group's frame, after its turn.
        points = [rotate(sx * g.w * s / 2, sy * g.h * s / 2, turn) for sx in (-1, 1) for sy in (-1, 1)]
        left, top = min(p[0] for p in points), min(p[1] for p in points)
        bw, bh = max(p[0] for p in points) - left, max(p[1] for p in points) - top
        # Where the footprint's top-left corner goes.
        if side in ("below", "above"):
            ax = {"left": -pw / 2, "center": -bw / 2, "right": pw / 2 - bw}[align]
            ay = ph / 2 + space if side == "below" else -ph / 2 - space - bh
        elif side in ("right", "left"):
            ax = pw / 2 + space if side == "right" else -pw / 2 - space - bw
            # Level neighbours share a baseline; turned ones hang from the top.
            level = turn % 360 == 0
            ay = -ph / 2 + (prev.last_baseline * ps - g.first_baseline * s if level else 0)
        else:
            raise EffectError(f"at.side: expected one of {', '.join(SIDES)}, got {side!r}")
        wx, wy = rotate(ax - left + at.get("dx", 0), ay - top + at.get("dy", 0), prev.base["rot"])
        g.base.update(x=prev.base["x"] + wx, y=prev.base["y"] + wy, rot=prev.base["rot"] + turn)
        prev = g


# ------------------------------------------------------------------ arrive


@effect("arrive", "pop")
def arrive_pop(ctx, w: Word, dur=0.18, start_scale=0.82, rise=0.14, lead=0.0):
    """Grow into place from a little smaller and lower, overshooting slightly. Rise is relative to text size."""
    t0 = w.start - lead
    w.key("opacity", t0, 0.0)
    w.key("opacity", t0 + dur / 2, 1.0, "linear")
    w.key("scale", t0, start_scale)
    w.key("scale", t0 + dur, w.base["scale"], "back")
    w.key("y", t0, w.base["y"] + rise * w.font.getSize())
    w.key("y", t0 + dur, w.base["y"], "out")


@effect("arrive", "blur-in")
def arrive_blur_in(ctx, w: Word, dur=0.22, blur=9.0, slide=22.0, lead=0.06):
    """Slide in from the right, coming into focus."""
    t0 = w.start - lead
    w.key("opacity", t0, 0.0)
    w.key("opacity", t0 + dur, 1.0, "out")
    w.key("blur", t0, blur)
    w.key("blur", t0 + dur, 0.0, "out")
    w.key("x", t0, w.base["x"] + slide)
    w.key("x", t0 + dur, w.base["x"], "out")


@effect("arrive", "fade")
def arrive_fade(ctx, w: Word, dur=0.3, lead=0.05):
    """Fade in where it rests."""
    w.key("opacity", w.start - lead, 0.0)
    w.key("opacity", w.start - lead + dur, 1.0, "out")


# ------------------------------------------------------------------ retire
# Each starts leaving `after` groups later, at the next section, or `hold` seconds after its last word.


@effect("retire", "fade")
def retire_fade(ctx, g: Group, after=2, dur=0.6, hold=None):
    """Fade out where it rests."""
    t = ctx.retire_time(g, after, hold)
    if t is None:
        return
    g.key("opacity", t, 1.0)
    g.key("opacity", t + dur, 0.0, "linear")


@effect("retire", "rotate-shrink")
def retire_rotate_shrink(ctx, g: Group, after=2, angle=-14.0, shrink=0.55, dur=1.0, hold=None):
    """Turn and shrink away while fading."""
    t = ctx.retire_time(g, after, hold)
    if t is None:
        return
    r, s = g.base["rot"], g.base["scale"]
    g.key("rot", t, r)
    g.key("rot", t + dur, r + angle, "in")
    g.key("scale", t, s)
    g.key("scale", t + dur, s * shrink, "in")
    g.key("opacity", t, 1.0)
    g.key("opacity", t + dur, 0.0, "in")


@effect("retire", "fly-left")
def retire_fly_left(ctx, g: Group, after=2, distance=1600.0, dur=0.7, hold=None):
    """Fly off along its own lines, to the left."""
    t = ctx.retire_time(g, after, hold)
    if t is None:
        return
    dx, dy = rotate(-distance, 0, g.base["rot"])
    for prop, delta in (("x", dx), ("y", dy)):
        g.key(prop, t, g.base[prop])
        g.key(prop, t + dur, g.base[prop] + delta, "in")
    g.key("opacity", t + dur * 0.5, 1.0)
    g.key("opacity", t + dur, 0.0, "linear")


@effect("retire", "drop")
def retire_drop(ctx, g: Group, after=2, fall=900.0, spin=35.0, dur=0.9, hold=None):
    """Fall out of the page, turning as it goes."""
    t = ctx.retire_time(g, after, hold)
    if t is None:
        return
    dx, dy = rotate(0, fall, g.base["rot"])  # down on screen while the camera is level with it
    for prop, delta in (("x", dx), ("y", dy), ("rot", spin)):
        g.key(prop, t, g.base[prop])
        g.key(prop, t + dur, g.base[prop] + delta, "in")
    g.key("opacity", t + dur * 0.6, 1.0)
    g.key("opacity", t + dur, 0.0, "linear")


# ------------------------------------------------------------------ camera


@effect("camera", "still")
def camera_still(ctx, cam: Camera, groups: list[Group]):
    """Stay centered on the origin at actual size."""


@effect("camera", "follow", hints={"with": 1, "zoom": 1.0, "tilt": 0.0, "cut": False})
def camera_follow(ctx, cam: Camera, groups: list[Group], fill=0.6, max_zoom=1.7, travel=0.6, drift=0.05, linger=0.25):
    """Frame each group as it starts, turned so its lines read level. It stays on a group until `linger` seconds
    after its last word starts, then travels for up to `travel` seconds, faster when the next group comes soon.

    Its `camera` hints: with (how many groups, counting back from this one, to frame together),
    zoom (relative to the framing), tilt in degrees, and cut (jump instead of travelling).
    """
    width, height = ctx.size
    prev, last_word = None, 0.0
    for i, g in enumerate(groups):
        hint = g.spec.camera
        framed = groups[max(0, i - hint.get("with", 1) + 1) : i + 1]
        theta = g.base["rot"] + hint.get("tilt", 0)
        # Bounding box of the framed groups, in a frame turned by theta.
        points = [rotate(x, y, -theta) for f in framed for x, y in f.corners()]
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        cx, cy = rotate((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, theta)
        bw, bh = max(xs) - min(xs), max(ys) - min(ys)
        zoom = min(width * fill / bw, height * fill * 1.2 / bh, max_zoom) * hint.get("zoom", 1.0)
        if prev is not None:  # turn the short way round
            theta += 360 * round((prev[2] - theta) / 360)
        target = (cx, cy, theta, zoom)
        arrive = g.start + 0.05
        if prev is None:
            for prop, value in zip(("x", "y", "rot", "zoom"), target):
                cam.key(prop, 0.0, value * 0.92 if prop == "zoom" else value)
                cam.key(prop, arrive, value, "out")
        else:
            cut = hint.get("cut", False)
            leave = arrive - 0.001 if cut else min(max(arrive - travel, last_word + linger), arrive - 0.05)
            held = (*prev[:3], prev[3] * (1 + drift))  # zoom in slowly while holding
            for prop, a, b in zip(("x", "y", "rot", "zoom"), held, target):
                cam.key(prop, leave, a, "linear")
                cam.key(prop, arrive, b, "hold" if cut else "inout")
        prev, last_word = target, g.words[-1].start
    for prop, value in zip(("x", "y", "rot", "zoom"), prev):
        cam.key(prop, ctx.duration, value * (1 + drift) if prop == "zoom" else value, "linear")
