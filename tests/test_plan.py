"""The plan file: its format, its markup and the mistakes it reports."""

import copy
import json

import numpy as np
import pytest

from kinetic_typography.check import check
from kinetic_typography.cli import main
from kinetic_typography.effects import EFFECTS, HINTS, SLOTS, parameters
from kinetic_typography.model import Phrase, Word
from kinetic_typography.phrases import group_phrases
from kinetic_typography.draft import draft_plan
from kinetic_typography.plan import GROUP_FIELDS, LOOK_DEFAULTS, PRESETS, PlanError, load_plan, save_plan
from kinetic_typography.render import FrameRenderer

SPOKEN = ["$6.3 billion", "left", "the", "world's", "biggest", "crypto", "exchange."]
SERIF = {"font": "EB Garamond", "upper": False, "emphasis": {
    "hero": {"size": 2.0, "bold": True}, "weight": {"bold": True}, "tone": {"italic": True}}}  # fmt: skip


def timed(texts, gap=0.4):
    return [Word(text, round(0.5 + i * gap, 3), round(0.5 + i * gap + gap, 3)) for i, text in enumerate(texts)]


def plan_data(groups=None, look=None, defaults=None, **top):
    """A version 2 plan over SPOKEN, as the JSON an agent would write."""
    data = {
        "version": 2,
        "audio": "talk.wav",
        "duration": 5.0,
        "look": look or {},
        "defaults": defaults or {},
        "sections": [{"groups": [{"text": text} if isinstance(text, str) else text for text in groups]}]
        if groups is not None
        else [{"groups": [{"text": "$6.3 billion left"}, {"text": "the world's biggest crypto exchange."}]}],
        "words": [{"text": w.text, "start": w.start, "end": w.end} for w in timed(SPOKEN)],
    }
    data.update(top)
    return data


def load(tmp_path, data):
    (tmp_path / "talk.wav").write_bytes(b"")
    path = tmp_path / "talk.plan.json"
    path.write_text(json.dumps(data))
    return load_plan(str(path))


def words_of(tmp_path, data):
    return [w for g in load(tmp_path, data).make_scene().groups for w in g.words]


# Writing and reading


def test_a_draft_survives_a_round_trip_and_reads_one_word_per_line(tmp_path):
    (tmp_path / "talk.wav").write_bytes(b"")
    words = timed(SPOKEN)
    phrases = [Phrase(tuple(words[:2]), levels=("weight", None)), Phrase(tuple(words[2:]), (2, 3), (None, None, "tone", None, None))]
    plan = draft_plan(str(tmp_path / "talk.wav"), 5.0, phrases)
    path = tmp_path / "talk.plan.json"
    save_plan(plan, str(path))
    text = path.read_text()
    assert json.loads(text)["audio"] == "talk.wav"
    assert len(text.splitlines()) < 25
    loaded = load_plan(str(path))
    assert loaded.words == words and loaded.sections == plan.sections
    assert [g["text"] for g in loaded.sections[0]["groups"]] == ["*$6.3 billion* left", "the world's / _biggest_ crypto exchange"]


def test_a_draft_is_on_the_gap_canvas_with_emphasis_seen_at_a_glance():
    plan = draft_plan("talk.wav", 5.0, group_phrases(timed(SPOKEN)))
    words = [w for g in plan.make_scene().groups for w in g.words]
    marked = [w for w in words if w.spec.level]
    assert plan.preset == "gap" and words[0].text == "$6.3 billion" and words[-1].text == "exchange"
    assert marked and all(w.spec.size > 1.2 and (w.spec.bold or w.spec.italic) for w in marked)


def test_drafted_groups_land_clear_of_words_still_showing_and_inside_the_frame():
    script = """$6.3 billion left the world's biggest crypto exchange in twenty minutes. How do you rob a vault?
    The comforting story: your money sits in a vault, offline, untouchable. This crew took twenty minutes.
    Picture a shop till, cash out front. This money sat in the online version: a hot wallet, always connected.
    Binance says it began with a compromised engineer's laptop. One copied key opened tills on ten chains."""
    plan = draft_plan("talk.wav", 30.0, group_phrases(timed(script.split(), 0.3)))
    found = check(plan.make_scene(), plan.group_names())
    assert len(plan.group_names()) > 8 and sum("turn" in g.get("at", {}) for s in plan.sections for g in s["groups"]) > 1
    assert not found["overlaps"] and not found["clipped"], found


