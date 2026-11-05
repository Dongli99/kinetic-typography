# Kinetic Typography

Turns a voiceover into a kinetic typography video, with an optional script for when the audio is unclear. The goal is a tool that a user's AI agent can drive to make many kinds of video, from the content and its context.

This repo is public. Keep hosts, addresses, credentials and private project names out of every file and commit message.

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"   # setup
tools/install-hooks.sh                                       # once per clone
.venv/bin/python -m pytest                                   # tests, under a second
.venv/bin/python tools/eval_alignment.py AUDIO [SCRIPT]      # timing check on a real recording
.venv/bin/kinetic make --audio AUDIO [--script SCRIPT] --out out.mp4
```

## Architecture

```
audio ─▶ transcribe or script ─▶ align ─▶ phrases ─▶ PLAN FILE ─▶ build ─▶ effects ─▶ scene ─▶ render
         └───────────── automatic first draft ─────┘              └──────────── deterministic ───────┘
```

**The plan file is the contract.** Every creative decision is data in it, and everything after it is a deterministic function of it. Agents supply judgment by editing the plan. They never have to reach into the pipeline.

So a new creative feature is a new plan field that the renderer honors, with a sensible automatic default. It's never a CLI flag. Flags are for where files go and how results are reported.

| File | Job |
|---|---|
| `transcribe.py` | The words, when there's no script. Never their timing. |
| `align.py` | Forced alignment of the words to the audio |
| `spoken.py` | How numbers sound, and how spoken numbers read |
| `phrases.py` | First draft of phrase breaks and emphasis |
| `plan.py` | Plan file format, its markup and validation. Every mistake is a `PlanError` naming the field |
| `scene.py` | The tree of world, groups and words, whose properties change over time through keys |
| `effects.py` | The registry of `place`, `arrive`, `retire` and `camera` effects, which write those keys. It validates choices and hints, and writes the guide's effect reference |
| `build.py` | Groups plus a choice per slot, made into a scene |
| `check.py` | What a viewer would see is wrong: overlaps, clipped and too-brief words. It also reports the styles applied |
| `render.py` | Skia frames at any scale, with motion blur and paper, drawn in parallel and piped to ffmpeg, and contact sheets. It walks the tree and knows no effect by name |
| `guide.md` | What a user's agent reads, via `kinetic guide`, followed by the generated effect reference |

Past technology choices and their evidence are in [docs/decisions.md](docs/decisions.md). Read it before changing the aligner, renderer or dependencies.

The agreed direction for the next stage, partly built, is in [docs/architecture-next.md](docs/architecture-next.md). Read it before changing layout, animation, rendering or the plan format.

## Principles

- **Restraint.** Add a parameter, flag or layer only when adjusting what exists can't do the job. A bug fix should leave the code simpler. If it adds a workaround, look for the root cause.
- **A guess may be wrong; a record may not.** Emphasis and phrase breaks are guesses that an agent can overrule, so don't chase every wrong one with another rule. Timing and a script's words are records, so a wrong one is a bug. Words worked out from audio are a guess that must be reported when doubtful.
- **Prefer a check to a rule.** If something must stay true, try to make it impossible, then detectable by a test or hook. Write it here only if neither works. When a check lands for a rule written here, delete the prose.
- **A passing check counts only if it could have failed.** When adding a check, show it failing once. A check that passes silently also has to prove it saw its subject, the way `eval_alignment.py` fails when it finds too few pauses.
- **Measure on real recordings.** Unit tests use fake model output, so they can't catch model behavior. A change to timing has to pass `eval_alignment.py`, and a single recording's result says nothing about which of two settings is better in general.

## Checks

| Check | Runs | Catches |
|---|---|---|
| `tools/git-hooks/pre-commit` | Every commit | Secrets (gitleaks) and failing tests |
| GitHub Actions | Every push and PR | Failed installs and tests on Linux and macOS |
| `tools/eval_alignment.py` | By hand, for timing changes | Timing regressions on a real recording |
| `test_guide_is_packaged_...` | With the tests | Guide missing a command, plan field, look setting, effect, parameter or hint |
| `test_a_mistake_is_an_error_...` | With the tests | A plan mistake that's skipped instead of reported |
| `test_shared_...` in `test_effects.py` | With the tests, on every registered effect | An effect without docs or defaults, words shown early, moving while spoken or never settling, groups that never leave, a camera losing the words |

## When changing things

- A changed command or plan field also changes `guide.md` and the README, in the same commit.
- A breaking plan format change bumps `PLAN_VERSION`.
- Report results from the actual output: the command, what it printed, and whether anything was skipped.
