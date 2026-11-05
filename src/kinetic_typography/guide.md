# Using kinetic: a guide for AI agents

`kinetic` turns a voiceover into a kinetic typography video. The tool handles timing, layout and rendering, which it does reliably. You handle meaning, which it can only guess at. Decisions you can change live in a JSON plan file.

## Workflow

```bash
kinetic plan --audio talk.mp3 --out talk.plan.json --json
# Edit talk.plan.json to suit the content.
kinetic check --plan talk.plan.json --json
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
{"ok": true, "plan": "talk.plan.json", "words_from": "audio", "duration": 60.5, "groups": 50, "confidence": -0.06, "doubtful": []}
{"ok": false, "error": "sections[0].groups[3].text: 'lift' doesn't match the next spoken word, 'left' (words[12] at 4.10s)"}
```

- `words_from` is `audio` or `script`.
- `doubtful` lists words to check. With a script, they were probably reworded or unspoken. From audio alone, they may be misheard, or the tool may have added a word nobody said, such as `billion` where it wrote `$2.8 billion` for a spoken "two point eight billion". An empty list doesn't prove the words are right.
- `confidence` runs from 0 (perfect) downward. Correct words normally score above -0.5. Below -2.5, the tool refuses because the words don't match the audio.

Every command that reads a plan checks all of it first. A mistake is an error naming the field to fix, never a part of the plan that's quietly skipped.

## The plan file

```json
{
 "version": 2,
 "audio": "talk.mp3",
 "duration": 60.5,
 "emphasis": {"source": "meaning"},
 "look": {"font": "EB Garamond", "upper": false, "emphasis": {"hero": {"size": 2, "bold": true}, "weight": {"bold": true}, "tone": {"italic": true}}},
 "defaults": {"place": "fit", "arrive": "pop", "retire": {"type": "fade", "after": 1, "dur": 0.08, "hold": 0.42}, "camera": "still"},
 "sections": [
  {"groups": [
   {"text": "**$6.3 billion** left"},
   {"text": "the world's / *biggest* crypto exchange", "retire": "drop"}
  ]}
 ],
 "words": [
  {"text": "$6.3 billion", "start": 0.24, "end": 1.10},
  {"text": "left", "start": 1.12, "end": 1.40}
 ]
}
```

| Field | Meaning |
|---|---|
| `audio` | Voiceover path, relative to the plan file |
| `duration` | Video length in seconds |
| `words` | The record: each spoken word and when, in seconds. Edit `text` only to fix a misheard word, and times only if they're wrong |
| `sections` | The direction: groups of the spoken words, in order. A new section clears the screen |
| `groups` | What's shown together. Every spoken word belongs to exactly one group, in order |
| `emphasis` | Where emphasis comes from. `{"source": "meaning"}`, from the markup, is the only option so far |
| `look` | How it appears. See below |
| `defaults` | The effect for each slot: `place`, `arrive`, `retire` and `camera`. See the effects reference at the end |

### A group

| Field | Meaning |
|---|---|
| `text` | The words as shown, with markup. It must match the spoken words in order, ignoring case and punctuation |
| `align` | `left`, `center` or `right`, for its lines. Default: the look's `align` |
| `at` | Hints for the place effect, such as `{"side": "right", "turn": -90}` with `canvas` |
| `camera` | Hints for the camera effect, such as `{"zoom": 1.3}` with `follow` |
| `arrive`, `retire` | This group's own effect, instead of the default, as a name or `{"type": name, ...parameters}` |

### Markup in `text`

| Write | For |
|---|---|
| `**word**` | `hero`: the single standout word of a paragraph, biggest and boldest |
| `*word*` | `weight`: what a listener must remember |
| `_word_` | `tone`: irony, softness or contrast. A different kind of emphasis, not a weaker one |
| `word^1.5` | Size, relative to the rest of the group. It combines with a level |
| `/` | A line break, as its own word. Without one, the place effect chooses the lines |

A mark can cover several words, as in `_not your keys_`. A spoken word written with a space, like `$6.3 billion`, takes markup and size as one word: `*$6.3 billion*^2`. Marking only part of it is an error. Text may differ from the spoken word in punctuation and case, and punctuation on its own, like `—`, joins the word next to it.