def test_a_version_1_plan_is_refused_with_the_way_forward(tmp_path):
    with pytest.raises(PlanError, match="version 1 plan.*Run `kinetic plan` again"):
        load(tmp_path, {"version": 1, "phrases": []})


# Markup


def test_each_level_takes_its_look(tmp_path):
    words = words_of(tmp_path, plan_data(["**$6.3 billion** left", "the _world's_ *biggest* crypto exchange."], SERIF))
    looks = {w.text: (w.spec.size, w.spec.bold, w.spec.italic) for w in words}
    assert looks["$6.3 billion"] == (2.0, True, False)
    assert looks["biggest"] == (1.0, True, False)
    assert looks["world's"] == (1.0, False, True)
    assert looks["left"] == (1.0, False, False)


def test_markup_and_size_cover_every_part_of_a_spoken_word(tmp_path):
    """The prototype dropped markup after the first part of '$6.3 billion' and said nothing."""
    words = words_of(tmp_path, plan_data(["*$6.3 billion*^2 left", "the world's biggest crypto exchange."]))
    assert (words[0].text, words[0].spec.size, words[0].color) == ("$6.3 BILLION", 1.35 * 2, (255, 210, 31))
    assert words[1].spec.size == 1.0


def test_marks_may_span_several_words_and_text_keeps_its_punctuation(tmp_path):
    look = {**SERIF, "upper": False}
    words = words_of(tmp_path, plan_data(["$6.3 billion left", "_the world's biggest_ crypto exchange."], look))
    assert [w.spec.italic for w in words] == [False, False, True, True, True, False, False]
    assert words[-1].text == "exchange."


def test_line_breaks_are_kept_even_by_fit(tmp_path):
    scene = load(tmp_path, plan_data(["$6.3 billion / left", "the world's biggest crypto exchange."])).make_scene()
    first = scene.groups[0].words
    assert first[1].base["y"] > first[0].base["y"]


def test_punctuation_between_words_joins_a_word(tmp_path):
    words = words_of(tmp_path, plan_data(["$6.3 billion — left", "the world's biggest crypto exchange. —"]))
    assert [w.text for w in words][:2] == ["$6.3 BILLION", "— LEFT"]
    assert words[-1].text == "EXCHANGE. —"


# Mistakes, each named where to fix it


def group_text(*texts):
    return lambda d: d["sections"][0].update(groups=[{"text": t} for t in texts])


