"""Draw a scene to frames and encode them with the audio into an MP4.

The renderer walks the tree and knows no effect by name.
"""

import math
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import skia

from .scene import Node, Scene, Word, fonts_for

PREVIEW_SCALE = 0.5  # of full size, for clips
TILE_WIDTH = 320  # pixels, for contact sheets
COLUMNS = 6
LABEL = 22  # pixels of label under each tile


class FrameRenderer:
    def __init__(self, scene: Scene, scale: float = 1.0):
        self.scene, self.scale = scene, scale
        look = scene.look
        self.background = skia.Color(*look.background)
        self.size = (_even(look.width * scale), _even(look.height * scale))  # video encoders need even sizes
        self.pixels = np.zeros((self.size[1], self.size[0], 4), dtype=np.uint8)
        self.surface = skia.Surface(self.pixels)

    def draw(self, t: float) -> np.ndarray:
        """Draw the frame at time t and return its RGBA pixels."""
        with self.surface as canvas:
            canvas.clear(self.background)
            canvas.setMatrix(self.scene.view(t, self.scale))
            self._walk(canvas, self.scene.world, t, 1.0)
        return self.pixels

    def _walk(self, canvas: skia.Canvas, node: Node, t: float, alpha: float) -> None:
        alpha *= node.get("opacity", t)
        if alpha < 0.002:
            return
        canvas.save()
        canvas.concat(node.matrix(t))
        if isinstance(node, Word):
            paint = skia.Paint(AntiAlias=True, Color=skia.Color(*node.color, round(alpha * 255)))
            blur = node.get("blur", t)
            if blur > 0.2:
                paint.setImageFilter(skia.ImageFilters.Blur(blur, blur * 0.4))
            canvas.drawString(node.text, -node.width / 2, 0, node.font, paint)
        for child in node.children:
            self._walk(canvas, child, t, alpha)
        canvas.restore()


def save_frame(scene: Scene, t: float, output_path: str) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    renderer = FrameRenderer(scene)
    renderer.draw(t)
    renderer.surface.makeImageSnapshot().save(output_path, skia.kPNG)


def save_sheet(scene: Scene, tiles: list[tuple[str, float]], output_path: str) -> None:
    """A contact sheet: a small frame for each (label, time), in rows, each labelled underneath."""
    renderer = FrameRenderer(scene, TILE_WIDTH / scene.look.width)
    tw, th = renderer.size
    columns = min(COLUMNS, len(tiles))
    rows = -(-len(tiles) // columns)
    gap = 4
    sheet = np.full((rows * (th + LABEL + gap), columns * (tw + gap), 4), 255, np.uint8)
    sheet[..., :3] = 48
    font = fonts_for("EB Garamond").font(15)
    paint = skia.Paint(AntiAlias=True, Color=skia.Color(230, 230, 225))
    surface = skia.Surface(sheet)
    with surface as canvas:
        for index, (label, t) in enumerate(tiles):
            x, y = (index % columns) * (tw + gap), (index // columns) * (th + LABEL + gap)
            frame = renderer.draw(t)
            canvas.drawImage(skia.Image.fromarray(frame.copy()), x, y)
            canvas.drawString(f"{label}  {t:.2f}s", x + 4, y + th + 16, font, paint)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    surface.makeImageSnapshot().save(output_path, skia.kPNG)


def render_video(scene: Scene, audio_path: str, output_path: str, on_progress=None,
                 scale: float = 1.0, start: float = 0.0, end: float | None = None) -> None:  # fmt: skip
    """The video from start to end seconds, at a fraction of full size."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    look = scene.look
    end = scene.duration if end is None else end
    first, frame_count = math.ceil(start * look.fps), math.ceil(end * look.fps) - math.ceil(start * look.fps)
    renderer = FrameRenderer(scene, scale)
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgba",
        "-s", f"{renderer.size[0]}x{renderer.size[1]}", "-r", str(look.fps), "-i", "-",
        "-ss", f"{first / look.fps:.3f}", "-t", f"{frame_count / look.fps:.3f}", "-i", audio_path,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        output_path,
    ]  # fmt: skip

    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=errors)
        try:
            for frame in range(frame_count):
                process.stdin.write(renderer.draw((first + frame) / look.fps).tobytes())
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


def _even(pixels: float) -> int:
    return max(2, 2 * round(pixels / 2))
