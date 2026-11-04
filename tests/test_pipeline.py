import dataclasses
import json
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from kinetic_typography import cli
from kinetic_typography.align import LETTER_IDS, PAD_ID, VOCAB, Alignment, align_to_log_probs, tokenize_script
from kinetic_typography.cli import main
from kinetic_typography.model import Phrase, Style, Word
from kinetic_typography.phrases import group_phrases, merge_numbers
from kinetic_typography.plan import Plan, PlanError, display_text, load_plan, save_plan
from kinetic_typography.render import FrameRenderer
from kinetic_typography.spoken import parse_number_words, spoken_words
from kinetic_typography.transcribe import Transcript, transcribe

FRAME = 0.02


def fake_audio(*events):
    """Build model output from ("text", seconds) events, where "" means silence.

    Each letter gets an equal share of its event's frames, followed by a blank, the way a
    real acoustic model reports speech.
    """
    rows = []
    for text, seconds in events:
        frames = round(seconds / FRAME)
        letters = [letter for letter in text.lower() if letter in LETTER_IDS]
        if not letters:
            rows += [PAD_ID] * frames
            continue
        share = max(2, frames // len(letters))
        for letter in letters:
            rows += [LETTER_IDS[letter]] * (share - 1) + [PAD_ID]
    probabilities = np.full((len(rows), len(VOCAB)), -12.0)
    probabilities[np.arange(len(rows)), rows] = -0.001
    return probabilities, len(rows) * FRAME


def align(script, *events):
    log_probs, duration = fake_audio(*events)
    return align_to_log_probs(tokenize_script(script), log_probs, duration)


def timed(text, gap=0.2):
    return [Word(token, i * gap, i * gap + gap) for i, token in enumerate(text.split())]


def phrase_texts(words):
    return [" ".join(word.text.strip(".,?!") for word in phrase.words) for phrase in group_phrases(words)]


# Timing


def test_tokenize_splits_dashes_and_drops_bare_punctuation():
    assert tokenize_script("Wait — what? well-known word--next - ok") == [
        "Wait—", "what?", "well-known", "word—", "next—", "ok",
    ]  # fmt: skip


def test_words_are_timed_where_they_are_spoken():
    result = align("alpha beta", ("", 1.0), ("alpha", 0.5), ("", 1.0), ("beta", 0.5), ("", 0.5))
    assert result.words[0].start == pytest.approx(1.0, abs=0.04)
    assert result.words[1].start == pytest.approx(2.5, abs=0.04)
    assert result.confidence > -0.5
    assert result.doubtful == []


def test_word_starting_with_the_previous_words_last_letter_waits_for_its_own_sound():
    # Regression: "the" claimed the end of "vault" and sat through the pause.
    result = align("vault the", ("vault", 0.5), ("", 1.0), ("the", 0.3))
    assert result.words[1].start == pytest.approx(1.5, abs=0.06)


def test_speech_missing_from_the_script_is_skipped():
    result = align(
        "alpha beta gamma delta",
        ("alpha", 0.4), ("beta", 0.4), ("you know i really think", 2.0), ("gamma", 0.4), ("delta", 0.4),
    )  # fmt: skip
    assert result.words[2].start == pytest.approx(2.7, abs=0.04)
    assert result.doubtful == []


def test_script_words_missing_from_the_speech_are_reported_and_neighbours_stay_right():
    spoken = "alpha beta gamma delta epsilon iota kappa lambda sigma omega"
    script = spoken.replace("gamma", "gamma zebra")
    events = [(word, 0.4) for word in spoken.split()]
    result = align(script, *events)
    assert result.doubtful == ["zebra"]
    assert result.words[4].start == pytest.approx(1.2, abs=0.08)


def test_a_script_that_does_not_match_is_refused():
    with pytest.raises(ValueError, match="doesn't match"):
        align("xylophone quartz zephyr jukebox", ("alpha beta", 1.0), ("", 1.0))


def test_a_script_too_long_for_the_audio_is_refused():
    with pytest.raises(ValueError, match="more letters"):
        align("alpha beta gamma delta epsilon", ("a", 0.04))


def test_symbols_with_no_sound_still_get_a_time():
    result = align("alpha 1 beta", ("alpha", 0.4), ("one", 0.3), ("beta", 0.4))
    assert [word.text for word in result.words] == ["alpha", "1", "beta"]
    assert result.words[1].start >= result.words[0].start


# How numbers sound


@pytest.mark.parametrize(
    "tokens, expected",
    [
        (["2026"], [["twenty", "twenty", "six"]]),
        (["1905"], [["nineteen", "oh", "five"]]),
        (["2000"], [["twenty", "hundred"]]),
        (["3,000"], [["three", "thousand"]]),
        (["42"], [["forty", "two"]]),
        (["20%"], [["twenty", "percent"]]),
        (["$5"], [["five", "dollars"]]),
        (["3rd"], [["third"]]),
        (["21st"], [["twenty", "first"]]),
        (["$6.3", "billion"], [["six", "point", "three"], ["billion", "dollars"]]),
        (["don’t,"], [["don't"]]),
    ],
)
def test_spoken_words(tokens, expected):
    assert spoken_words(tokens) == expected


# How numbers read


@pytest.mark.parametrize(
    "words, expected",
    [
        ("twenty minutes", ("20", 1)),
        ("twenty six people", ("26", 2)),
        ("twenty-six people", ("26", 1)),
        ("ten chains", ("10", 1)),
        ("three point three billion", ("3.3", 3)),
        ("two hundred and five", ("205", 4)),
        ("twenty twenty six", ("2026", 3)),
        ("nineteen ninety", ("1990", 2)),
        ("twelve thousand", ("12,000", 2)),
        ("three million", ("3", 1)),
        ("one copied key", None),
        ("no one", None),
        ("nine lives", None),
    ],
)
def test_parse_number_words(words, expected):
    from kinetic_typography.spoken import letters_only

    assert parse_number_words([letters_only(word) for word in words.split()]) == expected


def test_money_merges_into_one_unit_with_its_timing():
    words = [
        Word("Six", 0.0, 0.1), Word("point", 0.1, 0.2), Word("three", 0.2, 0.3),
        Word("billion", 0.3, 0.4), Word("dollars", 0.4, 0.5), Word("left.", 0.5, 0.6),
    ]  # fmt: skip
    merged = merge_numbers(words)
    assert merged == [Word("$6.3 billion", 0.0, 0.5), Word("left.", 0.5, 0.6)]


def test_digits_in_the_script_also_merge_with_their_magnitude():
    assert merge_numbers(timed("$6.3 billion, gone"))[0].text == "$6.3 billion,"


def test_punctuation_stops_a_number_from_absorbing_the_next_clause():
    assert [word.text for word in merge_numbers(timed("Chapter twenty, one more"))] == [
        "Chapter", "20,", "one", "more",
    ]  # fmt: skip


# Phrasing


def test_names_stay_together():
    words = timed("Tracing firms suspect North Korea's Trader Traitor group")
    assert all("North" not in text or "Korea's" in text for text in phrase_texts(words))
    assert all("Trader" not in text or "Traitor" in text for text in phrase_texts(words))
    assert "group" not in phrase_texts(words)


def test_a_possessive_stays_with_what_it_owns():
    texts = phrase_texts(timed("Money left the world's biggest crypto exchange today"))
    assert any("world's biggest" in text for text in texts), texts


def test_dates_stay_together():
    words = timed("It vanished in twenty minutes on October 29 from Binance wallets")
    texts = phrase_texts(words)
    assert any("October 29" in text for text in texts), texts


def test_a_count_stays_with_what_it_counts():
    texts = phrase_texts(timed("One copied key opened tills on ten chains"))
    assert any("10 chains" in text for text in texts), texts


def test_phrases_do_not_end_on_a_word_that_promises_more():
    texts = phrase_texts(timed("Six point three billion dollars left the world's biggest crypto exchange"))
    for text in texts:
        assert text.split()[-1].lower() not in ("the", "of", "a", "in"), texts


def test_sentences_never_share_a_phrase():
    assert phrase_texts(timed("Stop. Look up.")) == ["Stop", "Look up"]


def test_a_long_pause_breaks_a_phrase():
    words = [Word("Look", 0.0, 0.2), Word("up", 0.2, 0.4), Word("now", 1.5, 1.7)]
    assert phrase_texts(words) == ["Look up", "now"]


def test_every_word_survives_in_order_within_the_limits():
    words = timed("apples pears plums figs dates limes kiwis mangos grapes melons lemons peaches")
    phrases = group_phrases(words)
    assert [word for phrase in phrases for word in phrase.words] == words
    assert all(len(phrase.words) <= 5 for phrase in phrases)


# Emphasis


def emphasized(words):
    return [
        phrase.words[phrase.emphasis].text.strip(".,?!") for phrase in group_phrases(words) if phrase.emphasis is not None
    ]


def test_a_number_outranks_a_longer_word():
    assert emphasized(timed("Vast losses reached 30"))[-1] == "30"


def test_a_money_amount_is_emphasized():
    assert "$6.3 billion" in emphasized(timed("Six point three billion dollars left"))


def test_emphasis_skips_stop_words():
    assert emphasized(timed("into the wilderness")) == ["wilderness"]


def test_a_repeated_word_gives_way_to_a_new_one():
    picks = emphasized(timed("Binance froze accounts. Binance named nobody."))
    assert picks[-1] != "Binance"


def test_display_text_keeps_questions_and_contractions():
    assert display_text("“don’t,”") == "DON'T"
    assert display_text("why?") == "WHY?"
    assert display_text("$6.3 billion,") == "$6.3 BILLION"


# Today's look, through the scene


def plain_scene(text, style=Style(), duration=10.0, phrases=None):
    return Plan("talk.wav", duration, phrases or group_phrases(timed(text)), dataclasses.asdict(style)).make_scene()


@pytest.mark.parametrize("style", [Style(), Style(width=1920, height=1080), Style(width=1080, height=1920)])
@pytest.mark.parametrize(
    "text",
    ["internationalization", "I", "the quick brown fox jumps", "extraordinary misunderstanding"],
)
def test_layout_stays_inside_the_margins(text, style):
    scene = plain_scene(text, style)
    for word in scene.groups[0].words:
        for x, y in scene.on_screen(word, word.start + 1.0):
            assert style.margin - 1 <= x <= style.width - style.margin + 1
            assert style.margin - 1 <= y <= style.height - style.margin + 1


def test_phrases_are_never_on_screen_together():
    scene = plain_scene("One two. Three four. Five six.", duration=3.0)
    for t in np.arange(0, 3.0, 0.01):
        assert sum(any(w.opacity(t) > 0 for w in g.words) for g in scene.groups) <= 1, t


def test_word_is_hidden_until_it_is_spoken_then_settles():
    scene = plain_scene("", phrases=[Phrase(tuple(timed("alpha beta")), 1)], duration=5.0)
    second = scene.groups[0].words[1]
    assert second.opacity(second.start - 0.01) == 0
    for prop in ("opacity", "scale", "x", "y"):
        assert second.get(prop, second.start + 0.25) == pytest.approx(second.base[prop])


def test_rendering_is_repeatable_and_draws_text():
    renderer = FrameRenderer(plain_scene("alpha beta", duration=5.0))
    empty = renderer.draw(0.0).copy()
    first = renderer.draw(0.3).copy()
    second = renderer.draw(0.3).copy()
    assert first.shape == (1080, 1080, 4)
    assert np.array_equal(first, second)
    assert not np.array_equal(first, empty)


# Plan file


def sample_plan(tmp_path):
    audio = tmp_path / "talk.wav"
    audio.write_bytes(b"")
    return Plan(str(audio), 5.0, [Phrase((Word("alpha", 1.0, 1.5), Word("beta,", 1.5, 2.0)), 1)], {"fps": 24})


def test_plan_survives_a_round_trip_with_audio_relative_to_it(tmp_path):
    plan = sample_plan(tmp_path)
    path = tmp_path / "talk.plan.json"
    save_plan(plan, str(path))
    assert json.loads(path.read_text())["audio"] == "talk.wav"
    loaded = load_plan(str(path))
    assert loaded.phrases == plan.phrases
    assert loaded.make_style().fps == 24
    assert loaded.audio == str(tmp_path / "talk.wav")


@pytest.mark.parametrize(
    "change, field",
    [
        (lambda d: d.update(version=99), "version"),
        (lambda d: d.update(duration=-1), "duration"),
        (lambda d: d["style"].update(colour=1), "style.colour"),
        (lambda d: d["phrases"][0].update(emphasis=9), "phrases[0].emphasis"),
        (lambda d: d["phrases"][0]["words"][1].update(start=9), "phrases[0].words[1]"),
        (lambda d: d["phrases"][0]["words"][0].update(text=" "), "phrases[0].words[0].text"),
        (lambda d: d.update(phrases=[]), "phrases"),
    ],
)
def test_a_bad_plan_names_the_field_to_fix(tmp_path, change, field):
    path = tmp_path / "plan.json"
    save_plan(sample_plan(tmp_path), str(path))
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))
    with pytest.raises(PlanError) as error:
        load_plan(str(path))
    assert field in str(error.value)


