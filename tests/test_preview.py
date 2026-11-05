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
