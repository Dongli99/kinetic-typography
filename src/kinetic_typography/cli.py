"""Command line entry point."""

import argparse
import dataclasses
import json
import shutil
import sys
from importlib.resources import files
from pathlib import Path

from . import __version__
from .effects import describe
from .align import align_script, decode_audio, tokenize_script
from .check import MIN_READ, SETTLE, check
from .phrases import group_phrases
from .plan import Plan, draft_plan, load_plan, save_plan
from .render import PREVIEW_SCALE, render_video, save_frame, save_sheet
from .transcribe import transcribe


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="kinetic",
        description="Turn a voiceover into a kinetic typography video.",
        epilog="AI agents: run `kinetic guide` for the full workflow and plan file format.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    def add(name: str, summary: str) -> argparse.ArgumentParser:
        command = commands.add_parser(name, help=summary, description=summary)
        command.add_argument("--json", action="store_true", help="print one JSON result to stdout")
        return command

    script_help = "text file with the words being spoken, for when the audio is unclear (default: work them out from the audio)"

    make = add("make", "Go straight from audio to a video.")
    make.add_argument("--audio", required=True, help="voiceover file (.mp3 or .wav)")
    make.add_argument("--script", help=script_help)
    make.add_argument("--out", default="output.mp4", help="output video (default: output.mp4)")

    plan = add("plan", "Find the words and their timing in the audio, and write an editable plan file.")
    plan.add_argument("--audio", required=True, help="voiceover file (.mp3 or .wav)")
    plan.add_argument("--script", help=script_help)
    plan.add_argument("--out", required=True, help="plan file to write (.json)")

    render = add("render", "Render a plan file to a video.")
    render.add_argument("--plan", required=True, help="plan file")
    render.add_argument("--out", default="output.mp4", help="output video (default: output.mp4)")

    frame = add("frame", "Render one moment of a plan file to a PNG, to check it.")
    frame.add_argument("--plan", required=True, help="plan file")
    frame.add_argument("--at", required=True, type=float, help="time in seconds")
    frame.add_argument("--out", required=True, help="image to write (.png)")

    inspect = add("check", "Find overlapping, clipped and too-brief words in a plan, and list the styles it applies.")
    inspect.add_argument("--plan", required=True, help="plan file")

    preview = add("preview", "Preview a plan quickly: a contact sheet with a frame per group (.png), or a low-resolution clip (.mp4).")
    preview.add_argument("--plan", required=True, help="plan file")
    preview.add_argument("--out", required=True, help="contact sheet (.png) or clip (.mp4) to write")
    preview.add_argument("--from", dest="start", type=float, default=0.0, help="start time in seconds (default: 0)")
    preview.add_argument("--to", dest="end", type=float, help="end time in seconds (default: the end)")

    commands.add_parser("guide", help="Print the guide for AI agents.")

    args = parser.parse_args(argv)
    if args.command == "guide":
        print((files("kinetic_typography") / "guide.md").read_text(encoding="utf-8").rstrip() + "\n")
        print(describe())
        return 0

    try:
        result = {"make": run_make, "plan": run_plan, "render": run_render, "frame": run_frame, "check": run_check, "preview": run_preview}[args.command](args)
    except (OSError, ValueError, RuntimeError) as error:
        if args.json:
            print(json.dumps({"ok": False, "error": str(error)}))
        else:
            print(f"\nError: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"ok": True, **result}))
    return 0


def run_make(args: argparse.Namespace) -> dict:
    plan, summary = _build_plan(args.audio, args.script)
    _render(plan, args.out)
    return {"video": args.out, **summary}


def run_plan(args: argparse.Namespace) -> dict:
    plan, summary = _build_plan(args.audio, args.script)
    save_plan(plan, args.out)
    print(f"Wrote {args.out}", file=sys.stderr)
    return {"plan": args.out, **summary}


def run_render(args: argparse.Namespace) -> dict:
    plan = _load_checked_plan(args.plan)
    _render(plan, args.out)
    groups = sum(len(section["groups"]) for section in plan.sections)
    return {"video": args.out, "duration": plan.duration, "groups": groups}


def run_frame(args: argparse.Namespace) -> dict:
    plan = load_plan(args.plan)
    save_frame(plan.make_scene(), args.at, args.out)
    return {"frame": args.out, "at": args.at}


def run_check(args: argparse.Namespace) -> dict:
    plan = load_plan(args.plan)
    result = check(plan.make_scene(), plan.group_names())
    if not args.json:
        _print_check(result)
    return result


def run_preview(args: argparse.Namespace) -> dict:
    kind = Path(args.out).suffix.lower()
    if kind not in (".png", ".mp4"):
        raise ValueError(f"--out: expected a .png contact sheet or an .mp4 clip, got {args.out}")
    plan = _load_checked_plan(args.plan) if kind == ".mp4" else load_plan(args.plan)
    end = plan.duration if args.end is None else min(args.end, plan.duration)
    if not 0 <= args.start < end:
        raise ValueError(f"--from and --to: expected 0 <= from < to <= {plan.duration}, got {args.start} and {end}")
    scene = plan.make_scene()
    if kind == ".mp4":
        _render(plan, args.out, PREVIEW_SCALE, args.start, end)
        return {"clip": args.out, "from": args.start, "to": round(end, 3), "scale": PREVIEW_SCALE}
    # Each group just after its last word lands, when all of it shows.
    tiles = [(name, round(min(g.words[-1].start + SETTLE, plan.duration), 2)) for g, name in zip(scene.groups, plan.group_names())]
    tiles = [(name, t) for name, t in tiles if args.start <= t <= end]
    if not tiles:
        raise ValueError(f"No group finishes landing between {args.start}s and {end}s")
    save_sheet(scene, tiles, args.out)
    print(f"Wrote {args.out}", file=sys.stderr)
    return {"sheet": args.out, "tiles": [{"group": name, "at": t} for name, t in tiles]}


def _print_check(result: dict) -> None:
    lines = []
    for item in result["overlaps"]:
        lines.append(f"overlap  {item['group']}: {item['word']!r} at {item['at']}s lands on {item['on_word']!r} of {item['lands_on']}")
    for item in result["clipped"]:
        lines.append(f"clipped  {item['group']}: {item['word']!r} is {item['by']}px past the {item['edge']} edge as it lands at {item['at']}s")
    for item in result["brief"]:
        lines.append(f"brief    {item['group']}: {item['word']!r} at {item['at']}s shows for {item['shown']}s, under {MIN_READ}s")
    styles = result["styles"]
    for item in styles["styled"]:
        look = ", ".join(filter(None, [item["level"], f"size {item['size']}", item["bold"] and "bold", item["italic"] and "italic"]))
        lines.append(f"style    {item['group']}: {item['word']!r}: {look}")
    counts = ", ".join(f"{styles[level]} {level}" for level in ("hero", "weight", "tone"))
    problems = sum(len(result[key]) for key in ("overlaps", "clipped", "brief"))
    lines.append(f"{styles['words']} words: {counts}. " + ("Clean." if result["clean"] else f"{problems} problems."))
    print("\n".join(lines))


def _build_plan(audio: str, script: str | None) -> tuple[Plan, dict]:
    _require_ffmpeg()
    for path in (audio, script):
        if path and not Path(path).is_file():
            raise ValueError(f"File not found: {path}")

    samples = decode_audio(audio)
    if script:
        text, unsure = Path(script).read_text(encoding="utf-8"), []
    else:
        print("Listening for the words...", file=sys.stderr)
        text, unsure = dataclasses.astuple(transcribe(samples))
    tokens = tokenize_script(text)
    if not tokens:
        raise ValueError(f"The script has no words: {script}" if script else f"No speech was found in {audio}")

    print(f"Timing {len(tokens)} words...", file=sys.stderr)
    alignment = align_script(tokens, samples)
    doubtful = unsure + alignment.doubtful
    if doubtful:
        print(f"Check these words, which the audio barely supports: {', '.join(doubtful)}", file=sys.stderr)
    plan = draft_plan(audio, alignment.duration, group_phrases(alignment.words))
    return plan, {
        "words_from": "script" if script else "audio",
        "duration": round(plan.duration, 3),
        "groups": len(plan.sections[0]["groups"]),
        "confidence": round(alignment.confidence, 2),
        "doubtful": doubtful,
    }


def _load_checked_plan(path: str) -> Plan:
    _require_ffmpeg()
    plan = load_plan(path)
    if not Path(plan.audio).is_file():
        raise ValueError(f"File not found: {plan.audio}")
    return plan


def _render(plan: Plan, out: str, scale: float = 1.0, start: float = 0.0, end: float | None = None) -> None:
    _require_ffmpeg()
    scene = plan.make_scene()

    def show_progress(done: int, total: int) -> None:
        if done == total or done % scene.look.fps == 0:
            print(f"\rRendering {done}/{total} frames", end="", file=sys.stderr, flush=True)

    render_video(plan.make_scene, plan.audio, out, show_progress, scale, start, end)
    print(f"\nWrote {out}", file=sys.stderr)


def _require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg was not found. Install it (macOS: brew install ffmpeg) and retry.")


if __name__ == "__main__":
    sys.exit(main())
