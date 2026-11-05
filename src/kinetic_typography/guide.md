# Using kinetic: a guide for AI agents

`kinetic` turns a voiceover into a kinetic typography video. The tool does what it can measure: the words' timing, where each group fits, the camera, and finding what a viewer would see is wrong. You do what needs meaning: which words matter, how they group, and where the turns go. Every decision lives in a JSON plan file, and the video is made from the plan alone.

**Emphasis is the part only you can do well, and it decides the video's quality.** The tool can't read meaning. Its draft guesses with rules, and on a narration that a person marked, those guesses were right 63% of the time and found about a third of the person's words. A plain layout with the right emphasis beats a rich one with the wrong emphasis, so spend your effort here first.

## Workflow

```bash
kinetic plan --audio talk.mp3 --out talk.plan.json --json    # add --script talk.txt if you have the words
kinetic analyze --plan talk.plan.json --json    # optional: how the voice stressed each word
# Read the draft, then edit talk.plan.json: emphasis first, then groups, then placement.
kinetic check --plan talk.plan.json --json
kinetic preview --plan talk.plan.json --out sheet.png --json
kinetic frame --plan talk.plan.json --at 12.5 --out check.png --json
kinetic render --plan talk.plan.json --out talk.mp4 --json
```

Run `check` after every edit and fix what it finds. Look at a `preview` sheet before rendering, since a plan can pass every check and still read badly.

`kinetic make --audio talk.mp3 --out talk.mp4 --json` does plan and render in one step, with no edits. Its emphasis is guessed by rules, so use it when a rough video is enough.

## Frame size

`make` and `plan` take `--size WIDTHxHEIGHT`, which the draft writes into the plan's `look` as `width` and `height`. Set it when drafting, because the draft shapes its lines for the frame: up to 30 characters at 16:9, 22 square and 17 at 9:16. Any size from 16 to 8192 pixels a side works. Common ones:

| Size | For |
|---|---|
| `1920x1080` | Landscape 16:9, the default: YouTube and most screens |
| `1080x1920` | Vertical 9:16: Shorts, Reels and TikTok |
| `1080x1350` | Portrait 4:5: Instagram and Facebook feeds |
| `1080x1080` | Square 1:1 |
| `1280x720`, `3840x2160` | Landscape 16:9 at 720p or 4K |

To change the size of a plan already drafted, edit `look.width` and `look.height` and run `kinetic check`. The layout still works, but its lines were shaped for the old frame, so a new draft at the right size fits better.

## The draft

`kinetic plan` writes a complete first draft that `check` passes:

- **Sections** start at a pause of 0.7 seconds or more between sentences, once a section has 12 words.
- **Groups** are clauses of up to 8 words, set in lines of up to 5 words and a length that suits the frame, breaking where the punctuation and pauses suggest.
- **Placement** uses the `gap` preset. Each group gets `at` hints from a rule: mostly below the last, every third turned across it, and a turned page with a 400-pixel gap at each section. Where a spot would land on words still showing, or leave this group or the end of the one before out of frame, the next one on the group's list is used.
- **Emphasis** comes from rules, and the result says so with `"emphasis_from": "rules"`. Negations like *not* and *never* are `tone`. Numbers, sentence ends, names and long words score toward `weight`, less if said before, and a section's best-scoring word is its `hero`. It marks about one word in eight. On a narration that a person marked, 63% of its marks were right, and it found 32% of theirs. The rest needs meaning, which is your part.

## A worked example

These edits are to the draft of a 60-second news narration about a crypto theft. Each was checked with `kinetic check`.

### Emphasis and groups

The draft's second section:

```json
[
 {"text": "The comforting story", "at": {"side": "below", "gap": 400, "turn": -90}},
 {"text": "your money sits / in a vault", "at": {"side": "below"}},
 {"text": "offline", "at": {"side": "right"}},
 {"text": "*untouchable*", "at": {"side": "right"}},
 {"text": "This crew / took 20 minutes", "at": {"side": "below"}}
]
```

The sentence sets up a belief, lists why it feels safe, and knocks it down. Directed:

```json
[
 {"text": "The _comforting_ story:", "at": {"side": "below", "gap": 400, "turn": -90}},
 {"text": "your money / sits in a *vault,*", "at": {"side": "below"}},
 {"text": "_offline,_", "at": {"side": "right"}},
 {"text": "*untouchable.*^1.4", "at": {"side": "below", "align": "right"}},
 {"text": "This crew took / **20 minutes.**", "at": {"side": "below", "turn": 90, "gap": 60}}
]
```

