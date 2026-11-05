"""Stress measured from the voice, on synthetic speech."""

import numpy as np

from kinetic_typography.model import Word
from kinetic_typography.voice import RATE, stress


def speech(words):
    """A voiced tone per word, (pitch in hertz, loudness, seconds), with short silences between."""
    samples, timed, t = [], [], 0.0
    for text, (pitch, loudness, seconds) in words:
        clock = np.arange(int(RATE * seconds)) / RATE
        samples += [loudness * np.sin(2 * np.pi * pitch * clock), np.zeros(int(RATE * 0.15))]
        timed.append(Word(text, t, t + seconds))
        t += seconds + 0.15
    return np.concatenate(samples).astype(np.float32), timed


def test_a_louder_higher_longer_word_is_the_most_stressed():
    plain = (140, 0.1, 0.3)
    samples, words = speech([("this", plain), ("crew", plain), ("took", plain), ("twenty", (220, 0.4, 0.55)),
                             ("whole", plain), ("dull", plain), ("minutes.", plain)])  # fmt: skip
    ranks = stress(samples, words)
    assert ranks[3] == 1.0
    assert min(ranks) == 0.0 and len(set(ranks)) == len(ranks)


def test_silence_and_a_single_word_still_give_a_rank():
    assert stress(np.zeros(RATE, np.float32), [Word("hello", 0.1, 0.5), Word("there", 0.6, 0.9)]) in ([0.0, 1.0], [1.0, 0.0])
    assert stress(np.zeros(RATE, np.float32), [Word("hello", 0.1, 0.5)]) == [0.5]