REST = "the world's biggest crypto exchange."
MISTAKES = [
    (lambda d: d.update(version=99), "version: expected 2"),
    (lambda d: d.update(styles={}), "styles: unknown field"),
    (lambda d: d.update(duration=-1), "duration"),
    (lambda d: d.update(emphasis={"source": "voice"}), "emphasis.source: only \"meaning\" is available"),
    (lambda d: d["words"][1].update(start=9), r"words\[1\]: expected 0 <= start <= end"),
    (lambda d: d.update(sections=[]), "sections: expected a non-empty list"),
    (group_text("$6.3 billion lift", REST), r"groups\[0\]\.text: 'lift' doesn't match the next spoken word, 'left' \(words\[1\] at 0\.90s\)"),
    (group_text("$6.3 billion left", "the world's biggest crypto"), r"words\[6\] onward aren't in any group, from \"exchange\.\""),
    (group_text("$6.3 billion left", REST + " again"), r"groups\[1\]\.text: 'again' comes after the last spoken word"),
    (group_text("$6.3 billion", "left " + REST + " /"), "a line break needs words on both sides"),
    (group_text("/ $6.3 billion left", REST), "a line break needs words on both sides"),
    (group_text("$6.3 / billion left", REST), "a line break splits the spoken word \"\\$6.3 billion\""),
    (group_text("*$6.3* billion left", REST), "the markup covers only part of the spoken word '\\$6.3 billion'"),
    (group_text("$6.3 billion^2 left^", REST), "'left\\^': a \\^ needs a size after it"),
    (group_text("$6.3 billion *left", REST), "a weight mark is opened but never closed"),
    (group_text("$6.3 billion left*", REST), "'left\\*' closes a mark that was never opened"),
    (group_text("*$6.3 billion _left_*", REST), "opens tone inside weight"),
    (group_text("$6.3 billion^0 left", REST), "needs a positive size"),
    (group_text("$6.3", "billion left", REST), r"groups\[0\]\.text: the group ends partway through the spoken word"),
    (lambda d: d["sections"][0]["groups"][0].update(size=2), r"groups\[0\]\.size: unknown field"),
    (lambda d: d["sections"][0]["groups"][0].update(align="middle"), r"groups\[0\]\.align"),
    (lambda d: d["sections"][0]["groups"][1].update(at={"side": "right"}), r"groups\[1\]\.at: the place effect fit takes no hints"),
    (lambda d: d.update(defaults={"place": "canvas"}) or d["sections"][0]["groups"][1].update(at={"sid": "right"}), r"groups\[1\]\.at\.sid: canvas takes no such hint\. Known: side, turn"),
    (lambda d: d.update(defaults={"place": "canvas"}) or d["sections"][0]["groups"][1].update(at={"side": "up"}), r"at\.side: expected one of below, above, right, left"),
    (lambda d: d.update(defaults={"camera": "follow"}) or d["sections"][0]["groups"][1].update(camera={"with": 0}), r"camera\.with: expected a whole number from 1"),
    (lambda d: d.update(defaults={"retire": "vanish"}), "defaults.retire: unknown retire effect 'vanish'"),
    (lambda d: d.update(defaults={"zoom": "still"}), "defaults.zoom: unknown field"),
    (lambda d: d["sections"][0]["groups"][1].update(retire={"type": "fade", "durr": 1}), r"groups\[1\]\.retire\.durr: fade has no such parameter"),
    (lambda d: d.update(look={"colour": [0, 0, 0]}), "look.colour: unknown field"),
    (lambda d: d.update(preset="gapp"), "preset: expected one of plain, gap, got 'gapp'"),
    (lambda d: d.update(preset=["gap"]), "preset: expected one of plain, gap"),
    (lambda d: d.update(look={"paper": "yes"}), "look.paper: expected true or false"),
    (lambda d: d.update(look={"font": "Comic Sans"}), "look.font: expected one of Archivo Black, EB Garamond"),
    (lambda d: d.update(look={"ink": [0, 0, 300]}), r"look\.ink: expected \[red, green, blue\]"),
    (lambda d: d.update(look={"emphasis": {"weight": {"bold": True}}}), "look.emphasis.weight.bold: Archivo Black has no bold style. Fonts that do: EB Garamond"),
    (lambda d: d.update(look={"emphasis": {"tone": {}}}), "look.emphasis.tone: this looks the same as unmarked text"),
    (lambda d: d.update(look={"emphasis": {"bold": {}}}), "look.emphasis.bold: unknown field"),
]


@pytest.mark.parametrize("change, message", MISTAKES, ids=[m[1][:40] for m in MISTAKES])
def test_a_mistake_is_an_error_that_names_the_fix(tmp_path, change, message):
    data = plan_data()
    load(tmp_path, copy.deepcopy(data))  # the plan is fine before the change
    change(data)
    with pytest.raises(PlanError, match=message):
        load(tmp_path, data)


# Presets


def test_a_preset_supplies_a_look_and_effects_that_the_plan_overrides(tmp_path):
    scene = load(tmp_path, plan_data(preset="gap")).make_scene()
    assert (scene.look.font, scene.look.width, scene.look.paper) == ("EB Garamond", 1920, True)
    assert "blur" in scene.groups[0].words[0].tracks  # blur-in, not pop
    words = words_of(tmp_path, plan_data(["**$6.3 billion** left", REST], {"width": 1080, "emphasis": {"tone": {"size": 0.8}}},
                                         preset="gap"))  # fmt: skip
    hero = words[0]
    assert (hero.spec.size, hero.spec.bold) == (2.4, True)  # the preset's hero, kept
    assert load(tmp_path, plan_data(look={"width": 1080}, preset="gap")).make_scene().look.width == 1080


