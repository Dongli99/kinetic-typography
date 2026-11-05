"""How strongly the voice stressed each word: a hint for whoever marks emphasis, never a decision.

Per word: loudness, pitch peak, pitch range and length, each against the speaker's trend through
the sentence, and the pauses around it. The six are weighted equally, fixed in advance rather than
tuned to a reference. On a text-to-speech narration they ranked a person's marked words with an
AUC of 0.68, where 0.5 is chance.
"""

import numpy as np

from .model import Word

RATE = 16000
HOP = 0.010  # seconds between frames
NEAR = 2.0  # seconds either side that a word is compared with
SENTENCE_ENDS = ".?!:;"


def stress(samples: np.ndarray, words: list[Word]) -> list[float]:
    """Each word's stress as its rank in the recording, from 0 (least) to 1 (most)."""
    if len(words) < 2:
        return [0.5] * len(words)
    loud = _loudness(samples)
    semitones = _pitch(samples)
    count = min(len(loud), len(semitones))
    loud, semitones = loud[:count], semitones[:count]
    times = np.arange(count) * HOP + 0.015
    if np.any(~np.isnan(semitones)):
        semitones = 12 * np.log2(semitones / np.nanmedian(semitones))

    letters = np.array([max(1, sum(c.isalnum() for c in w.text)) for w in words])
    lengths = np.array([w.end - w.start for w in words])
    # The expected length for a word's letters, in this voice.
    slope, base = np.polyfit(letters, lengths, 1) if len(set(letters)) > 1 else (0.0, lengths.mean())
    features = {name: [] for name in ("loudness", "pitch peak", "pitch range", "length", "pause after", "pause before")}
    for i, w in enumerate(words):
        inside = (times >= w.start) & (times < max(w.end, w.start + 0.03))
        near = (times >= w.start - NEAR) & (times < w.end + NEAR)
        features["loudness"].append(np.percentile(loud[inside], 90) - np.median(loud[near]) if inside.any() else np.nan)
        pitch = semitones[inside]
        pitch = pitch[~np.isnan(pitch)]
        around = semitones[near]
        around = np.nanmedian(around) if np.any(~np.isnan(around)) else 0.0
        features["pitch peak"].append(pitch.max() - around if len(pitch) else np.nan)
        features["pitch range"].append(np.ptp(pitch) if len(pitch) > 2 else np.nan)
        features["length"].append(np.log(max(lengths[i], 0.01) / max(0.04, base + slope * letters[i])))
        features["pause after"].append(min(words[i + 1].start - w.end, 1.0) if i + 1 < len(words) else 0.5)
        features["pause before"].append(min(w.start - words[i - 1].end, 1.0) if i else 0.5)

    # Speakers start a sentence high and loud and drift down, so measure against the sentence's trend.
    sentence = np.cumsum([0] + [w.text.rstrip("\"')”’")[-1:] in SENTENCE_ENDS for w in words[:-1]])
    for name in ("loudness", "pitch peak", "pitch range", "length"):
        values = np.array(features[name], float)
        for s in np.unique(sentence):
            mask = (sentence == s) & ~np.isnan(values)
            if mask.sum() >= 3:
                x = np.flatnonzero(mask)
                values[mask] -= np.polyval(np.polyfit(x, values[mask], 1), x)
        features[name] = values
    score = sum(_standard(values) for values in features.values())
    ranks = np.argsort(np.argsort(score, kind="stable"), kind="stable")
    return [round(float(r) / (len(words) - 1), 2) for r in ranks]


def _standard(values) -> np.ndarray:
    values = np.asarray(values, float)
    if np.all(np.isnan(values)):
        return np.zeros(len(values))
    return np.nan_to_num((values - np.nanmean(values)) / (np.nanstd(values) + 1e-9))


def _frames(samples: np.ndarray, width: int) -> np.ndarray:
    hop = int(RATE * HOP)
    count = max(0, 1 + (len(samples) - width) // hop)
    return samples[np.arange(width)[None, :] + hop * np.arange(count)[:, None]]


def _loudness(samples: np.ndarray) -> np.ndarray:
    """Decibels per frame."""
    return 10 * np.log10(np.mean(_frames(samples, int(RATE * 0.03)) ** 2, axis=1) + 1e-10)


def _pitch(samples: np.ndarray, low=70, high=400, threshold=0.15) -> np.ndarray:
    """Pitch in hertz per frame by YIN, NaN where there's no voice."""
    width = int(RATE * 0.04)
    frames = _frames(samples, width)
    frames = frames - frames.mean(axis=1, keepdims=True)
    longest = int(RATE / low)
    spectrum = np.fft.rfft(frames, 2 * width)
    correlation = np.fft.irfft(spectrum * np.conj(spectrum), 2 * width)[:, : longest + 1]
    energy = np.cumsum(frames[:, ::-1] ** 2, axis=1)[:, ::-1]
    shifted = np.zeros_like(correlation)
    reach = min(longest + 1, width - 1)
    shifted[:, :reach] = energy[:, 1 : reach + 1]
    difference = energy[:, :1] + shifted - 2 * correlation
    difference[:, 0] = 0
    mean = np.cumsum(difference[:, 1:], axis=1) / np.arange(1, difference.shape[1])
    normal = np.ones_like(difference)
    normal[:, 1:] = difference[:, 1:] / (mean + 1e-10)
    shortest = int(RATE / high)
    out = np.full(len(frames), np.nan)
    for i, row in enumerate(normal):
        below = np.flatnonzero(row[shortest:] < threshold)
        if len(below):
            lag = below[0] + shortest
            while lag + 1 < len(row) and row[lag + 1] < row[lag]:
                lag += 1
            out[i] = RATE / lag
    return out
