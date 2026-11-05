#!/usr/bin/env python3
"""Score a plan's emphasis against a reference that a person marked, word by word.

A word counts as found when both mark it, at any level. Levels are compared separately,
since picking the right word matters more than how it's marked.

The reference is JSON: {"words": [{"text": ..., "start": seconds, "emphasis": "hero" | "weight" | "tone" | null}]}.
If `kinetic analyze` has added stress to the plan's words, it also reports how well stress ranks
the reference's marked words, as an AUC: the chance a marked word is more stressed than an unmarked
one, where 0.5 is chance.

One reference describes one narration. It can show that rules mark too much, not which of
two close settings is better in general.

    tools/eval_emphasis.py reference.json plan.json
"""

import argparse
import json
import sys

from kinetic_typography.plan import load_plan

MATCH_SECONDS = 0.1  # how far apart the reference and the plan may time the same word
MIN_MATCHED = 0.9  # share of reference words that must be found in the plan, or the score means nothing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("reference")
    parser.add_argument("plan")
    args = parser.parse_args()

    with open(args.reference, encoding="utf-8") as file:
        reference = json.load(file)["words"]
    plan = load_plan(args.plan)
    marked = {round(w.start, 2): (w.text, w.spec.level) for g in plan.make_scene().groups for w in g.words}
    stressed = {round(w.start, 2): w.stress for w in plan.words}

    pairs = []
    for ref in reference:
        near = [start for start in marked if abs(start - ref["start"]) <= MATCH_SECONDS]
        if near:
            start = min(near, key=lambda s: abs(s - ref["start"]))
            pairs.append((ref["text"], ref["emphasis"], marked[start][1], stressed[start]))
    if len(pairs) < MIN_MATCHED * len(reference):
        print(f"FAIL: only {len(pairs)} of {len(reference)} reference words were found in the plan. "
              "Are they the same recording?")  # fmt: skip
        return 1

    wanted = sum(1 for _, ref, _, _ in pairs if ref)
    chosen = sum(1 for _, _, got, _ in pairs if got)
    found = sum(1 for _, ref, got, _ in pairs if ref and got)
    same = sum(1 for _, ref, got, _ in pairs if ref and ref == got)
    for text, ref, got, _ in pairs:
        if ref or got:
            verdict = "found" if ref and got else "missed" if ref else "extra"
            print(f"  {verdict:7}{text:18}reference {ref or '-':7}plan {got or '-'}")
    precision = found / chosen if chosen else 0.0
    recall = found / wanted if wanted else 0.0
    print(f"\n{len(pairs)} words. Reference marks {wanted} ({wanted / len(pairs):.0%}), plan marks {chosen} "
          f"({chosen / len(pairs):.0%}). Found {found}, extra {chosen - found}, same level {same}.")  # fmt: skip
    print(f"Precision {precision:.2f}, recall {recall:.2f}")
    if all(stress is not None for *_, stress in pairs):
        marked_stress = [s for _, ref, _, s in pairs if ref]
        plain_stress = [s for _, ref, _, s in pairs if not ref]
        wins = sum((m > p) + 0.5 * (m == p) for m in marked_stress for p in plain_stress)
        print(f"Stress AUC {wins / (len(marked_stress) * len(plain_stress)):.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
