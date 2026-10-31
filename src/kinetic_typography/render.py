"""Draw scenes to frames and encode them with the audio into an MP4."""

import math
import subprocess
import tempfile
from bisect import bisect_right
from pathlib import Path

import numpy as np
import skia

from .animate import camera_at, word_state
from .layout import load_typeface
from .model import Scene, Style


class FrameRenderer:
    def __init__(self, style: Style, typeface=None):
        self.style = style
        self.typeface = typeface or load_typeface()
        self.pixels = np.zeros((style.height, style.width, 4), dtype=np.uint8)
        self.surface = skia.Surface(self.pixels)
        self.fonts: dict[float, skia.Font] = {}

    def draw(self, scene: Scene | None, t: float) -> np.ndarray:
        """Draw the frame at time t and return its RGBA pixels."""
        style = self.style
        camera = camera_at(t)
        with self.surface as canvas:
            canvas.clear(skia.Color(*style.background))
            if scene is None:
                return self.pixels
            canvas.save()
            canvas.translate(style.width / 2, style.height / 2)
            canvas.scale(camera.zoom, camera.zoom)
            canvas.translate(-camera.x, -camera.y)
            for word in scene.words:
                state = word_state(word, scene, t, style)
                if state is None:
                    continue
                color = style.accent if word.emphasized else style.foreground
                paint = skia.Paint(
                    AntiAlias=True,
                    Color=skia.Color(*color, round(state.opacity * 255)),
                )
                center_x = word.x + word.width / 2
                canvas.save()
                canvas.translate(center_x, word.y + state.y_offset)
                canvas.scale(state.scale, state.scale)
                canvas.drawString(word.text, -word.width / 2, 0, self._font(word.size), paint)
                canvas.restore()
            canvas.restore()
        return self.pixels

    def _font(self, size: float) -> skia.Font:
        font = self.fonts.get(size)
        if font is None:
            font = skia.Font(self.typeface, size)
            font.setSubpixel(True)
            font.setHinting(skia.FontHinting.kNone)
            font.setEdging(skia.Font.Edging.kAntiAlias)
            self.fonts[size] = font
        return font


def _scene_at(scenes: list[Scene], starts: list[float], t: float) -> Scene | None:
    index = bisect_right(starts, t) - 1
    if index >= 0 and t < scenes[index].end:
        return scenes[index]
    return None


def save_frame(scenes: list[Scene], t: float, output_path: str, style: Style) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    renderer = FrameRenderer(style)
    renderer.draw(_scene_at(scenes, [scene.start for scene in scenes], t), t)
    renderer.surface.makeImageSnapshot().save(output_path, skia.kPNG)


def render_video(
    scenes: list[Scene],
    audio_path: str,
    output_path: str,
    duration: float,
    style: Style,
    on_progress=None,
) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    frame_count = math.ceil(duration * style.fps)
    renderer = FrameRenderer(style)
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgba",
        "-s", f"{style.width}x{style.height}", "-r", str(style.fps), "-i", "-",
        "-i", audio_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        output_path,
    ]  # fmt: skip

    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=errors)
        try:
            starts = [scene.start for scene in scenes]
            for frame in range(frame_count):
                t = frame / style.fps
                process.stdin.write(renderer.draw(_scene_at(scenes, starts, t), t).tobytes())
                if on_progress:
                    on_progress(frame + 1, frame_count)
            process.stdin.close()
        except BrokenPipeError:
            pass
        code = process.wait()
        if code != 0:
            errors.seek(0)
            message = errors.read().decode(errors="replace").strip()
            raise RuntimeError(f"ffmpeg failed: {message}")
