import json
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from kinetic_typography import cli
from kinetic_typography.align import LETTER_IDS, PAD_ID, VOCAB, Alignment, align_to_log_probs, tokenize_script
from kinetic_typography.cli import main
from kinetic_typography.model import Word
from kinetic_typography.phrases import GROUP_SIZES, LINE_SIZES, group_phrases, merge_numbers
from kinetic_typography.plan import load_plan
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
    assert all(len(phrase.words) <= max(GROUP_SIZES) for phrase in phrases)
    assert all(sum(phrase.lines) == len(phrase.words) and max(phrase.lines) <= max(LINE_SIZES) for phrase in phrases)


def test_a_group_is_a_clause_in_lines():
    phrases = group_phrases(timed("Six point three billion dollars left the world's biggest crypto exchange in twenty minutes."))
    assert len(phrases) < 3 and any(len(phrase.lines) > 1 for phrase in phrases)


def test_a_long_pause_between_sentences_starts_a_section_once_one_is_long_enough():
    first = timed("Apples pears plums figs dates limes kiwis mangos grapes melons lemons peaches.")
    later = [Word(w.text, w.start + 10, w.end + 10) for w in timed("Then more. And more.")]
    phrases = group_phrases(first + later)
    assert [p.section for p in phrases].count(True) == 1 and phrases[[p.section for p in phrases].index(True)].words[0].text == "Then"
    short = timed("Apples pears.") + later
    assert not any(p.section for p in group_phrases(short))


# Emphasis


def emphasized(words):
    """Each marked word and its level, in order."""
    return [
        (word.text.strip(".,?!"), level)
        for phrase in group_phrases(words)
        for word, level in zip(phrase.words, phrase.levels)
        if level
    ]


def test_a_number_outranks_a_longer_word():
    assert emphasized(timed("Vast losses reached 30")) == [("30", "hero")]


def test_a_money_amount_is_emphasized():
    assert ("$6.3 billion", "hero") in emphasized(timed("Six point three billion dollars left"))


def test_emphasis_skips_stop_words():
    assert emphasized(timed("into the wilderness")) == [("wilderness", "weight")]


def test_a_repeated_word_gives_way_to_a_new_one():
    picks = [text for text, _ in emphasized(timed("Accounts froze at Binance. Withdrawals stopped at Binance."))]
    assert picks.count("Binance") == 1, picks


def test_a_repeated_number_is_one_number_not_its_magnitude():
    assert "3.3 billion" in dict(emphasized(timed("Six point three billion dollars left. Three point three billion stayed.")))


def test_a_negation_is_tone():
    assert ("never", "tone") in emphasized(timed("The money will never be found"))


def test_emphasis_is_rare_and_has_one_hero_at_most():
    script = """The comforting story: your money sits in a vault, offline, untouchable. Picture a shop till,
    cash out front. This money sat in the online version: a hot wallet, always connected. Binance says it
    began with a compromised engineer's laptop. One copied key opened tills on ten chains."""
    levels = [level for phrase in group_phrases(timed(script)) for level in phrase.levels]
    assert 0 < sum(map(bool, levels)) <= 0.2 * len(levels)
    assert levels.count("hero") <= 1


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

    def run(heard="", script=None, size=None):
        monkeypatch.setattr(cli, "_require_ffmpeg", lambda: None)
        monkeypatch.setattr(cli, "decode_audio", lambda path: "samples")
        monkeypatch.setattr(cli, "transcribe", lambda samples: fake_transcribe(samples, heard))
        monkeypatch.setattr(cli, "align_script", fake_align)
        arguments = ["plan", "--audio", str(audio), "--out", str(tmp_path / "out.plan.json"), "--json"]
        if size:
            arguments += ["--size", size]
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


def test_a_size_is_written_into_the_drafts_look(plan_command, tmp_path):
    code, result, _ = plan_command(heard="Hello there.", size="1080x1920")
    assert code == 0 and result["size"] == [1080, 1920]
    assert load_plan(str(tmp_path / "out.plan.json")).look == {"width": 1080, "height": 1920}


def test_a_draft_reports_that_its_emphasis_came_from_rules(plan_command):
    code, result, _ = plan_command(heard="Hello there.")
    assert code == 0 and result["emphasis_from"] == "rules"


def test_a_script_replaces_the_recognizer(plan_command, tmp_path):
    code, result, calls = plan_command(heard="wrong words", script="Right words.")
    assert code == 0
    assert result["words_from"] == "script"
    assert calls == []
    assert [word.text for word in load_plan(str(tmp_path / "out.plan.json")).words] == ["Right", "words."]


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
