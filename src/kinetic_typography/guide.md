# Using kinetic: a guide for AI agents

`kinetic` turns a voiceover into a kinetic typography video. The tool handles timing, layout and rendering, which it does reliably. You handle meaning, which it can only guess at. Decisions you can change live in a JSON plan file.

## Workflow

```bash
kinetic plan --audio talk.mp3 --out talk.plan.json --json
# Edit talk.plan.json to suit the content.
kinetic check --plan talk.plan.json --json
kinetic preview --plan talk.plan.json --out sheet.png --json
kinetic frame --plan talk.plan.json --at 12.5 --out check.png --json
kinetic render --plan talk.plan.json --out talk.mp4 --json
```

`kinetic make --audio talk.mp3 --out talk.mp4 --json` does plan and render in one step, for when the automatic choices are good enough.

## The draft

`kinetic plan` writes a complete first draft, which `kinetic check` passes:

- **Sections** start at a pause of 0.7 seconds or more between sentences, once a section has 12 words.
- **Groups** are clauses of up to 8 words, set in lines of up to 5, breaking where the punctuation and pauses suggest.
- **Placement** uses the `gap` preset. Each group gets `at` hints from a rule: mostly below the last, every third turned across it, and a turned page with a 400-pixel gap at each section. Where a spot would land on words still showing, or clip, the next one on the group's list is used.
- **Emphasis** comes from rules, and the result says so with `"emphasis_from": "rules"`. Negations like *not* and *never* are `tone`. Numbers, sentence ends, names and long words score toward `weight`, and less if said before, and a section's best-scoring word is its `hero`. It marks about one word in eight. On a reference that a person marked, 63% of its marks were right, and it found 32% of theirs. The rest needs meaning, which is your part.

## Audio alone, or with a script

Audio alone is the default: the tool works out the words, then times them. Add `--script talk.txt` when you have the exact words and either the audio is unclear or the words must be exact, such as names and invented spellings. The script's words are then what's shown, and nothing is transcribed.

From audio alone, words can be misheard, and every wrong word shows on screen. Read the words in the plan against what you know of the content, and correct `text` directly: the timing stays right if the mistake is only spelling. If many words are wrong, supply a script.

## Reading results

With `--json`, stdout carries exactly one JSON object and progress goes to stderr. Exit code 0 means success and 1 means failure.

```json
{"ok": true, "plan": "talk.plan.json", "words_from": "audio", "emphasis_from": "rules", "duration": 60.5, "sections": 6, "groups": 41, "confidence": -0.06, "doubtful": []}
{"ok": false, "error": "sections[0].groups[3].text: 'lift' doesn't match the next spoken word, 'left' (words[12] at 4.10s)"}
```

- `words_from` is `audio` or `script`.
- `emphasis_from` is `rules`: the draft's emphasis is a guess for you to replace.
- `doubtful` lists words to check. With a script, they were probably reworded or unspoken. From audio alone, they may be misheard, or the tool may have added a word nobody said, such as `billion` where it wrote `$2.8 billion` for a spoken "two point eight billion". An empty list doesn't prove the words are right.
- `confidence` runs from 0 (perfect) downward. Correct words normally score above -0.5. Below -2.5, the tool refuses because the words don't match the audio.

Every command that reads a plan checks all of it first. A mistake is an error naming the field to fix, never a part of the plan that's quietly skipped.

## The plan file

```json
{
 "version": 2,
 "preset": "plain",
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
| `preset` | A starting look and effects, which `look` and `defaults` override. See below |
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

## Presets

A preset sets a whole style at once. Your `look` and `defaults` then change only the keys you give. In `look.emphasis` that's level by level, so `{"tone": {"size": 0.8}}` keeps the preset's `hero` and `weight`.

| Preset | Look | Effects |
|---|---|---|
| `plain` | The defaults below: one group at a time, in heavy capitals on a dark background | `fit`, `pop`, `fade`, `still` |
| `gap` | 1920 by 1080, `EB Garamond` in dark ink on paper, left-aligned. `hero` is 2.4 times the size in bold, `weight` 1.5 times in bold, and `tone` 1.25 times in italic, so emphasis shows at a glance | `canvas`, `blur-in`, `rotate-shrink`, `follow` |

With `gap`, words build up on one page as the camera travels across it, so the `at` hints for each group are what make the layout: which side of the last group it goes on, and its turn. Without hints, each group goes below the last.

The camera blurs as it moves, the way a film camera does. That's automatic: a still camera costs nothing, and a moving one renders several times slower.

## Look settings

Colors are `[red, green, blue]` from 0 to 255. These are the defaults, which are the `plain` preset:

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
| `paper` | false | Show the background as paper, with grain and toasted corners |
| `ink` | [245, 245, 240] | Text color |
| `emphasis` | See below | How each level looks |

`emphasis` sets `hero`, `weight` and `tone`, each with any of `size` (relative, default 1), `bold`, `italic` and `color` (default: `ink`). A level you set replaces its default entirely. The defaults suit Archivo Black, which has no bold or italic: `hero` is 1.7 times the size in yellow, `weight` 1.35 times in yellow, and `tone` gray. A level that looks like plain text, or asks for a style the font lacks, is an error.

## What to edit

Do these in order of value:

1. **Emphasis.** The draft's rules mark few words and miss what only meaning shows, like the image a sentence turns on. Mark what carries the point.
2. **Groups.** Move words between groups so each reads as a unit of meaning. Start a new section where the subject changes.
3. **Look and motion.** For example, a single word alone as its own group, larger, or a different `side` and `turn` in a group's `at` hints. After moving words between groups, run `kinetic check`, since the draft's placement was searched for the groups as they were.

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

`clean` is true when there are no overlaps, clipped words or brief words. The check can't judge taste, so look too:

| Command | Shows | Takes |
|---|---|---|
| `kinetic preview --out sheet.png` | A contact sheet: one small frame per group, just after its last word lands, labelled with the group and time | Under a second |
| `kinetic preview --out clip.mp4` | A clip at half size, with its audio, to judge motion and pace | About a second per 5 seconds of video |
| `kinetic frame --at 12.5` | One moment at full size | Under a second |

`preview` takes `--from` and `--to` in seconds to cover part of the video. A sheet of a whole video has a tile for every group, so use a range of 20 or 30 seconds to see each tile clearly. The result lists each tile's group and time:

```json
{"ok": true, "sheet": "sheet.png", "tiles": [{"group": "sections[0].groups[0]", "at": 0.49}, {"group": "sections[0].groups[1]", "at": 3.55}]}
```

A full render of a 60-second video takes a few seconds with `plain`, and about 15 seconds with a moving camera, as in the draft.
