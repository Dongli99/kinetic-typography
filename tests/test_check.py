"""`kinetic check`: each problem it reports, shown both found and absent."""

import json

from kinetic_typography.build import build
from kinetic_typography.check import check
from kinetic_typography.cli import main
from kinetic_typography.scene import GroupSpec, Look, WordSpec

LOOK = Look(1920, 1080)
SLOTS = {"place": "fit", "arrive": "fade", "retire": {"type": "fade", "after": 1, "dur": 0.1}, "camera": "still"}


def run(slots=None, texts=("one two", "three four", "five six"), at=None, gap=0.5, word=0.3, level=None):
    specs, t = [], 0.5
    for index, text in enumerate(texts):
        words = []
        for token in text.split():
            words.append(WordSpec(token, t, t + word, level=level))
            t += word
        specs.append(GroupSpec(tuple(words), at=(at or {}).get(index, {})))
        t += gap
    scene = build(specs, {**SLOTS, **(slots or {})}, LOOK, t + 2.0)
    return check(scene, [f"sections[0].groups[{i}]" for i in range(len(specs))])


def test_a_well_spaced_scene_is_clean_and_every_word_was_seen():
    result = run()
    assert result["clean"] and result["styles"]["words"] == 6


def test_a_group_landing_on_one_still_showing_is_an_overlap():
    result = run({"retire": {"type": "fade", "after": 2, "dur": 0.1}})  # fit puts each group at the center, and now two show
    assert [(o["group"], o["lands_on"]) for o in result["overlaps"]] == [
        ("sections[0].groups[1]", "sections[0].groups[0]"),
        ("sections[0].groups[2]", "sections[0].groups[1]"),
    ]
    assert not result["clean"]


def test_side_by_side_groups_that_both_show_do_not_overlap():
    result = run({"place": "canvas", "retire": {"type": "fade", "after": 2}}, at={1: {"side": "right"}, 2: {"side": "below"}})
    assert result["overlaps"] == []


def test_a_word_past_the_frame_edge_is_clipped():
    result = run({"place": "canvas"}, at={1: {"side": "right", "gap": 800}})  # and the third hangs below it
    assert {(c["word"], c["edge"]) for c in result["clipped"]} == {(w, "right") for w in ("three", "four", "five", "six")}


def test_a_word_gone_before_it_can_be_read_is_brief():
    result = run(gap=0.05)  # each group leaves 0.1s before the next starts
    assert [b["word"] for b in result["brief"]] == ["two", "four"]
    assert all(b["shown"] < 0.3 for b in result["brief"])


def test_styles_report_each_marked_word_and_the_counts():
    styles = run(level="tone")["styles"]
    assert styles["tone"] == 6 and styles["hero"] == 0
    assert styles["styled"][0] == {"group": "sections[0].groups[0]", "word": "one", "at": 0.5, "level": "tone",
                                   "size": 1.0, "bold": False, "italic": False, "color": [245, 245, 240]}  # fmt: skip
    assert run()["styles"]["styled"] == []


def test_check_command_reports_one_json_result(tmp_path, capsys):
    (tmp_path / "talk.wav").write_bytes(b"")
    plan = {
        "version": 2, "audio": "talk.wav", "duration": 3.0,
        "sections": [{"groups": [{"text": "*hello* there"}]}],
        "words": [{"text": "hello", "start": 0.5, "end": 0.9}, {"text": "there", "start": 1.0, "end": 1.4}],
    }  # fmt: skip
    (tmp_path / "p.json").write_text(json.dumps(plan))
    assert main(["check", "--plan", str(tmp_path / "p.json"), "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] and result["clean"]
    assert [(s["word"], s["level"]) for s in result["styles"]["styled"]] == [("HELLO", "weight")]
