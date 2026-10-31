"""Work out what was said, for when no script is given.

Whisper supplies only the words and punctuation. Their timing still comes from forced
alignment, because Whisper's word times are far less accurate (see docs/decisions.md).
"""

import sys
from dataclasses import dataclass

import numpy as np

from .align import cache_dir

MODEL = "small.en"
MODEL_REVISION = "d1d751a5f8271d482d14ca55d9e2deeebbae577f"

# Measured: on one narration, clean and with noise, this flagged the wrong words
# "trader" and "respect" and no right ones. It missed "fits" for "sits" and "copy" for "copied".
WORD_PROBABILITY_FLOOR = 0.5


@dataclass(frozen=True)
class Transcript:
    text: str
    unsure: list[str]  # words the recognizer may have misheard


def transcribe(samples: np.ndarray) -> Transcript:
    from faster_whisper import WhisperModel
    from faster_whisper.utils import download_model

    if not (cache_dir() / "recognizer").is_dir():
        print("Downloading the 484 MB recognizer model (once only)...", file=sys.stderr)
    path = download_model(MODEL, cache_dir=str(cache_dir() / "recognizer"), revision=MODEL_REVISION)
    model = WhisperModel(path, device="cpu", compute_type="int8")

    # Without the voice filter, Whisper hears words in silence.
    segments, _ = model.transcribe(samples, language="en", word_timestamps=True, vad_filter=True)
    segments = list(segments)
    return Transcript(
        " ".join(segment.text.strip() for segment in segments),
        [word.word.strip() for segment in segments for word in segment.words if word.probability < WORD_PROBABILITY_FLOOR],
    )
