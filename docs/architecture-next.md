# Next architecture

The agreed direction for the next stage. A prototype has passed (see below), and step 1 of the [Stage 1 plan](#stage-1-plan) is in the package. All sizes and savings here are estimates.

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
2. **Plan format v2.** It adds sections, groups and lines, and per word an emphasis level (hero, weight or tone) and an optional size. It also adds placement fields and slot choices. `"emphasis": {"source": "meaning"}` is the default, with `"voice"` or `"both"` as opt-ins. `PLAN_VERSION` goes to 2, and version 1 plans are refused with a message rather than converted. Markup that doesn't apply, a word that doesn't match the recording, or an unknown effect is an error.
3. **`kinetic check`**, with output a machine can read. It reports overlaps, clipping at the frame edge, words too brief to read, and the styles actually applied.
4. **Previews.** Contact sheets and short low-resolution clips, since full renders with motion blur are slow.
5. **Rendering.** The moving camera with motion blur and a paper look. The presets are `gap` first and `plain` for today's look. The font is a bundled open-licensed serif, such as EB Garamond, because the prototype's font ships only with macOS. Record the choice in `decisions.md`.
6. **Automatic first draft.** `kinetic make --audio` still works with no agent: groups from sentences and pauses, placement by a rule that uses the overlap check as a search, and emphasis from improved rules. Those rules mark less, and favor numbers and contrast words. The tool reports that it fell back to rules.
7. **Guide.** `guide.md` is rewritten with worked examples, and the README changes in the same commit.
8. **Optional voice hints.** `kinetic analyze` writes each word's measured stress into the plan as hints. It's last, because it measured weak.

The tool doesn't call a model itself. Reading meaning belongs to the agent driving it, or to the script's author.

Done when:

- The tests pass and `eval_alignment.py` shows timing unchanged.
- A fresh Haiku agent, given only `kinetic guide`, directs the reference narration with no silent failures and a clean `check`. Its emphasis is scored against the reference and its token cost recorded.
- A person watches that video once.
- The no-agent default is acceptable on a recording it hasn't seen.

## Open risks

- **Automatic placement** may look random no matter how much code it gets. It's the biggest risk.
- **Taste can't be tested.** A layout can pass every check and still look bad. When nobody reviews the result, checks, emphasis references and possibly a model reviewing the contact sheet are the only guards, and that last gate is unmeasured.
- **Local edits** are hard on a connected canvas, and hand-placed overrides may conflict when placement re-runs. Pinned elements need clear rules.
- **Agent savings are partly measured.** A Haiku agent directed a video for about 63,000 tokens. Making the same video without the tool hasn't been tried.