# Command line


@pytest.fixture
def plan_command(tmp_path, monkeypatch, capsys):
    """Run `kinetic plan` with the models faked, returning the result and the recognizer's calls."""
    audio = tmp_path / "talk.wav"
    audio.write_bytes(b"")
    calls = []

    def fake_transcribe(samples, heard):
        calls.append(samples)
        return Transcript(heard, ["mishard"] if heard else [])

    def fake_align(tokens, samples):
        words = [Word(token, index, index + 0.5) for index, token in enumerate(tokens)]
        return Alignment(words, len(tokens), -0.1, [])

    def run(heard="", script=None):
        monkeypatch.setattr(cli, "_require_ffmpeg", lambda: None)
        monkeypatch.setattr(cli, "decode_audio", lambda path: "samples")
        monkeypatch.setattr(cli, "transcribe", lambda samples: fake_transcribe(samples, heard))
        monkeypatch.setattr(cli, "align_script", fake_align)
        arguments = ["plan", "--audio", str(audio), "--out", str(tmp_path / "out.plan.json"), "--json"]
        if script is not None:
            path = tmp_path / "script.txt"
            path.write_text(script)
            arguments += ["--script", str(path)]
        code = main(arguments)
        return code, json.loads(capsys.readouterr().out), calls

    return run