def test_a_plan_without_a_preset_is_plain_and_a_draft_says_which_it_uses(tmp_path):
    assert load(tmp_path, plan_data()).make_scene().look.font == "Archivo Black"
    plan = draft_plan(str(tmp_path / "talk.wav"), 5.0, group_phrases(timed(SPOKEN)))
    save_plan(plan, str(tmp_path / "draft.json"))
    assert json.loads((tmp_path / "draft.json").read_text())["preset"] == "gap"


# The plain look


def draft_scene(text, look=None, duration=10.0):
    """The draft's groups in the plain look, one at a time in the middle."""
    plan = draft_plan("talk.wav", duration, group_phrases(timed(text.split(), 0.2)))
    plan.preset, plan.look = "plain", look or {}
    for section in plan.sections:
        for group in section["groups"]:
            group.pop("at", None)
    return plan.make_scene()


@pytest.mark.parametrize("look", [{}, {"width": 1920, "height": 1080}, {"width": 1080, "height": 1920}])
@pytest.mark.parametrize("text", ["internationalization", "I", "the quick brown fox jumps", "extraordinary misunderstanding"])
def test_fit_stays_inside_the_margins(text, look):
    scene = draft_scene(text, look)
    for word in scene.groups[0].words:
        for x, y in scene.on_screen(word, word.start + 1.0):
            assert 89 <= x <= scene.look.width - 89 and 89 <= y <= scene.look.height - 89


def test_drafted_groups_are_never_on_screen_together():
    scene = draft_scene("One two. Three four. Five six.", duration=3.0)
    for t in np.arange(0, 3.0, 0.01):
        assert sum(any(w.opacity(t) > 0 for w in g.words) for g in scene.groups) <= 1, t


def test_rendering_is_repeatable_and_draws_text():
    renderer = FrameRenderer(draft_scene("alpha beta", duration=5.0))
    empty = renderer.draw(0.0).copy()
    first = renderer.draw(0.8).copy()
    assert first.shape == (1080, 1080, 4)
    assert np.array_equal(first, renderer.draw(0.8))
    assert not np.array_equal(first, empty)


def test_bold_and_italic_are_drawn_differently(tmp_path):
    words = words_of(tmp_path, plan_data(["$6.3 billion *left*", "_the_ world's biggest crypto exchange."], SERIF))
    regular, bold, italic = (words[i].font for i in (3, 1, 2))
    widths = [font.measureText("Garamond") / font.getSize() for font in (regular, bold, italic)]
    assert len(set(widths)) == 3 and widths[1] > widths[0]


# The command line and the guide


def test_frame_writes_a_png_from_an_edited_plan(tmp_path, capsys):
    load(tmp_path, plan_data(["**$6.3 billion** left", REST], SERIF))
    image = tmp_path / "frame.png"
    assert main(["frame", "--plan", str(tmp_path / "talk.plan.json"), "--at", "1.0", "--out", str(image), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert image.read_bytes().startswith(b"\x89PNG")


def test_guide_is_packaged_and_covers_every_command_field_and_effect(capsys):
    assert main(["guide"]) == 0
    guide = capsys.readouterr().out
    for command in ("make", "plan", "check", "preview", "render", "frame"):
        assert f"kinetic {command}" in guide, f"kinetic {command} is missing from the guide"
    for name in [*LOOK_DEFAULTS, *LOOK_DEFAULTS["emphasis"], *GROUP_FIELDS, *PRESETS, "preset", "sections", "words", "defaults", "emphasis"]:
        assert f"`{name}`" in guide, f"{name} is missing from the guide"
    for slot in SLOTS:
        for name in EFFECTS[slot]:
            assert f"**`{name}`**" in guide
            for key in [*parameters(slot, name), *HINTS[slot][name]]:
                assert f"`{key}`" in guide