Mark sparingly. Emphasis works when it's rare and uneven: often a quarter of the words or fewer, with `hero` at most once a paragraph. Short words of contrast and negation, like *not*, *no* and *but*, are easy to miss.

## Look settings

Colors are `[red, green, blue]` from 0 to 255. These are the defaults:

| Setting | Default | Meaning |
|---|---|---|
| `width`, `height` | 1080, 1080 | Frame size in pixels |
| `fps` | 30 | Frames per second |
| `font` | `Archivo Black` | `Archivo Black`, one heavy weight, or `EB Garamond`, a serif with bold and italic |
| `upper` | true | Show text in capitals |
| `align` | `center` | How a group's lines line up |
| `size` | 64 | Text size in pixels, for place effects that don't size text themselves |
| `line_gap` | 0.28 | Space between lines' ink, relative to text size |
| `background` | [17, 17, 17] | Background color |
| `ink` | [245, 245, 240] | Text color |
| `emphasis` | See below | How each level looks |

`emphasis` sets `hero`, `weight` and `tone`, each with any of `size` (relative, default 1), `bold`, `italic` and `color` (default: `ink`). A level you set replaces its default entirely. The defaults suit Archivo Black, which has no bold or italic: `hero` is 1.7 times the size in yellow, `weight` 1.35 times in yellow, and `tone` gray. A level that looks like plain text, or asks for a style the font lacks, is an error.

## What to edit

Do these in order of value:

1. **Emphasis.** The draft marks one word per group by rules about numbers, position, repetition and length, so it marks too much and misses meaning. Mark what carries the point.
2. **Groups.** Move words between groups so each reads as a unit of meaning. Start a new section where the subject changes.
3. **Look and motion.** For example, `EB Garamond` with bold and italic levels, `canvas` placement with `follow`, and per-group `at` hints for turns.

Don't change the timing unless you've found it wrong. It comes from the audio and is usually accurate to a few hundredths of a second.

## Writing scripts

- English only, with or without a script. Non-English text won't align.
- Write what's spoken. Digits are fine (`$6.3 billion`, `2026`, `20%`, `3rd`) because they're converted to how they sound.
- Other than that, the script doesn't need to be perfect. Ad-libs in the audio are skipped, and reworded or unspoken script words are reported in `doubtful`.
- Sentence ends always break a group in the draft. Commas, colons and dashes encourage one.

## Checking your work

Run `kinetic check` after every edit. It takes about a second and reads the plan the way a viewer would see it:

```json
{"ok": true, "clean": false,
 "overlaps": [{"group": "sections[1].groups[2]", "word": "minutes", "at": 18.2, "lands_on": "sections[1].groups[0]", "on_word": "WIRED"}],
 "clipped": [{"group": "sections[2].groups[1]", "word": "vanished", "at": 16.14, "edge": "bottom", "by": 454}],
 "brief": [{"group": "sections[0].groups[0]", "word": "left", "at": 2.02, "shown": 0.1}],
 "styles": {"words": 157, "hero": 1, "weight": 29, "tone": 23, "styled": [{"group": "sections[0].groups[0]", "word": "$6.3 billion", "at": 0.24, "level": "hero", "size": 2.4, "bold": true, "italic": false, "color": [30, 24, 20]}]}}
```

| Finding | Means | Usual fix |
|---|---|---|
| `overlaps` | A word lands where a word of an earlier group is still showing. One per pair of groups | A different `side`, more `gap`, or an earlier exit for the older group with its `retire` |
| `clipped` | A word is past the frame edge 0.25 seconds after it starts, by `by` pixels | With `follow`, frame fewer groups with `with`, lower `zoom`, or `cut`. With `canvas`, a different `side` or `turn` |
| `brief` | A word is readable for `shown` seconds, under 0.3, before its group leaves | Move it into the next group, or give its group a later exit |
| `styles` | Every word with a level or a size, as it was applied, and the count at each level | Compare it with what you meant to mark |

`clean` is true when there are no overlaps, clipped words or brief words. The check can't judge taste, so look at a few frames with `kinetic frame` too, especially where groups turn or the camera travels. Rendering a 60-second video takes a few seconds.
