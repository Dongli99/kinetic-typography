"""Find when each script word is spoken, by forced alignment.

The script is known, so nothing is transcribed. An acoustic model (wav2vec2) estimates
which letter is sounding in each 20 ms frame, and a Viterbi search finds the best path
through the script's letters. Optional "gap" states between words absorb silence and
speech the script doesn't contain, such as ad-libs.
"""

import hashlib
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .model import Word
from .spoken import spoken_words

SAMPLE_RATE = 16000
SAMPLES_PER_FRAME = 320
CHUNK_SECONDS = 30
CHUNK_OVERLAP_SECONDS = 1

MODEL_URL = (
    "https://huggingface.co/onnx-community/wav2vec2-base-960h-ONNX/resolve/"
    "729c1a6730fb549c20a1c73a3d3f96f11020225e/onnx/model.onnx"
)
MODEL_SHA256 = "00b7cc69516c1ab63c429e63a2b543e4d42bb77441ec5b98ee935de175b00de1"

# The model's output classes, in order.
VOCAB = ["<pad>", "<s>", "</s>", "<unk>", "|", *"ETAONIHSRDLUMWCFGYPBVK'XJQZ"]
LETTER_IDS = {letter.lower(): index for index, letter in enumerate(VOCAB) if letter.isalpha() or letter == "'"}
PAD_ID, WORD_BREAK_ID = 0, 4
GAP = -1

# Log-probability cost per frame for treating speech as not being in the script.
GAP_PENALTY = 2.0
# Cost per frame for silence inside a word. Without it, a word can claim the end of the
# word before ("vaulT / The") and then wait through the whole pause.
SILENCE_IN_WORD_PENALTY = 0.1
# Measured: wrong scripts score -2.85 or lower; right ones, even with a sentence unspoken, -1.40 or higher.
WORD_CONFIDENCE_FLOOR = -4.0
SCRIPT_CONFIDENCE_FLOOR = -2.5


@dataclass(frozen=True)
class Alignment:
    words: list[Word]
    duration: float
    confidence: float  # mean log-probability of the matched letters; 0 is perfect
    doubtful: list[str]  # script words the audio gave little evidence for


def tokenize_script(script: str) -> list[str]:
    """Split a script into words, treating dashes between words as separators."""
    spaced = re.sub(r"\s+-\s+|\s*(?:—|–|--)\s*", "— ", script)
    return [token for token in spaced.split() if re.search(r"[a-zA-Z0-9]", token)]


def decode_audio(audio_path: str) -> np.ndarray:
    """Decode to the model's input format: 16 kHz mono float samples."""
    command = [
        "ffmpeg", "-loglevel", "error", "-i", audio_path, "-map", "0:a:0",
        "-f", "f32le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-",
    ]  # fmt: skip
    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0:
        message = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"ffmpeg could not read {audio_path}: {message}")
    samples = np.frombuffer(result.stdout, dtype=np.float32)
    if samples.size == 0:
        raise ValueError(f"No audio found in {audio_path}")
    return samples


def align_script(tokens: list[str], samples: np.ndarray) -> Alignment:
    return align_to_log_probs(tokens, letter_log_probs(samples), len(samples) / SAMPLE_RATE)


def align_to_log_probs(tokens: list[str], log_probs: np.ndarray, duration: float) -> Alignment:
    letters, owners = _script_letters(tokens)
    if not letters:
        raise ValueError("The script has no words that can be spoken.")
    if len(letters) > len(log_probs):
        raise ValueError(
            f"The script has more letters than the audio has time for ({len(letters)} letters, "
            f"{duration:.1f}s). Does it match the recording?"
        )

    labels, state_owner = _build_states(letters, owners)
    path = _viterbi(log_probs, labels)
    spans, scores = _word_spans(path, labels, state_owner, log_probs)

    seconds_per_frame = duration / len(log_probs)
    words = []
    doubtful = []
    previous_end = 0.0
    for index, token in enumerate(tokens):
        if index in spans:
            first, last = spans[index]
            start, end = first * seconds_per_frame, (last + 1) * seconds_per_frame
            if np.mean(scores[index]) < WORD_CONFIDENCE_FLOOR:
                doubtful.append(token)
        else:
            start, end = previous_end, previous_end  # nothing speakable, such as a lone symbol
        words.append(Word(token, start, end))
        previous_end = end

    all_scores = [score for word_scores in scores.values() for score in word_scores]
    confidence = float(np.mean(all_scores))
    if confidence < SCRIPT_CONFIDENCE_FLOOR:
        raise ValueError(f"The script doesn't match the audio (confidence {confidence:.2f}). Is it the right script?")
    return Alignment(words, duration, confidence, doubtful)


def letter_log_probs(samples: np.ndarray) -> np.ndarray:
    """Run the acoustic model over the audio and return frames x classes log-probabilities."""
    import onnxruntime

    options = onnxruntime.SessionOptions()
    options.log_severity_level = 3
    session = onnxruntime.InferenceSession(str(_model_path()), options, providers=["CPUExecutionProvider"])

    # Long audio is split into overlapping chunks, keeping each chunk's middle.
    chunk = CHUNK_SECONDS * SAMPLE_RATE
    overlap = CHUNK_OVERLAP_SECONDS * SAMPLE_RATE
    frame_overlap = overlap // SAMPLES_PER_FRAME
    pieces = []
    start = 0
    while True:
        piece = samples[start : start + chunk]
        normalized = (piece - piece.mean()) / (piece.std() + 1e-7)
        logits = session.run(None, {"input_values": normalized[np.newaxis, :]})[0][0]
        is_last = start + chunk >= len(samples)
        pieces.append(logits[frame_overlap if start else 0 : None if is_last else -frame_overlap])
        if is_last:
            break
        start += chunk - 2 * overlap
    logits = np.concatenate(pieces)
    shifted = logits - logits.max(axis=1, keepdims=True)
    return shifted - np.logaddexp.reduce(shifted, axis=1, keepdims=True)


