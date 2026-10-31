"""Command line entry point."""

import argparse
import dataclasses
import json
import shutil
import sys
from importlib.resources import files
from pathlib import Path

from . import __version__
from .align import align_script, decode_audio, tokenize_script
from .layout import build_scenes
from .phrases import group_phrases
from .plan import Plan, load_plan, save_plan
from .render import render_video, save_frame
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

    commands.add_parser("guide", help="Print the guide for AI agents.")

    args = parser.parse_args(argv)
    if args.command == "guide":
        print((files("kinetic_typography") / "guide.md").read_text(encoding="utf-8"))
        return 0

    try:
        result = {"make": run_make, "plan": run_plan, "render": run_render, "frame": run_frame}[args.command](args)
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
    return {"video": args.out, "duration": plan.duration, "phrases": len(plan.phrases)}


def run_frame(args: argparse.Namespace) -> dict:
    plan = load_plan(args.plan)
    style = plan.make_style()
    save_frame(build_scenes(plan.phrases, plan.duration, style), args.at, args.out, style)
    return {"frame": args.out, "at": args.at}


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
    plan = Plan(audio, alignment.duration, group_phrases(alignment.words))
    return plan, {
        "words_from": "script" if script else "audio",
        "duration": round(plan.duration, 3),
        "phrases": len(plan.phrases),
        "confidence": round(alignment.confidence, 2),
        "doubtful": doubtful,
    }


def _load_checked_plan(path: str) -> Plan:
    _require_ffmpeg()
    plan = load_plan(path)
    if not Path(plan.audio).is_file():
        raise ValueError(f"File not found: {plan.audio}")
    return plan


def _render(plan: Plan, out: str) -> None:
    _require_ffmpeg()
    style = plan.make_style()
    scenes = build_scenes(plan.phrases, plan.duration, style)

    def show_progress(done: int, total: int) -> None:
        if done == total or done % style.fps == 0:
            print(f"\rRendering {done}/{total} frames", end="", file=sys.stderr, flush=True)

    render_video(scenes, plan.audio, out, plan.duration, style, show_progress)
    print(f"\nWrote {out}", file=sys.stderr)


def _require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg was not found. Install it (macOS: brew install ffmpeg) and retry.")


if __name__ == "__main__":
    sys.exit(main())
