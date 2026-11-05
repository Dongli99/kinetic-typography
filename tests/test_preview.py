"""`kinetic preview`: contact sheets and low-resolution clips."""

import json
import subprocess
import wave

import numpy as np
import pytest
import skia

from kinetic_typography.cli import main
from kinetic_typography.render import COLUMNS, LABEL, TILE_WIDTH, FrameRenderer


@pytest.fixture
def plan(tmp_path):
    with wave.open(str(tmp_path / "talk.wav"), "wb") as audio:  # 3 seconds of silence
        audio.setnchannels(1), audio.setsampwidth(2), audio.setframerate(16000)
        audio.writeframes(b"\0\0" * 48000)
    texts = ["one", "two", "three", "four", "five", "six", "seven", "eight"]
    data = {
        "version": 2, "audio": "talk.wav", "duration": 3.0, "look": {"width": 640, "height": 360},
        "sections": [{"groups": [{"text": text} for text in texts]}],
        "words": [{"text": text, "start": 0.2 + i * 0.3, "end": 0.45 + i * 0.3} for i, text in enumerate(texts)],
    }  # fmt: skip
    path = tmp_path / "talk.plan.json"
    path.write_text(json.dumps(data))
    return str(path)


def preview(capsys, *arguments):
    code = main(["preview", *arguments, "--json"])
    return code, json.loads(capsys.readouterr().out)


def test_a_sheet_has_a_labelled_tile_per_group_as_it_lands(plan, tmp_path, capsys):
    code, result = preview(capsys, "--plan", plan, "--out", str(tmp_path / "sheet.png"))
    assert code == 0
    assert [t["group"] for t in result["tiles"]] == [f"sections[0].groups[{i}]" for i in range(8)]
    assert result["tiles"][0]["at"] == 0.45  # its last word's start, plus 0.25s
    image = skia.Image.open(str(tmp_path / "sheet.png"))
    tile_height = 360 * TILE_WIDTH // 640
    assert (image.width(), image.height()) == (COLUMNS * (TILE_WIDTH + 4), 2 * (tile_height + LABEL + 4))


def test_a_sheet_covers_only_the_range_asked_for(plan, tmp_path, capsys):
    code, result = preview(capsys, "--plan", plan, "--out", str(tmp_path / "sheet.png"), "--from", "1", "--to", "2")
    assert code == 0 and [t["at"] for t in result["tiles"]] == [1.05, 1.35, 1.65, 1.95]
    code, result = preview(capsys, "--plan", plan, "--out", str(tmp_path / "sheet.png"), "--from", "2", "--to", "1")
    assert code == 1 and "--from and --to" in result["error"]


def test_a_preview_needs_a_png_or_an_mp4(plan, tmp_path, capsys):
    code, result = preview(capsys, "--plan", plan, "--out", str(tmp_path / "clip.gif"))
    assert code == 1 and ".png contact sheet or an .mp4 clip" in result["error"]


def test_a_clip_is_half_size_and_only_the_range_asked_for(plan, tmp_path, capsys):
    clip = str(tmp_path / "clip.mp4")
    code, result = preview(capsys, "--plan", plan, "--out", clip, "--from", "1", "--to", "2")
    assert code == 0 and result["scale"] == 0.5
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,duration",
                            "-of", "json", clip], capture_output=True, text=True, check=True)  # fmt: skip
    streams = {s["codec_type"]: s for s in json.loads(probe.stdout)["streams"]}
    assert (streams["video"]["width"], streams["video"]["height"]) == (320, 180)
    assert float(streams["video"]["duration"]) == pytest.approx(1.0, abs=0.05)
    assert float(streams["audio"]["duration"]) == pytest.approx(1.0, abs=0.05)


def test_a_smaller_frame_shows_the_same_picture(plan):
    from kinetic_typography.plan import load_plan

    scene = load_plan(plan).make_scene()
    full = FrameRenderer(scene).draw(0.6)[..., :3].astype(float)
    half = FrameRenderer(scene, 0.5).draw(0.6)[..., :3].astype(float)
    shrunk = full.reshape(180, 2, 320, 2, 3).mean(axis=(1, 3))
    assert np.abs(shrunk - half).mean() < 3 and half.std() > 10


# Rendering: motion blur, paper and parallel frames


def moving_scene(plan_path, preset="gap"):
    from kinetic_typography.plan import load_plan

    loaded = load_plan(plan_path)
    loaded.preset = preset
    return loaded.make_scene()


def test_a_frame_is_the_same_whatever_was_drawn_before_it(plan):
    """Workers draw frames out of order, so no frame may depend on the one before."""
    scene = moving_scene(plan)
    fresh = FrameRenderer(scene).draw(1.0).copy()
    used = FrameRenderer(scene)
    used.draw(2.5), used.draw(0.3)
    assert np.array_equal(used.draw(1.0), fresh)


def test_the_camera_blurs_only_while_it_moves(plan):
    still, moving = FrameRenderer(moving_scene(plan, "plain")), FrameRenderer(moving_scene(plan))
    times = np.arange(0, 3, 1 / 30)
    assert {still.samples(t) for t in times} == {1}
    counts = [moving.samples(t) for t in times]
    assert max(counts) > 1 and min(counts) == 1  # it travels between groups and rests on them


def test_paper_is_the_same_every_time_and_toasted_at_the_corners(plan):
    a, b = (FrameRenderer(moving_scene(plan)).draw(0.0)[..., :3].astype(float) for _ in range(2))
    assert np.array_equal(a, b)
    middle, corner = a[150:210, 290:350].mean(), a[:30, :30].mean()
    assert corner < middle - 20 and a[150:210, 290:350].std() > 1  # darker edges, and not flat


def test_frames_drawn_in_parallel_make_the_same_video(plan, tmp_path, monkeypatch):
    from kinetic_typography import render
    from kinetic_typography.plan import load_plan

    loaded = load_plan(plan)
    loaded.preset = "gap"
    monkeypatch.setattr(render, "PARALLEL_FROM", 10**6)
    render.render_video(loaded.make_scene, loaded.audio, str(tmp_path / "one.mp4"), scale=0.25)
    monkeypatch.setattr(render, "PARALLEL_FROM", 1)
    monkeypatch.setattr(render.os, "cpu_count", lambda: 2)
    render.render_video(loaded.make_scene, loaded.audio, str(tmp_path / "two.mp4"), scale=0.25)
    assert (tmp_path / "one.mp4").read_bytes() == (tmp_path / "two.mp4").read_bytes()
