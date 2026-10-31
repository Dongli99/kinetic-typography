#!/usr/bin/env python3
"""Check timing on a real recording, using the audio's own silences as the reference.

Every pause in the audio has a measurable end, and the next script word should start
there. Comparing the two needs no hand labels, so any audio and script pair works.

This is a regression gate, not a way to pick between settings: thresholds tuned against
one recording would only describe that recording.

    tools/eval_alignment.py audio.mp3 script.txt
    tools/eval_alignment.py audio.mp3                           # words from the audio itself
    tools/eval_alignment.py audio.mp3 script.txt --shift 0.2    # must fail: proves the gate can
"""

import argparse
import re
import subprocess
import sys

import numpy as np

from kinetic_typography.align import align_script, decode_audio, tokenize_script
from kinetic_typography.transcribe import transcribe

MAX_MEDIAN_ERROR = 0.03
MAX_P90_ERROR = 0.08
MAX_WORST_ERROR = 0.15
MIN_BOUNDARIES = 5


def speech_resumes(audio_path: str) -> list[tuple[float, float]]:
    command = ["ffmpeg", "-hide_banner", "-i", audio_path, "-af", "silencedetect=n=-35dB:d=0.25", "-f", "null", "-"]
    log = subprocess.run(command, capture_output=True, text=True).stderr
    starts = [float(value) for value in re.findall(r"silence_start: ([\d.]+)", log)]
    ends = [float(value) for value in re.findall(r"silence_end: ([\d.]+)", log)]
    return list(zip(starts, ends))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("audio")
    parser.add_argument("script", nargs="?")
    parser.add_argument("--shift", type=float, default=0.0, help="move all word times, to prove the gate can fail")
    args = parser.parse_args()

    samples = decode_audio(args.audio)
    text = open(args.script, encoding="utf-8").read() if args.script else transcribe(samples).text
    alignment = align_script(tokenize_script(text), samples)

    errors = []
    for silence_start, silence_end in speech_resumes(args.audio):
        middle = (silence_start + silence_end) / 2
        following = [word for word in alignment.words if (word.start + word.end) / 2 >= middle]
        if following:
            errors.append((following[0].start + args.shift - silence_end, following[0].text, silence_end))

    if len(errors) < MIN_BOUNDARIES:
        print(f"FAIL: only {len(errors)} pauses found, too few to judge. A pass here would mean nothing.")
        return 1

    sizes = np.abs([error for error, _, _ in errors])
    median, p90, worst = float(np.median(sizes)), float(np.percentile(sizes, 90)), float(sizes.max())
    print(f"{len(errors)} pauses · confidence {alignment.confidence:.2f} · doubtful {alignment.doubtful}")
    print(f"error: median {median:.3f}s (max {MAX_MEDIAN_ERROR}) · p90 {p90:.3f}s (max {MAX_P90_ERROR}) · worst {worst:.3f}s (max {MAX_WORST_ERROR})")
    for error, text, at in sorted(errors, key=lambda row: -abs(row[0]))[:3]:
        print(f"  {error:+.3f}s  {text!r} at {at:.2f}s")

    if median > MAX_MEDIAN_ERROR or p90 > MAX_P90_ERROR or worst > MAX_WORST_ERROR:
        print("FAIL")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
