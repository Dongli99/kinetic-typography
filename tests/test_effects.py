"""The scene and the effect registry. Tests marked shared run on every registered effect."""

import inspect
import math

import numpy as np
import pytest

from kinetic_typography.build import build
from kinetic_typography.effects import EFFECTS, SLOTS, EffectError, resolve
from kinetic_typography.scene import GroupSpec, Look, Node, WordSpec, quads_overlap

LOOK = Look(1920, 1080)
BASIC = {"place": "fit", "arrive": "fade", "retire": {"type": "fade", "after": 1, "dur": 0.1}, "camera": "still"}
CANVAS = {"place": "canvas", "arrive": "blur-in", "retire": "rotate-shrink", "camera": "follow"}
HINTS = [{}, {"side": "right"}, {"side": "below", "turn": -90}, {}, {"side": "left", "turn": 12}, {"side": "below"}]


def groups(texts=("Words stay", "in one world", "while a camera", "travels", "through it", "and old words leave"),
           hints=HINTS):  # fmt: skip
    """Groups of 0.3s words with 0.5s pauses between them. The fourth starts a section."""
    specs, t = [], 0.5
    for index, text in enumerate(texts):
        words = []
        for token in text.split():
            words.append(WordSpec(token, t, t + 0.3))
            t += 0.3
        specs.append(GroupSpec(tuple(words), section=index == 3, at=hints[index % len(hints)]))
        t += 0.5
    return specs, t + 3.0


def scene_with(slot, name, base=BASIC):
    specs, duration = groups()
    return build(specs, {**base, slot: name}, LOOK, duration)


def every(slot):
    return pytest.mark.parametrize("name", sorted(EFFECTS[slot]))


def at_rest(node, t):
    return all(node.get(prop, t) == pytest.approx(value, abs=1e-6) for prop, value in node.base.items())


# The tree


def test_a_property_eases_between_keys_and_holds_outside_them():
    node = Node(x=5.0)
    assert node.get("x", 3.0) == 5.0
    node.key("x", 1.0, 0.0)
    node.key("x", 2.0, 10.0, "linear")
    assert [node.get("x", t) for t in (0.0, 1.5, 9.0)] == [0.0, 5.0, 10.0]


def test_a_hold_jumps_at_its_key():
    node = Node()
    node.key("x", 1.0, 0.0)
    node.key("x", 2.0, 10.0, "hold")
    assert [node.get("x", t) for t in (1.99, 2.0)] == [0.0, 10.0]


def test_a_mistyped_property_or_ease_is_an_error():
    with pytest.raises(KeyError, match="Properties: x, y"):
        Node().key("opactiy", 0.0, 1.0)
    with pytest.raises(KeyError, match="Eases: linear"):
        Node().key("x", 0.0, 1.0, "bounce")


def test_a_group_moves_its_words():
    scene = scene_with("place", "fit")
    group, word = scene.groups[0], scene.groups[0].words[0]
    before = word.corners(5.0)
    group.base["x"] += 100
    assert [x for x, _ in word.corners(5.0)] == pytest.approx([x + 100 for x, _ in before])


def test_lines_stack_with_a_gap_between_their_ink():
    specs, duration = groups(texts=("Top lowly jog",))
    group = build(specs, BASIC, LOOK, duration).groups[0]
    group.set_lines((1, 1, 1), 100.0)
    ink = [group.look.fonts.measure(w.text) for w in group.words]
    assert group.h == pytest.approx(100 * (sum(top + bottom for _, top, bottom in ink) + 2 * LOOK.line_gap))
    tops = [w.base["y"] - w.top for w in group.words]
    bottoms = [w.base["y"] + w.bottom for w in group.words]
    assert [b - a for a, b in zip(bottoms, tops[1:])] == pytest.approx([100 * LOOK.line_gap] * 2)


# The registry


@pytest.mark.parametrize("slot", SLOTS)
def test_shared_every_effect_is_documented_and_works_with_no_parameters(slot):
    assert EFFECTS[slot], f"no {slot} effects registered"
    for name, fn in EFFECTS[slot].items():
        assert inspect.getdoc(fn), f"{slot} {name} has no docstring"
        params = list(inspect.signature(fn).parameters.values())[SLOTS[slot] :]
        assert all(p.default is not inspect.Parameter.empty for p in params), f"{slot} {name} needs defaults"
        scene_with(slot, name, CANVAS if slot == "camera" else BASIC)


@pytest.mark.parametrize(
    "spec, message",
    [
        ("spin", "unknown retire effect 'spin'. Known: "),
        ({"type": "fade", "durr": 1}, "retire.durr: fade has no such parameter. Known: after, dur, hold"),
        ({"type": "fade", "dur": "1s"}, "retire.dur: expected a number"),
        ({"type": "fade", "hold": True}, "retire.hold: expected a number or null"),
        ({"dur": 1}, "expected an effect name"),
    ],
)
def test_a_bad_effect_choice_names_the_fix(spec, message):
    with pytest.raises(EffectError, match=message.replace(".", r"\.").replace("(", r"\(")):
        resolve("retire", spec)


