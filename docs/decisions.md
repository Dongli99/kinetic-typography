# Technology decisions

Each entry records what was chosen, the evidence and what would change the decision. Numbers come from one 60-second narration with 22 measurable pauses, plus a synthetic test clip, so they're strong enough to reject a clearly worse option but not to rank close ones.

## Timing: forced alignment with wav2vec2 on ONNX

**Chosen:** `wav2vec2-base-960h` (Apache-2.0) through `onnxruntime`, with a small Viterbi aligner in `align.py`.

Error at speech onset after each pause, 2026-10-30:

| Candidate | Median | 90th percentile | Worst | Notes |
|---|---|---|---|---|
| Whisper `base.en`, matched to script | 0.040s | 0.212s | 0.739s | The first version |
| Whisper `small.en`, matched to script | 0.029s | 0.170s | 0.699s | |
| Whisper `large-v3-turbo`, matched to script | 0.231s | 0.350s | 0.444s | Consistently early |
| wav2vec2 through PyTorch | 0.011s | 0.040s | 0.105s | 800 MB install |
| **wav2vec2 through ONNX (this)** | **0.013s** | **0.049s** | **0.105s** | 169 MB install, plus a 378 MB model |

**Why it works:** the script is already known, so recognizing the speech first throws information away. Whisper's word times are also a by-product of its attention, while CTC models tie letters directly to frames.

**Stress results, compared with the same words in a matching script:**

| Script differs by | Words moved over 0.1s | Reported as doubtful |
|---|---|---|
| Digits instead of spoken numbers | 0 (largest move 0.00s) | None |
| Two words reworded | 0 (largest move 0.08s) | Both |
| Two paragraphs of the audio missing | 0 | None |
| One paragraph of the audio missing | 1: "minutes." moved 4.64s, to the same word in the extra speech | None |
| A sentence that isn't spoken | 4 neighbors, by up to 0.36s | 15 of 178 words |

A wrong script scores -2.85 or lower and is refused.

**Known limit:** a script word can snap to the same word in speech the script leaves out, and nothing reports it. The fix is to make the script match the recording, or to correct that word's time in the plan.

**Rejected:**