- `_comforting_` is `tone`: the word is ironic, and italic says so without shouting.
- The list builds: `*vault,*`, then `_offline,_` beside it, then `*untouchable.*` on its own line and a little larger, with `^1.4`.
- `**20 minutes.**` is the section's one `hero`, because it's the point the list was set up for. The draft had marked nothing there.
- The last group turns 90 degrees, so the camera turns with it as the story turns.
- Punctuation is kept in `text` because it's shown. Text must match the spoken words, but only letters and digits are compared.

### Contrast

The draft:

```json
[
 {"text": "Binance says / it will cover / all losses", "at": {"side": "right", "turn": -90}},
 {"text": "but withdrawals / are still *suspended*", "at": {"side": "below"}},
 {"text": "**2.8 billion** is *frozen*", "at": {"side": "below"}}
]
```

A promise, then the catch. The rules made the number the hero, but the news is the catch. Directed:

```json
[
 {"text": "Binance says / it will *cover* all losses,", "at": {"side": "right", "turn": -90}},
 {"text": "_but_ withdrawals / are still **suspended.**", "at": {"side": "below"}},
 {"text": "2.8 billion / is *frozen.*", "at": {"side": "below", "align": "right"}}
]
```

- `*cover*` is the promise and `**suspended.**` is the catch. `_but_` is the hinge between them: short words of contrast and negation, like *but*, *not* and *no*, are the ones most often missed.
- The number loses its mark. A number isn't the point just because it's a number.

### A check finding

Moving `*untouchable.*^1.4` to `{"side": "left"}` puts it on words still showing. `kinetic check --json` says where:

```json
{"ok": true, "clean": false, "overlaps": [{"group": "sections[1].groups[3]", "word": "untouchable.", "at": 10.11, "lands_on": "sections[1].groups[1]", "on_word": "your"}], "clipped": [], "brief": []}
```

`group` names the group to change, and `lands_on` the one it hits. Here, `{"side": "below", "align": "right"}` puts it back clear. `styles` is left out of this result for space.

## Voice hints

`kinetic analyze --plan talk.plan.json` measures how strongly the voice stressed each word and writes it into the plan's `words` as `stress`, from 0 (least in this recording) to 1 (most). It takes about a second, and it changes nothing else:

```json
{"ok": true, "plan": "talk.plan.json", "words": 157, "most_stressed": [{"word": "2.8 billion", "at": 40.42, "stress": 1.0}, {"word": "$6.3 billion", "at": 0.24, "stress": 0.99}]}
```

`most_stressed` is the top tenth of the words. Stress is evidence, not a decision: nothing is marked or drawn from it. It's measured from loudness, pitch, length and pauses, each against the speaker's own trend through the sentence. On a text-to-speech narration it ranked a person's marked words above unmarked ones 69% of the time, where 50% is chance, and it added nothing to reading the text. Use it where reading the text leaves you unsure, such as which of two words in a sentence carries it, and expect it to work better on a human voice that stresses for meaning.

## Audio alone, or with a script

Audio alone is the default: the tool works out the words, then times them. Add `--script talk.txt` when you have the exact words and either the audio is unclear or the words must be exact, such as names and invented spellings. The script's words are then what's shown, and nothing is transcribed.

From audio alone, words can be misheard, and every wrong word shows on screen. Read the words in the plan against what you know of the content, and correct `text` directly: the timing stays right if the mistake is only spelling. If many words are wrong, supply a script.

Writing a script:

- English only, with or without a script. Non-English text won't align.
- Write what's spoken. Digits are fine (`$6.3 billion`, `2026`, `20%`, `3rd`) because they're converted to how they sound.
- Numbers are shown as digits either way. "Six point three billion dollars" in the script, or in the audio, becomes one word in the plan, `$6.3 billion`, timed across all of its spoken words. That's why the plan can have fewer words than the script, and it isn't reported in `doubtful`.
- Other than that, the script doesn't need to be perfect. Ad-libs in the audio are skipped, and reworded or unspoken script words are reported in `doubtful`.
- Sentence ends always end a group in the draft. Commas, colons and dashes encourage a break.

## Reading results

With `--json`, stdout carries exactly one JSON object and progress goes to stderr. Exit code 0 means success and 1 means failure.

