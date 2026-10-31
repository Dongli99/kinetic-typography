# Next architecture

The agreed direction for the next stage. None of this is built yet, and the code still works as [CLAUDE.md](../CLAUDE.md) describes. All sizes and savings here are estimates.

## Goal

The target is a **continuous canvas**: words stay in one world, and a camera travels through it while old words rotate, shrink and disappear. Each of those behaviors must be replaceable, so rotation can be swapped for another effect.

The project stays focused on words in motion. Each new idea gets sorted into a stage, other tools, or out of scope.

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
kinetic analyze    words, timing, pauses, how the voice stressed them
Agent writes direction
kinetic check      overflow, collisions, words too brief to read
kinetic preview    contact sheets and short clips
Agent edits one section; the rest stays put
kinetic render     MP4, or transparent video for other tools
```

`kinetic make --audio talk.mp3` stays the one-step path, and it has to produce a good default.

The tool should provide what agents can't do alone: hearing the voice, solving geometry, planning camera paths and measuring motion. Agents keep meaning, metaphor, voice assignment and mood.

## Stages

| Stage | Build | Estimated new code |
|---|---|---|
| 1. Core | Tree and changing properties, canvas placement, moving camera with motion blur, slots with 2–3 effects each, per-word font, weight and size, voice styles, voice analysis, `check`, contact-sheet preview | 2,000–3,000 lines |
| 2. Richer type | Scaled line stacks, reflow, letter-level reveal, overlaps, custom fonts, background per section, transparent output | 2,000–3,000 lines |
| 3. Advanced | Masks and stripe reveals, physics-style stacking, beat timing, section transitions, simple icons | 2,000–4,000 lines |

**Other tools:** illustration, live footage, music and charts. We hand off through transparent video and take in images.

**Out of scope:** hand-drawn letter shapes, character animation, data visualization, video editing, particle effects and true 3D.

## Next step: a prototype

Before redesigning, build a throwaway prototype with the tree and changing properties, outside the package. Hand-direct a 60-second narration in The Gap's style, then watch it.

It passes if:

1. The hand-directed video looks right to a person. Automate placement only after this.
2. Swapping `retire` from rotation to another effect needs a direction change only.
3. Adding a new `retire` effect changes the renderer by zero lines.

If the hand-directed video doesn't look right, stop and rethink before migrating.

## Open risks

- **Automatic placement** may look random no matter how much code it gets. It's the biggest risk.
- **Taste can't be tested.** A layout can pass every check and still look bad, so review by a person is the slowest step.
- **Motion blur** draws each frame several times, and the slowdown hasn't been measured.
- **Local edits** are hard on a connected canvas, and hand-placed overrides may conflict when placement re-runs. Pinned elements need clear rules.
- **Agent savings are unmeasured.** After Stage 1, have an agent make the same video with and without the tool.