def test_a_group_can_override_a_slot_and_its_mistakes_name_the_group():
    specs, duration = groups()
    specs[1] = GroupSpec(specs[1].words, retire={"type": "fly-left", "dur": 0.2})
    scene = build(specs, BASIC, LOOK, duration)
    assert "x" in scene.groups[1].tracks and "x" not in scene.groups[0].tracks
    specs[1] = GroupSpec(specs[1].words, arrive="zoom")
    with pytest.raises(EffectError, match=r"groups\[1\]\.arrive: unknown arrive effect"):
        build(specs, BASIC, LOOK, duration)


# Shared contracts for each slot


@every("place")
def test_shared_placement_is_repeatable_and_finite(name):
    first, second = scene_with("place", name), scene_with("place", name)
    for a, b in zip(first.groups, second.groups):
        assert a.base == b.base and all(math.isfinite(v) for v in a.base.values())
        assert [w.base for w in a.words] == [w.base for w in b.words]


@every("arrive")
def test_shared_a_word_arrives_as_it_is_spoken_and_settles_where_it_was_placed(name):
    for group in scene_with("arrive", name).groups:
        for word in group.words:
            assert word.get("opacity", word.start - 0.5) == 0, f"{word.text} shows before it is spoken"
            assert word.get("opacity", word.start + 1 / LOOK.fps) > 0, f"{word.text} is hidden while spoken"
            assert at_rest(word, word.start + 0.5), f"{word.text} hasn't settled"


@every("retire")
def test_shared_a_group_holds_still_while_spoken_and_leaves_for_good(name):
    """Every retire effect times its exit the same way, with after and hold."""
    assert {"after", "hold"} <= set(inspect.signature(EFFECTS["retire"][name]).parameters)
    scene = scene_with("retire", {"type": name, "after": 1})
    for group in scene.groups:
        for t in np.linspace(group.start, group.words[-1].start, 8):
            assert at_rest(group, t), f"{group.words[0].text} moves while spoken, at {t:.2f}s"
    for group in scene.groups[:-1]:
        gone = [t for t in np.arange(group.end, scene.duration, 0.05) if group.get("opacity", t) == 0]
        assert gone, f"{group.words[0].text} never leaves"
        assert all(group.get("opacity", t) == 0 for t in np.arange(gone[0], scene.duration, 0.05))


@every("camera")
def test_shared_the_camera_keeps_each_word_in_frame_while_it_is_spoken(name):
    """With fit, everything rests at the center, so any camera should keep it in view."""
    scene = scene_with("camera", name)
    for t in np.arange(0, scene.duration, 0.1):
        assert scene.camera.get("zoom", t) > 0 and all(math.isfinite(scene.camera.get(p, t)) for p in ("x", "y", "rot"))
    assert_words_in_frame(scene)


def assert_words_in_frame(scene):
    for group in scene.groups:
        for word in group.words:
            t = word.start + 0.3
            for x, y in scene.on_screen(word, t):
                assert 0 <= x <= LOOK.width and 0 <= y <= LOOK.height, f"{word.text} is off screen at {t:.2f}s"


# The canvas


def assert_no_landing_on_visible_words(scene):
    for i, group in enumerate(scene.groups):
        for older in scene.groups[:i]:
            if any(w.opacity(group.start) > 0.05 for w in older.words):
                assert not quads_overlap(group.corners(), older.corners()), (
                    f"{group.words[0].text!r} lands on {older.words[0].text!r}"
                )


@pytest.mark.parametrize("slots", [BASIC, CANVAS], ids=["fit", "canvas"])
def test_a_group_never_lands_on_words_still_showing(slots):
    specs, duration = groups()
    assert_no_landing_on_visible_words(build(specs, slots, LOOK, duration))


@pytest.mark.parametrize("turn", [-90, -30, 12, 45, 90])
@pytest.mark.parametrize("side", ["below", "above", "right", "left"])
def test_a_turned_group_is_placed_by_its_turned_footprint(side, turn):
    specs, duration = groups(texts=("a wide first group", "then a long turned one"), hints=[{}, {"side": side, "turn": turn}])
    scene = build(specs, {**CANVAS, "retire": "fade"}, LOOK, duration)
    assert not quads_overlap(scene.groups[0].corners(), scene.groups[1].corners(), margin=1)


def test_the_camera_follows_words_around_the_canvas():
    specs, duration = groups()
    scene = build(specs, CANVAS, LOOK, duration)
    assert len({round(g.base["x"]) for g in scene.groups}) > 2, "the canvas should spread the groups out"
    assert_words_in_frame(scene)
