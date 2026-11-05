# Next architecture

The agreed direction for the next stage. A prototype has passed (see below), and all eight steps of the [Stage 1 plan](#stage-1-plan) are in the package. All sizes and savings here are estimates.

## Goal

The target is a **continuous canvas**: words stay in one world, and a camera travels through it while old words rotate, shrink and disappear. Each of those behaviors must be replaceable, so rotation can be swapped for another effect.

The project stays focused on words in motion. Each new idea gets sorted into a stage, other tools, or out of scope.

**The boundary:** an agent-friendly tool that turns audio into kinetic typography video. It can run attended or unattended; whoever drives it decides. Agent-friendly means failures are loud and readable by a machine, checks report what a person would otherwise have to spot, and quality can be scored against references that people mark once.

## What makes a video kinetic

| Axis | Question | Today | Next | Later | Skip |
|---|---|---|---|---|---|
| Grouping | Which words belong together? | Phrases | Sections above phrases | | |
| Composition | Where do words sit relative to each other? | Fit to screen | Canvas | Scroll, text on a path | |
| Word motion | How does a word arrive and leave? | Pop, fade | Slide, blur-in | Letter by letter | Changing letter shapes |
| Camera | Where are we looking? | Fixed | Cut, pan, zoom, rotate, motion blur | Drift, shake | True 3D |
| Look | How does it appear? | One font, one accent | Fonts, per-word size and color, section themes | Texture, images | |
| Timing | When does it happen? | Speech | Speech | Beats for music | |

## Reference videos

Reviewed from sampled frames, without sound, so motion and pacing are only partly judged.

| Reference | What it teaches | Verdict |
|---|---|---|
| [Stephen Fry, Language](https://www.youtube.com/watch?v=J7E-aoXLZGY) | Words stay in a world, with a camera moving between clusters, many sizes and structural rotation | Build |
| [The Gap](https://www.thisamericanlife.org/extras/the-gap) | One serif, bold and italic per word, rotated lines, camera blur, paper texture | Build. First target |
| [Pulp Fiction](https://www.youtube.com/watch?v=hjoH1TL3LMg&t=90s) | Lines scaled to one width, nested movement, a typeface per speaker | Build the type. Icons later |
| [Curiosity](https://www.youtube.com/watch?v=8fsH8qxDDY4) | Words part to make room for a new word | Build the reflow. Illustration belongs to other tools |
| [The Girl Effect](https://www.youtube.com/embed/WIvmE4_KMNw) | Words land, overlap and push a stack, single letters move, timing isn't tied to speech | Later |
| [From Paper to Screen](https://www.athenastokes.design/blog/from-paper-to-screen) | Each section has its own era of fonts, textures and backgrounds | Later |
| [Childline, First Step](https://www.youtube.com/watch?v=cqdVEZuTZtg) | Hand-drawn letters that change shape, plus simple letter reveals and two-voice contrast | Out of reach overall. Take the reveal and the contrast |
| [Burger King, You Rule](https://www.youtube.com/embed/-fr78CuwlBY) | A few words composited over live footage | Other tools, through transparent output |
| [The Fallen of World War II](https://www.youtube.com/watch?v=DwKPFT-RioU) | Data visualization, not typography | Out of scope, insight only |

Not reviewed: [Ira Glass on Storytelling](https://vimeo.com/24715531), which needs a login. The Gap frames came from a YouTube upload that couldn't be confirmed as the version linked above.

## Design

```
audio ▶ words + timing ▶ DIRECTION ▶ effects ▶ tree + changes over time ▶ draw list ▶ Skia
```

1. **Elements in a tree:** letter, word, group, section, world. Moving a group moves its words.
2. **Properties that change over time:** position, size, rotation, opacity and blur can change at any moment, not only on entry and exit. Effects write these changes, so words can reflow and push each other.
3. **Replaceable slots:** `place`, `arrive`, `retire` and `camera` each take any registered effect, with parameters.
4. **Effects in one registry:** an effect is a small named function. The registry generates its documentation and validation, and runs shared tests on it.
5. **Styles that inherit:** section, then group, then word. A voice can be a named style.
6. **Timing as plain data:** the renderer doesn't care whether times came from speech, beats or a person.
7. **Layers:** background, then text, with masks possible later. This also allows transparent output.

Agents can direct at whichever level is enough:

```json
{
  "defaults": {"place": "canvas", "arrive": "blur-in", "retire": "rotate-shrink", "camera": "follow"},
  "styles": {"caller": {"font": "Archivo Black", "color": [245, 245, 240]}},
  "sections": [{"style": "caller", "phrases": [{"words": ["..."], "retire": "fly-left"}]}]
}
```

| Level | Example |
|---|---|
| Preset | `"preset": "gap"` |
| Swap a slot | `"retire": "fly-left"` |
| Tune it | `"retire": {"type": "rotate-shrink", "angle": 90}` |
| Direct one element | Make one word huge and italic |
| Exact control | Keyframes on any element |

**Trade-off:** this is more machinery than today's "state at time t" function. It's accepted because reflow and interaction can't be added later without replacing the core. Pay for the model now, and for the effects that use it only when they're needed.

## Agent flow

```
kinetic analyze    words, timing, pauses, and optionally how the voice stressed them
Agent writes direction
kinetic check      collisions, clipping at the frame edge, markup that didn't apply, words too brief to read
kinetic preview    contact sheets and short clips
Agent edits one section; the rest stays put
kinetic render     MP4, or transparent video for other tools
```

`kinetic make --audio talk.mp3` stays the one-step path, and it has to produce a good default.

The tool should provide what agents can't do alone: timing, solving geometry, planning camera paths, measuring motion and catching failures. Agents keep meaning, emphasis, metaphor, voice assignment and mood.

## Stages

| Stage | Build | Estimated new code |
|---|---|---|
| 1. Core | Tree and changing properties, canvas placement, moving camera with motion blur, slots with 2–3 effects each, per-word font, weight and size, voice styles, emphasis levels with optional voice hints, `check`, contact-sheet preview | 2,000–3,000 lines |
| 2. Richer type | Scaled line stacks, reflow, letter-level reveal, overlaps, custom fonts, background per section, transparent output | 2,000–3,000 lines |
| 3. Advanced | Masks and stripe reveals, physics-style stacking, beat timing, section transitions, simple icons | 2,000–4,000 lines |

**Other tools:** illustration, live footage, music and charts. We hand off through transparent video and take in images.

**Out of scope:** hand-drawn letter shapes, character animation, data visualization, video editing, particle effects and true 3D.

## Prototype result

A throwaway prototype, outside the package, had the tree, changing properties, the four slots and a renderer that knows no effect by name, in about 500 lines. A 60-second narration was hand-directed in The Gap's style as 36 groups, 2026-11-03.

| Pass check | Result |
|---|---|
| The hand-directed video looks right to a person | Passed. Judged by watching the full video |
| Swapping `retire` from rotation needs a direction change only | Passed. `fly-left` and `drop` were each a one-line change to `defaults` |
| Adding a new `retire` effect changes the renderer by zero lines | Passed. The renderer's source was identical before and after adding `drop` |

What it taught:

- **Collisions are the placement problem.** The first direction put 15 groups on top of words still on screen, and a rotated-rectangle overlap check found every one. Ten came from anchoring a turned group by its unturned corner. Placing it by its turned footprint fixed those, and the other 5 were fixed in the direction. `check` should include this overlap test from the start.
- **Motion blur costs about 15 times the render time.** 1080p at 30 fps took 57–63s for 60 seconds, against about 4s today. Blur drew sub-frames on 29% of frames, 2.85 draws per frame on average, and the per-frame compositing in numpy is also part of the cost. Previews should render at lower resolution.
- **A small direction vocabulary was enough** to hand-direct the whole video: side (below, right, left, above), turn, gap, align, offset and a section flag, plus inline markup for bold, italic and size.

## Agent test

A fresh Haiku agent got a one-page guide, the words with their timing, and the prototype. It didn't see the hand direction. 2026-11-03.

| Measure | Result |
|---|---|
| Finished | Yes. A full video, with 0 overlaps |
| Effort | 4 check runs and 3 contact sheets. It never read the engine's code |
| Cost | About 63,000 tokens and 2 minutes, plus about 1 minute of rendering |
| Quality | Clean and readable but flat: 20 groups, 2 turns and little size contrast. It reads as a document scrolling, not The Gap |

What it taught:

- **Operating the tool isn't the hard part; craft is.** A weak model ran the loop correctly but made timid choices. Presets that make strong contrast the default, and a guide with worked examples instead of warnings, should help.
- **Markup failed silently.** Markup across a two-token spoken word, like `*$6.3 billion*^2`, was dropped without an error, and the agent reported it as applied. An agent can't act on what isn't reported, so this is the worst kind of failure. Markup that doesn't apply must be an error, and `check` should print the styles it applied.
- **`check` needs edge clipping.** The agent found clipped words only on contact sheets.
- **Lines inside a group sit too close.** This shows once groups have three or more lines.

## Emphasis

Which words stand out matters more than how they move: a plain video with the right emphasis beats a rich one with the wrong emphasis.

A person marked a reference on the same narration: 37 of 157 words, at three levels. **Hero** is the one word of a paragraph, the biggest and boldest. **Weight** is what a listener must remember, in bold. **Tone** is irony, softness or contrast, in italic at normal weight; it's a different kind of emphasis, not a weaker one. Candidates were scored word by word:

| Candidate | Marked | Found | Extra | Precision | Recall |
|---|---|---|---|---|---|
| Today's rules (`phrases.py`) | 51 | 19 | 32 | 0.37 | 0.51 |
| Claude, reading the text | 52 | 30 | 22 | 0.58 | 0.81 |
| Haiku, reading the text | 20 | 17 | 3 | 0.85 | 0.46 |
| The voice, top 37 words | 37 | 12 | 25 | 0.32 | 0.32 |
| Step 6 rules (`phrases.py`) | 19 | 12 | 7 | 0.63 | 0.32 |

The voice was measured from loudness, pitch, length and pauses, each against the speaker's trend through the sentence. Its ranking AUC was 0.68, where 0.5 is chance, and word length was its best signal at 0.72. Used as a filter on Claude's picks it scored 0.51, so it added nothing on top of reading the text. The test narration is text-to-speech, which may stress words by rule rather than meaning, so this result may not hold for a human voice.

What it taught:

- **Read emphasis from the meaning, and best from the source.** Whoever writes the script knows what matters, and marking emphasis as it's written is cheaper and more reliable than recovering it later.
- **Voice analysis is optional.** It's an opt-in plan field, such as `"emphasis": {"source": "meaning"}` with `"voice"` or `"both"`. When on, it writes per-word stress into the plan as hints for the agent, never as decisions. It isn't a CLI flag.
- **The default needs a reader.** The tool can't read meaning alone. Marks come from the script, or from the agent driving the tool. Otherwise the fallback is the rules, which are improved but still weak, and the tool must report that it used them.
- **Today's rules mark one word per phrase.** Emphasis should be rare and uneven, which is the main reason they over-mark.
- **The models differ in how much they mark, not which words they see.** Haiku's picks were a subset of Claude's. The reference marked 24% of words, Haiku 13% and Claude 33%. Short words of contrast and negation, like *not*, *no* and *cover*, were the ones most often missed.
- **One reference ranks nothing.** It's enough to say the rules need replacing. Two or three more references are needed before tuning a guide or choosing between models.

## Stage 1 plan

Agreed 2026-11-03. It moves the prototype's design into the package, so an agent can direct a video through the CLI and every failure is reported, never silent.

Build order:

1. **Core model.** The tree, changing properties, the four slots and the effect registry replace `layout.py` and `animate.py`. Every effect passes the shared tests. *Done 2026-11-03.* Version 1 plans run through it as `fit`, `pop`, `fade` and `still`, and look as before, except that line boxes now fit the ink instead of the cap height. The prototype's hand direction rebuilt through it with 0 overlaps.
2. **Plan format v2.** It adds sections, groups and lines, and per word an emphasis level (hero, weight or tone) and an optional size. It also adds placement fields and slot choices. `"emphasis": {"source": "meaning"}` is the default, with `"voice"` or `"both"` as opt-ins. `PLAN_VERSION` goes to 2, and version 1 plans are refused with a message rather than converted. Markup that doesn't apply, a word that doesn't match the recording, or an unknown effect is an error. *Done 2026-11-03,* with two changes. The bundled serif came forward from step 5, since bold and italic levels can't be drawn without it. `"voice"` and `"both"` are refused until step 8 builds them, so the field never promises what the tool can't do. The prototype's hand direction, translated, loads with no errors, renders with 0 overlaps and looks like the prototype.
3. **`kinetic check`**, with output a machine can read. It reports overlaps, clipping at the frame edge, words too brief to read, and the styles actually applied. *Done 2026-11-04.* Clipping is measured once per word, 0.25 seconds after it starts. Measuring for as long as its group is spoken flagged 17 words in the hand direction, which a person had passed. Most of those were words already read, leaving as the camera travelled on. Measured once, it flags 3. All 3 are real: the hero word *vanished* is 454px out of frame while it's spoken, because `follow` starts travelling before the group's last word lands. `follow` now stays until 0.25 seconds after a group's last word starts, its `linger`, and then travels in the time left. That leaves the hand direction clean. Its median trip went from 0.6 to 0.5 seconds, and the quickest from 0.55 to 0.12. It was chosen over keeping emphasized words off a group's end, which is often the strongest place for them, and its look is still to be judged by watching. On the draft of the same narration, it finds 14 words readable for under 0.3 seconds, as short as 0.1, all of them the last word of a group that leaves as the next one starts.
4. **Previews.** Contact sheets and short low-resolution clips, since full renders with motion blur are slow. *Done 2026-11-04,* as `kinetic preview`, which picks by the output's extension. A sheet has one tile per group, 0.25 seconds after its last word starts, so each tile names a place in the plan. A clip is half size. Both take `--from` and `--to`. A sheet of all 36 groups of the hand direction takes 0.2 seconds, and a 5-second clip 0.8. Full renders now cut the audio to the video's length.
5. **Rendering.** The moving camera with motion blur and a paper look. The presets are `gap` first and `plain` for today's look. Render frames in parallel, since each depends only on the plan and its time. *Done 2026-11-04.* A plan's `preset` gives a look and defaults, which its own `look` and `defaults` override key by key. `plain` is the default, so drafts look as before until step 6 can place groups on a canvas. Motion blur follows the camera and has no field: a still camera costs nothing. `look.paper` turns the background into paper. The hand direction on `gap` renders in 13.6 seconds, against 57–63 for the prototype, and its frames match the prototype's. Fast camera turns still show separate sub-frames, as the prototype's did, since the count stops at 10.
6. **Automatic first draft.** `kinetic make --audio` still works with no agent: groups from sentences and pauses, placement by a rule that uses the overlap check as a search, and emphasis from improved rules. Those rules mark less, and favor numbers and contrast words. The tool reports that it fell back to rules. *Built 2026-11-04, to be judged by watching.* The draft now uses `gap`. Groups are clauses of up to 8 words in lines of up to 5, from the same break costs at both levels, which took the reference narration from 54 groups to 41, near the hand direction's 36. A pause of 0.7 seconds between sentences starts a section, once it has 12 words, and that found all six paragraphs of the reference script. Each group gets `at` hints from a short list, the rule's choice first, and the first spot that neither overlaps nor clips is kept. Without the search the draft overlaps, and a test shows it. Bold alone read as flat, so the `gap` preset now gives the levels sizes too: `hero` 2.4, `weight` 1.5 and `tone` 1.25. Agents writing their own plans get that contrast by default, as the agent test asked. The hand direction sets its own `^` sizes on top, so it now keeps the old level sizes in its own `look` and renders as before. Both the reference narration and a recording the rules never saw come out clean on `check`, where the old draft had 14 brief words, and drafting takes 0.3 seconds. On the reference, the new rules mark 19 words where the old marked 51: precision went from 0.37 to 0.63 and recall from 0.51 to 0.32, measured by `tools/eval_emphasis.py`. Recall stays near 0.33 at every threshold tried, because the missed words, like *vault*, *cash* and *copied key*, need meaning. `make` and `plan` report `"emphasis_from": "rules"`. On the unseen recording the rules marked 13 of 180 words, with one hero.
7. **Guide.** `guide.md` is rewritten with worked examples, and the README changes in the same commit. *Done 2026-11-04.* It now leads with the draft and a worked example from the reference narration: two passages directed for emphasis, grouping and turns, and one `check` finding with its fix. Each edit was applied to a real draft and checked clean. The warnings it had became reasons inside the examples. A test parses every JSON example in the guide and loads its plan, so an example that stops working fails the tests; a misspelled word in it fails with the field named.
8. **Optional voice hints.** `kinetic analyze` writes each word's measured stress into the plan as hints. It's last, because it measured weak. *Done 2026-11-04,* with one change. `analyze` writes `stress`, a rank from 0 to 1, into each of the plan's `words`, and nothing reads it but the agent. The `"voice"` and `"both"` sources were not built: a hint that never decides can't be where emphasis comes from, so the field would have done nothing. `emphasis.source` stays, with `"meaning"` its only value, since removing it would break every saved plan; it can go at the next format change. The study's measure moved into `voice.py` unchanged in method, and on the reference narration it ranks the marked words with an AUC of 0.69 against the study's 0.68. `tools/eval_emphasis.py` reports that AUC whenever a plan has stress. Analyzing 60 seconds takes about half a second.

The tool doesn't call a model itself. Reading meaning belongs to the agent driving it, or to the script's author.

Done when:

- The tests pass and `eval_alignment.py` shows timing unchanged.
- A fresh Haiku agent, given only `kinetic guide`, directs the reference narration with no silent failures and a clean `check`. Its emphasis is scored against the reference and its token cost recorded.
- A person watches that video once.
- The no-agent default is acceptable on a recording it hasn't seen.

### Stage 1 agent test

A fresh Haiku agent got only `kinetic guide`, the narration's audio and its script, 2026-11-04.

| Measure | Prototype test | Stage 1 |
|---|---|---|
| Finished | Yes, 0 overlaps | Yes, `check` clean |
| Effort | 4 checks, 3 sheets | 3 checks, 1 sheet, 9 tool calls. It never read the code |
| Cost | About 63,000 tokens, 2 minutes | 67,042 tokens, 90 seconds, render included |
| Emphasis against the reference | Not scored | Precision 0.76, recall 0.51, 16% of words marked |
| Silent failures | Markup dropped without an error | None |

**The emphasis score is inflated.** The guide's worked example is drawn from this same narration, and the agent said it borrowed several edits from it. That passes the "no silent failures" and "clean check" parts of the done-when list, but the emphasis score needs a narration the guide doesn't contain, with its own reference. The agent kept the draft's groups and placement, so the layout is the draft's.

It found three gaps in the guide, fixed the same day: the workflow didn't show `--script`, nothing said spoken numbers become one digit word such as `$6.3 billion`, and earlier groups cut off at the edge of a sheet's tile looked like a fault.

## Open risks

- **Automatic placement** may look random no matter how much code it gets. It's the biggest risk.
- **Taste can't be tested.** A layout can pass every check and still look bad. When nobody reviews the result, checks, emphasis references and possibly a model reviewing the contact sheet are the only guards, and that last gate is unmeasured.
- **Local edits** are hard on a connected canvas, and hand-placed overrides may conflict when placement re-runs. Pinned elements need clear rules.
- **Agent savings are partly measured.** A Haiku agent directed a video for about 63,000 tokens. Making the same video without the tool hasn't been tried.