- **`int8` model:** it's a quarter of the size but took 47.6s against 2.1s for the full model on this machine, with lower confidence.
- **`MMS_FA`:** the weights are CC-BY-NC, which rules out commercial videos.
- **WhisperX:** it requires PyTorch, and at the time of writing doesn't support Python 3.14.
- **Montreal Forced Aligner:** [one study](https://arxiv.org/html/2406.19363v1) found it more accurate than WhisperX and MMS on hand-labeled English, but it needs a conda install. That's too heavy for a default, and it's the option to try if onset accuracy ever becomes a limit.
- **Parakeet:** not measured, because `onnx-asr` didn't recognize the model name I tried. It's a recognizer, so it wouldn't change the reasoning above, but its timing is unknown.

**Revisit if:** adding other languages, since this model is English-only.

## Words from audio: Whisper `small.en`, in front of the aligner

**Chosen:** audio is the only required input. `faster-whisper` with `small.en` (MIT) supplies the words and punctuation, and the aligner above still supplies the timing. A script replaces the recognizer when the audio is unclear or the words must be exact.

Word error against the known script, one 60-second narration on CPU, 2026-10-30. Noise was added to the recording at the stated signal-to-noise ratio. The `small.en` clean figure includes two harmless differences: writing "$2.8 billion" for a spoken "two point eight billion" reads as an extra "dollars". Its one real error was "trader" for "traitor".

| Recognizer | Clean | 10 dB noise | 0 dB noise | Time on clean audio | Model |
|---|---|---|---|---|---|
| wav2vec2, decoded directly | 13.1% | Over 100% | Over 100% | 2.8s | Already installed |
| Whisper `base.en` | 4.2% | 6.0% | 45.2% | 2.9s | Smaller, not measured |
| **Whisper `small.en` (this)** | **1.8%** | **3.6%** | **23.8%** | **8.2s** | **484 MB** |
| Whisper `distil-small.en` | 48.2% | 57.7% | 75.0% | 4.7s | Not measured; it dropped long stretches of speech at default settings |

**Why this one:** a wrong word stays on screen, so accuracy beats speed here, and the extra seconds are per minute of audio.

**Timing is unaffected.** Aligning the `small.en` transcript passed `eval_alignment.py` with the same result as the real script: median 0.013s, 90th percentile 0.049s, worst 0.105s, over 22 pauses.

**Reporting mistakes:** word probability below 0.5 flagged "trader" for "traitor" and "respect" for "suspect", with no right word flagged. It missed "fits" for "sits" and "copy" for "copied" in noise, so an empty list doesn't prove the words are right.

**The voice filter stays on:** without it, Whisper heard "You" in 8 seconds of pure silence.

**Revisit if:** the install weight becomes a problem, or a smaller recognizer gets close on noisy audio. `Parakeet` remains unmeasured.

## Rendering: Skia, piped to ffmpeg

**Chosen:** `skia-python` for frames and an `ffmpeg` subprocess for encoding.

60 seconds of 1080x1080 video renders in about 4 seconds. Frames come from a pure function of the plan and time, so output is repeatable and any moment can be previewed alone with `kinetic frame`.

**Rejected:**

None of these were benchmarked. They were ruled out on what they'd add to the install and the design:

- **Remotion or a headless browser:** richer effects are the appeal, but it brings a browser dependency and a Node toolchain. Its license also requires some companies to pay.
- **Pillow:** lighter, but it places text at whole pixels, so scaling text would jitter.
- **Manim and MoviePy:** built for other jobs.

**Revisit if:** the effects we want need a real shader pipeline beyond what Skia offers, or non-Latin text needs complex shaping. Skia has a shaper, which would be the first thing to try.

## Agent interface: a plan file and a CLI

**Chosen:** an editable JSON plan, a CLI with `--json` results, and `kinetic guide` for documentation that ships with the installed version.

Agents are good at meaning and the tool is good at timing, so the plan file is where they meet. A CLI works with any agent that has a shell, and a plain file is easy to diff and can be reviewed by a person.

**Rejected for now:**

- **MCP server:** it would add a long-running process for what are one-shot commands. It's easy to add later as a thin wrapper over the same functions.
- **LLM inside the tool:** this would need API keys and would make output non-repeatable, when the user's agent is already an LLM.
- **Many CLI flags for creative options:** every option would need to be duplicated in the plan anyway, and flags can't vary by phrase.

## Phrasing: a cost search, not an NLP model

**Chosen:** split each sentence by minimizing a cost over every possible split, using punctuation, measured pauses and word lists.

A parser such as spaCy would add a large dependency to improve a guess that an agent can overrule anyway. The first version's greedy rule was replaced because it couldn't weigh a good break later against a mediocre one now.

**Revisit if:** users who don't use an agent keep hitting bad breaks.

## Language and packaging

**Chosen:** Python 3.11 or newer, installed with pipx from git. Python holds the aligner, renderer bindings and CLI in one language, and needs no build step.

**Revisit if:** render speed becomes a limit. The per-frame code is small and could move to a compiled language without touching the plan format.

## Fonts: Archivo Black and EB Garamond, bundled

**Chosen:** two families ship with the package, both under the SIL Open Font License, so videos look the same on every machine. Archivo Black is the heavy sans for today's look. [EB Garamond](https://github.com/octaviopardo/EBGaramond12), from the Google Fonts repository, is the serif, as variable upright and italic files with weights from 400 to 800, 2026-11-03.

**Why a serif with bold and italic:** emphasis has three levels, and two of them are drawn as weight and slant. Archivo Black has a single weight, so it can only show emphasis by size and color. The prototype used Hoefler Text, which ships only with macOS.

**Evidence:** the prototype's hand direction, set in EB Garamond, kept its look on a contact sheet. No other serif was tried, so this choice isn't ranked against alternatives.

**A trap:** in skia-python, variation arguments built inline as temporaries are quietly ignored, and bold comes out at the regular weight. Building them step by step works. `test_bold_and_italic_are_drawn_differently` fails if bold comes out at the regular width.

**Revisit if:** a reference video needs a heavier black weight than 800, or languages beyond what these fonts cover.

