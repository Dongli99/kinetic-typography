# Using kinetic: a guide for AI agents

`kinetic` turns a voiceover into a kinetic typography video. The tool handles timing, layout and rendering, which it does reliably. You handle meaning, which it can only guess at. Decisions you can change live in a JSON plan file.

## Workflow

```bash
kinetic plan --audio talk.mp3 --out talk.plan.json --json
# Edit talk.plan.json to suit the content.
kinetic frame --plan talk.plan.json --at 12.5 --out check.png --json
kinetic render --plan talk.plan.json --out talk.mp4 --json
```

`kinetic make --audio talk.mp3 --out talk.mp4 --json` does plan and render in one step, for when the automatic choices are good enough.

## Audio alone, or with a script

Audio alone is the default: the tool works out the words, then times them. Add `--script talk.txt` when you have the exact words and either the audio is unclear or the words must be exact, such as names and invented spellings. The script's words are then what's shown, and nothing is transcribed.

From audio alone, words can be misheard, and every wrong word shows on screen. Read the words in the plan against what you know of the content, and correct `text` directly: the timing stays right if the mistake is only spelling. If many words are wrong, supply a script.

## Reading results

With `--json`, stdout carries exactly one JSON object and progress goes to stderr. Exit code 0 means success and 1 means failure.

```json
{"ok": true, "plan": "talk.plan.json", "words_from": "audio", "duration": 60.5, "phrases": 50, "confidence": -0.06, "doubtful": []}
{"ok": false, "error": "phrases[3].emphasis: expected null or a word index below 3, got 5"}
```

- `words_from` is `audio` or `script`.
- `doubtful` lists words to check. With a script, they were probably reworded or unspoken. From audio alone, they may be misheard, or the tool may have added a word nobody said, such as `billion` where it wrote `$2.8 billion` for a spoken "two point eight billion". An empty list doesn't prove the words are right.
- `confidence` runs from 0 (perfect) downward. Correct words normally score above -0.5. Below -2.5, the tool refuses because the words don't match the audio.

## The plan file

```json
{
 "version": 1,
 "audio": "talk.mp3",
 "duration": 60.5,
 "style": {},
 "phrases": [
  {
   "emphasis": 1,
   "words": [
    {"text": "the", "start": 0.24, "end": 0.40},
    {"text": "vault?", "start": 0.41, "end": 0.88}
   ]
  }
 ]
}
```

| Field | Meaning |
|---|---|
| `audio` | Voiceover path, relative to the plan file |
| `duration` | Video length in seconds |
| `style` | Overrides of the settings below |
| `phrases` | What's on screen together, in order. Each phrase replaces the last. |
| `phrases[].emphasis` | Index of the word to enlarge and color, or `null` for none |
| `words[].text` | Text to show. It's shown in capitals, without edge punctuation except `?` and `!`. It may contain spaces, as in `$6.3 billion`, and then appears as one unit. |
| `words[].start`, `end` | When the word is spoken, in seconds. A word appears at `start`. |

## What to edit

Do these in order of value:

1. **Emphasis.** The tool's choice is a guess based on numbers, position, repetition and length. Set it to the word that carries the point.
2. **Phrase breaks.** Move words between phrases so each one reads as a unit of meaning. Keep `start` and `end` as they are.
3. **On-screen text.** Change `text` to shorten or restyle, such as `six point three billion` to `$6.3B`. Merge words by keeping the first word's `start` and the last word's `end`.
4. **Style.** See below.

Don't change the timing unless you've found it wrong. It comes from the audio and is usually accurate to a few hundredths of a second.

## Style settings

Colors are `[red, green, blue]` from 0 to 255. These are the defaults:

| Setting | Default | Meaning |
|---|---|---|
| `width`, `height` | 1080, 1080 | Canvas size in pixels |
| `fps` | 30 | Frames per second |
| `margin` | 90 | Empty border in pixels |
| `max_font_size` | 190 | Largest base text size |
| `emphasis_scale` | 1.35 | How much larger the emphasized word is |
| `line_gap` | 0.28 | Space between lines, relative to text size |
| `background` | [17, 17, 17] | Background color |
| `foreground` | [245, 245, 240] | Text color |
| `accent` | [255, 210, 31] | Emphasized word color |
| `lead_in` | 0 | Seconds a word starts appearing early |
| `pop_duration` | 0.18 | Seconds a word takes to settle |
| `fade_out` | 0.08 | Seconds a phrase takes to fade |
| `hold` | 0.5 | Seconds a phrase stays after its last word |

## Writing scripts

- English only, with or without a script. Non-English text won't align.
- Write what's spoken. Digits are fine (`$6.3 billion`, `2026`, `20%`, `3rd`) because they're converted to how they sound.
- Other than that, the script doesn't need to be perfect. Ad-libs in the audio are skipped, and reworded or unspoken script words are reported in `doubtful`.
- Sentence ends always break a phrase. Commas, colons and dashes encourage one.

## Checking your work

Run `kinetic frame` on a few moments before a full render. It's quick, and you can look at the PNG. Rendering a 60-second video takes a few seconds.