```json
{"ok": true, "plan": "talk.plan.json", "words_from": "audio", "emphasis_from": "rules", "duration": 60.5, "size": [1920, 1080], "sections": 6, "groups": 41, "confidence": -0.06, "doubtful": []}
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
 "preset": "gap",
 "audio": "talk.mp3",
 "duration": 4.0,
 "emphasis": {"source": "meaning"},
 "look": {"emphasis": {"tone": {"size": 1.1, "italic": true}}},
 "defaults": {"retire": {"type": "rotate-shrink", "angle": 90}},
 "sections": [
  {"groups": [
   {"text": "**$6.3 billion** left"},
   {"text": "the world's / *biggest* crypto exchange", "at": {"side": "below"}, "retire": "drop"}
  ]}
 ],
 "words": [
  {"text": "$6.3 billion", "start": 0.24, "end": 1.10},
  {"text": "left", "start": 1.12, "end": 1.40},
  {"text": "the", "start": 1.42, "end": 1.50},
  {"text": "world's", "start": 1.52, "end": 1.86},
  {"text": "biggest", "start": 1.88, "end": 2.30},
  {"text": "crypto", "start": 2.32, "end": 2.70},
  {"text": "exchange.", "start": 2.72, "end": 3.30}
 ]
}
```

| Field | Meaning |
|---|---|
| `audio` | Voiceover path, relative to the plan file |
| `duration` | Video length in seconds |
| `words` | The record: each spoken word and when, in seconds, plus its `stress` once `kinetic analyze` has run. Edit `text` only to fix a misheard word, and times only if they're wrong |
| `sections` | The direction: groups of the spoken words, in order. A new section clears the screen |
| `groups` | What's shown together. Every spoken word belongs to exactly one group, in order |
| `emphasis` | Where emphasis comes from: `{"source": "meaning"}`, the markup, is the only option. The voice gives hints through `kinetic analyze` instead |
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
| `word^1.5` | Size, relative to the rest of the group. It multiplies the level's size |
| `/` | A line break, as its own word. Without one, the place effect chooses the lines |

A mark can cover several words, as in `_not your keys_`. A spoken word written with a space, like `$6.3 billion`, takes markup and size as one word: `*$6.3 billion*^2`. Marking only part of it is an error. Text may differ from the spoken word in punctuation and case, and punctuation on its own, like `—`, joins the word next to it.

Emphasis works when it's rare and uneven: often a quarter of the words or fewer, with `hero` at most once a paragraph, and some sentences with none.

## Presets

A preset sets a whole style at once. Your `look` and `defaults` then change only the keys you give. In `look.emphasis` that's level by level, so `{"tone": {"size": 0.8}}` keeps the preset's `hero` and `weight`.

| Preset | Look | Effects |
|---|---|---|
| `plain` | The look settings' defaults below: one group at a time, in heavy capitals on a dark background. A plan without `preset` is `plain` | `fit`, `pop`, `fade`, `still` |
| `gap` | 1920 by 1080, `EB Garamond` in dark ink on paper, left-aligned. `hero` is 2.4 times the size in bold, `weight` 1.5 times in bold, and `tone` 1.25 times in italic, so emphasis shows at a glance. The draft uses it | `canvas`, `blur-in`, `rotate-shrink`, `follow` |

With `gap`, words build up on one page as the camera travels across it, so the `at` hints for each group are what make the layout: which side of the last group it goes on, and its turn. A group with no hints goes below the last. After moving words between groups, run `kinetic check`, since the draft's hints were searched for the groups as they were.

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

`emphasis` sets `hero`, `weight` and `tone`, each with any of `size` (relative, default 1), `bold`, `italic` and `color` (default: `ink`). A level you set replaces the preset's version of it entirely. Without a preset, the levels suit Archivo Black, which has no bold or italic: `hero` is 1.7 times the size in yellow, `weight` 1.35 times in yellow, and `tone` gray. A level that looks like plain text, or asks for a style the font lacks, is an error.

## Checking your work

`kinetic check` takes about a second and reads the plan the way a viewer would see it:

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

A tile can show an earlier group cut off at the edge, because the camera is already travelling to the newest group. That's expected: `check` measures each word only as it lands. On a sheet, look for what a check can't see: a section where every group sits the same way, emphasis that doesn't match what the voice is saying, or a hero that isn't the point.

A full render of a 60-second video takes a few seconds with `plain`, and about 15 seconds with a moving camera, as in the draft.

Don't change the timing unless you've found it wrong. It comes from the audio and is usually accurate to a few hundredths of a second.