def _script_letters(tokens: list[str]) -> tuple[list[int], list[tuple[int, int]]]:
    """Return letter ids and, for each letter, which (token, spoken word) it belongs to."""
    letters, owners = [], []
    position = 0
    for token_index, words in enumerate(spoken_words(tokens)):
        for word in words:
            for letter in word:
                if letter in LETTER_IDS:
                    letters.append(LETTER_IDS[letter])
                    owners.append((token_index, position))
            position += 1
    return letters, owners


def _build_states(letters: list[int], owners: list[tuple[int, int]]) -> tuple[np.ndarray, list[int]]:
    """Lay out the path: a gap, then each word's letters followed by another gap."""
    labels, state_owner = [GAP], [-1]
    for index, (letter, owner) in enumerate(zip(letters, owners)):
        labels.append(letter)
        state_owner.append(owner[0])
        if index + 1 == len(letters) or owners[index + 1][1] != owner[1]:
            labels.append(GAP)
            state_owner.append(-1)
    return np.array(labels), state_owner


# Moves recorded for backtracking.
_STAY_SILENT, _STAY_SOUNDING, _FROM_PREVIOUS, _SKIP_GAP = 0, 1, 2, 3


def _viterbi(log_probs: np.ndarray, labels: np.ndarray) -> list[tuple[int, int]]:
    """Return the best path as (state, move) per frame."""
    frames, states = len(log_probs), len(labels)
    is_gap = labels == GAP
    is_letter = ~is_gap
    # A letter directly after a gap may also be entered from the letter before that gap.
    can_skip = np.zeros(states, dtype=bool)
    can_skip[2:] = is_letter[2:] & is_gap[1:-1] & is_letter[:-2]
    lookup = np.where(is_gap, 0, labels)

    silence = np.maximum(log_probs[:, PAD_ID], log_probs[:, WORD_BREAK_ID])
    gap_score = np.maximum(silence, log_probs.max(axis=1) - GAP_PENALTY)

    best = np.full(states, -np.inf)
    best[0] = gap_score[0]
    if states > 1:
        best[1] = log_probs[0, labels[1]]
    moves = np.zeros((frames, states), dtype=np.uint8)
    moves[0, 1:] = _FROM_PREVIOUS

    for frame in range(1, frames):
        sounding = log_probs[frame, lookup]
        stay_silent = best + np.where(is_gap, gap_score[frame], silence[frame] - SILENCE_IN_WORD_PENALTY)
        stay_sounding = np.where(is_letter, best + sounding, -np.inf)

        previous = np.concatenate(([-np.inf], best[:-1]))
        enter = previous + np.where(is_gap, gap_score[frame], sounding)
        before_gap = np.concatenate(([-np.inf, -np.inf], best[:-2]))
        skip = np.where(can_skip, before_gap + sounding, -np.inf)

        options = np.stack((stay_silent, stay_sounding, enter, skip))
        moves[frame] = options.argmax(axis=0)
        best = options.max(axis=0)

    last_letter = states - 2
    state = states - 1 if best[states - 1] >= best[last_letter] else last_letter
    path = []
    for frame in range(frames - 1, -1, -1):
        move = int(moves[frame, state])
        path.append((state, move))
        if frame:
            state -= {_STAY_SILENT: 0, _STAY_SOUNDING: 0, _FROM_PREVIOUS: 1, _SKIP_GAP: 2}[move]
    path.reverse()
    return path


def _word_spans(path, labels, state_owner, log_probs):
    """Turn the path into each token's first and last sounding frame and letter scores."""
    spans: dict[int, list[int]] = {}
    scores: dict[int, list[float]] = {}
    for frame, (state, move) in enumerate(path):
        if labels[state] == GAP or move == _STAY_SILENT:
            continue
        owner = state_owner[state]
        span = spans.setdefault(owner, [frame, frame])
        span[1] = frame
        if move != _STAY_SOUNDING:
            scores.setdefault(owner, []).append(float(log_probs[frame, labels[state]]))
    return spans, scores


def cache_dir() -> Path:
    return Path(os.environ.get("KINETIC_CACHE", Path.home() / ".cache" / "kinetic-typography"))


def _model_path() -> Path:
    cache = cache_dir()
    path = cache / "wav2vec2-base-960h.onnx"
    if path.is_file():
        return path

    print(f"Downloading the 378 MB speech model to {path} (once only)...", file=sys.stderr)
    cache.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with tempfile.NamedTemporaryFile(dir=cache, delete=False) as partial:
        try:
            with urllib.request.urlopen(MODEL_URL) as response:
                while block := response.read(1 << 20):
                    digest.update(block)
                    partial.write(block)
            partial.close()
            if digest.hexdigest() != MODEL_SHA256:
                raise RuntimeError(f"The downloaded speech model failed its checksum: {MODEL_URL}")
            os.replace(partial.name, path)
        except BaseException:
            Path(partial.name).unlink(missing_ok=True)
            raise
    return path
