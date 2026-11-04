"""Draw a scene to frames and encode them with the audio into an MP4.

The renderer walks the tree and knows no effect by name.
"""

import math
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import skia

from .scene import Node, Scene, Word


class FrameRenderer:
    def __init__(self, scene: Scene):
        self.scene = scene
        look = scene.look
        self.background = skia.Color(*look.background)
        self.pixels = np.zeros((look.height, look.width, 4), dtype=np.uint8)
        self.surface = skia.Surface(self.pixels)

    def draw(self, t: float) -> np.ndarray:
        """Draw the frame at time t and return its RGBA pixels."""
        with self.surface as canvas:
            canvas.clear(self.background)
            canvas.setMatrix(self.scene.view(t))
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


def render_video(scene: Scene, audio_path: str, output_path: str, on_progress=None) -> None:
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    look = scene.look
    frame_count = math.ceil(scene.duration * look.fps)
    renderer = FrameRenderer(scene)
    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgba",
        "-s", f"{look.width}x{look.height}", "-r", str(look.fps), "-i", "-",
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
            for frame in range(frame_count):
                process.stdin.write(renderer.draw(frame / look.fps).tobytes())
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