def test_audio_alone_is_enough_and_misheard_words_are_reported(plan_command):
    code, result, _ = plan_command(heard="Hello there.")
    assert code == 0
    assert result["words_from"] == "audio"
    assert result["doubtful"] == ["mishard"]


def test_a_script_replaces_the_recognizer(plan_command, tmp_path):
    code, result, calls = plan_command(heard="wrong words", script="Right words.")
    assert code == 0
    assert result["words_from"] == "script"
    assert calls == []
    words = [word.text for phrase in load_plan(str(tmp_path / "out.plan.json")).phrases for word in phrase.words]
    assert words == ["Right", "words."]


def test_audio_with_no_speech_is_an_error_not_an_empty_video(plan_command):
    code, result, _ = plan_command(heard="")
    assert code == 1
    assert "No speech" in result["error"]


def test_recognizer_reports_only_low_probability_words(monkeypatch, tmp_path):
    word = lambda text, probability: SimpleNamespace(word=text, probability=probability)
    segment = SimpleNamespace(text=" One two.", words=[word(" One", 0.9), word(" two.", 0.2)])
    model = SimpleNamespace(transcribe=lambda samples, **options: (iter([segment]), None))
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=lambda *a, **k: model))
    monkeypatch.setitem(sys.modules, "faster_whisper.utils", SimpleNamespace(download_model=lambda *a, **k: "path"))
    monkeypatch.setenv("KINETIC_CACHE", str(tmp_path))
    assert transcribe(np.zeros(10)) == Transcript("One two.", ["two."])


def test_json_mode_reports_errors_as_one_object_on_stdout(capsys):
    assert main(["render", "--plan", "missing.json", "--json"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["ok"] is False
    assert "missing.json" in result["error"]


def test_frame_writes_a_png_from_an_edited_plan(tmp_path, capsys):
    path = tmp_path / "plan.json"
    save_plan(sample_plan(tmp_path), str(path))
    image = tmp_path / "frame.png"
    assert main(["frame", "--plan", str(path), "--at", "1.8", "--out", str(image), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert image.read_bytes().startswith(b"\x89PNG")


def test_guide_is_packaged_and_covers_every_style_setting(capsys):
    assert main(["guide"]) == 0
    guide = capsys.readouterr().out
    from dataclasses import fields

    for setting in fields(Style):
        assert f"`{setting.name}`" in guide, f"{setting.name} is missing from the guide"
    for command in ("make", "plan", "render", "frame"):
        assert f"kinetic {command}" in guide, f"kinetic {command} is missing from the guide"
