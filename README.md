# Kinetic Typography

> **Early version:** tested on one recording so far.

Turn a voiceover into a kinetic typography video. Each word pops onto the screen as it is spoken.

- **Input:** an audio file (`.mp3` or `.wav`) in English, plus an optional script for when the audio is unclear
- **Output:** a 1080x1080 `.mp4` with the animated words and your audio
- **Made for agents too:** every creative decision is in a JSON plan file that you or your AI agent can edit

## Install

You need Python 3.11 or newer and [ffmpeg](https://ffmpeg.org/download.html) (on macOS: `brew install ffmpeg`).

```bash
pipx install git+https://github.com/Dongli99/kinetic-typography
```

No pipx? Use a virtual environment:

```bash
python3 -m venv .venv
.venv/bin/pip install git+https://github.com/Dongli99/kinetic-typography
```

## Use

```bash
kinetic make --audio talk.mp3 --out talk.mp4
```

The first run downloads two speech models, 860 MB in total. After that, everything runs offline on your computer.

Words worked out from audio can be misheard, and you'll be told about ones the tool isn't sure of. If the audio is unclear or the words must be exact, add a script. It also skips the larger model's work:

```bash
kinetic make --audio talk.mp3 --script talk.txt --out talk.mp4
```

### Adjust the result

To change the emphasis, the groups of words, the font or the motion, make a plan file first. You mark emphasis in each group's text, like `**hero**`, `*weight*` and `_tone_`:

```bash
kinetic plan --audio talk.mp3 --out talk.plan.json
# Edit talk.plan.json
kinetic check --plan talk.plan.json                              # overlapping, clipped or too-brief words
kinetic frame --plan talk.plan.json --at 12.5 --out check.png    # preview one moment
kinetic render --plan talk.plan.json --out talk.mp4
```

### Use it with an AI agent

Tell your agent to run `kinetic guide`. It prints the workflow, the plan format and how to read results. Add `--json` to any command for one machine-readable result on stdout.

## Writing a script

With a script, the video shows its words, so spelling and names stay as you wrote them.

- **Digits are fine.** `$6.3 billion`, `2026` and `20%` are matched to how they sound. Spoken-out numbers like "six point three billion dollars" appear as `$6.3 BILLION`.
- **Differences from the recording are fine.** Ad-libs in the audio are skipped, and you'll be told about script words the audio doesn't seem to contain. A script that doesn't match at all is refused.
- **Punctuation shapes the phrases.** Sentence ends always start a new phrase, and commas, colons and dashes encourage one.

## How it works

```
audio ─▶ words (or your script) ─▶ timing ─▶ groups ─▶ plan file ─▶ effects ─▶ MP4
```

Whisper works out the words, unless you give a script. Timing then uses forced alignment: because the words are known, a second speech model only has to find when each letter sounds. Why each technology was chosen is in [docs/decisions.md](docs/decisions.md).

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
tools/install-hooks.sh
.venv/bin/python -m pytest
```

Contributing, by hand or with an agent? Start with [CLAUDE.md](CLAUDE.md).

## Roadmap

- Contact sheets and quick previews
- Motion blur, a paper look and presets
- A better first draft without an agent
- Custom fonts

## License

The code is under the [MIT License](LICENSE). The bundled fonts, [Archivo Black](src/kinetic_typography/fonts/ArchivoBlack-OFL.txt) and [EB Garamond](src/kinetic_typography/fonts/EBGaramond-OFL.txt), are under the SIL Open Font License. The speech models are downloaded separately: [wav2vec2-base-960h](https://huggingface.co/facebook/wav2vec2-base-960h) is under Apache-2.0, and [faster-whisper-small.en](https://huggingface.co/Systran/faster-whisper-small.en) is under MIT.
