"""Draw a scene to frames and encode them with the audio into an MP4.

The renderer walks the tree and knows no effect by name.
"""

import math
import multiprocessing
from collections import deque
import os
import subprocess
import tempfile
from functools import cache
from pathlib import Path

import numpy as np
import skia

from .scene import Node, Scene, Word, fonts_for

PREVIEW_SCALE = 0.5  # of full size, for clips
TILE_WIDTH = 320  # pixels, for contact sheets
COLUMNS = 6
LABEL = 22  # pixels of label under each tile
PARALLEL_FROM = 90  # frames; fewer are quicker drawn than shared out
TOASTED = (120, 82, 50)  # the paper's color at its corners
SHUTTER = 0.5  # of a frame's time, for motion blur
MAX_SAMPLES = 10
PIXELS_PER_SAMPLE = 3.0  # how far the picture may move between sub-frames


class FrameRenderer:
    def __init__(self, scene: Scene, scale: float = 1.0):
        self.scene, self.scale = scene, scale
        look = scene.look
        self.background = skia.Color(*look.background)
        self.size = (_even(look.width * scale), _even(look.height * scale))  # video encoders need even sizes
        self.paper = make_paper(*self.size, look.background, scale) if look.paper else None
        self.pixels = np.zeros((self.size[1], self.size[0], 4), dtype=np.uint8)
        self.surface = skia.Surface(self.pixels)

    def draw(self, t: float) -> np.ndarray:
        """Draw the frame at time t and return its RGBA pixels.

        While the camera moves, the frame averages sub-frames across a half-frame shutter, as a film camera blurs.
        """
        samples = self.samples(t)
        with self.surface as canvas:
            canvas.resetMatrix()  # the canvas keeps the last frame's camera
            if self.paper is None:
                canvas.clear(self.background)
            else:
                canvas.drawImage(self.paper, 0, 0)
            if samples == 1:
                canvas.setMatrix(self.scene.view(t, self.scale))
                self._walk(canvas, self.scene.world, t, 1.0)
                return self.pixels
            canvas.saveLayer()  # the sum of the sub-frames, which then goes over the background
            share = skia.Paint(Alphaf=1 / samples, BlendMode=skia.BlendMode.kPlus)
            for k in range(samples):
                at = t - SHUTTER / self.scene.look.fps * k / (samples - 1)
                canvas.saveLayer(paint=share)
                canvas.setMatrix(self.scene.view(at, self.scale))
                self._walk(canvas, self.scene.world, at, 1.0)
                canvas.restore()
            canvas.restore()
        return self.pixels

    def samples(self, t: float) -> int:
        """How many sub-frames the camera's motion across the shutter needs, from how far pixels travel."""
        now, before = self.scene.view(t, self.scale), self.scene.view(t - SHUTTER / self.scene.look.fps, self.scale)
        back = skia.Matrix()
        if not now.invert(back):
            return 1
        w, h = self.size
        worst = 0.0
        for x, y in ((0, 0), (w, 0), (0, h), (w, h), (w / 2, h / 2)):
            p = back.mapXY(x, y)
            q = before.mapXY(p.x(), p.y())
            worst = max(worst, math.hypot(q.x() - x, q.y() - y))
        return max(1, min(MAX_SAMPLES, math.ceil(worst / PIXELS_PER_SAMPLE)))

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


@cache
def make_paper(width: int, height: int, color: tuple[int, int, int], scale: float) -> skia.Image:
    """Paper of a color: faint mottling and grain, toasting toward the corners. The same every time."""
    rng = np.random.default_rng(7)
    cell = max(2, round(60 * scale))
    coarse = rng.normal(0, 1, (height // cell + 2, width // cell + 2)).astype(np.float32)
    yi, xi = np.linspace(0, coarse.shape[0] - 1.001, height), np.linspace(0, coarse.shape[1] - 1.001, width)
    y0, x0 = yi.astype(int), xi.astype(int)
    fy, fx = (yi - y0)[:, None], (xi - x0)[None, :]
    mottle = (coarse[y0][:, x0] * (1 - fy) * (1 - fx) + coarse[y0 + 1][:, x0] * fy * (1 - fx)
              + coarse[y0][:, x0 + 1] * (1 - fy) * fx + coarse[y0 + 1][:, x0 + 1] * fy * fx)  # fmt: skip
    grain = rng.normal(0, 1, (height, width)).astype(np.float32)
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    corner = np.hypot((xx - width / 2) / (width / 2), (yy - height / 2) / (height / 2)) / math.sqrt(2)
    burn = (np.clip((corner - 0.45) / 0.55, 0, 1) ** 1.8 * 0.75)[..., None]  # 0 in the middle
    paper = np.array(color, np.float32) * (1 - burn) + np.array(TOASTED, np.float32) * burn
    paper += (mottle * 3.5 + grain * 2.5)[..., None]
    pixels = np.dstack([np.clip(paper, 0, 255).astype(np.uint8), np.full((height, width), 255, np.uint8)])
    return skia.Image.fromarray(pixels)


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


def render_video(make_scene, audio_path: str, output_path: str, on_progress=None,
                 scale: float = 1.0, start: float = 0.0, end: float | None = None) -> None:  # fmt: skip
    """The video from start to end seconds, at a fraction of full size.

    make_scene is a function that can be sent to other processes, such as a plan's make_scene, so that
    each process builds its own scene and draws its share of the frames.
    """
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    scene = make_scene()
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
    times = [(first + frame) / look.fps for frame in range(frame_count)]
    workers = min(os.cpu_count() or 1, 8) if frame_count >= PARALLEL_FROM else 1

    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=errors)
        try:
            if workers == 1:
                frames = (renderer.draw(t) for t in times)
            else:
                frames = _draw_in_parallel(make_scene, scale, renderer.pixels.shape, times, workers)
            for index, frame in enumerate(frames):
                process.stdin.write(memoryview(frame))
                if on_progress:
                    on_progress(index + 1, frame_count)
            process.stdin.close()
        except BrokenPipeError:
            pass
        code = process.wait()
        if code != 0:
            errors.seek(0)
            message = errors.read().decode(errors="replace").strip()
            raise RuntimeError(f"ffmpeg failed: {message}")


def _draw_in_parallel(make_scene, scale: float, shape: tuple, times: list[float], workers: int):
    """Each frame in order, drawn by worker processes into slots of a shared file, which saves copying them."""
    slots = 2 * workers
    with tempfile.NamedTemporaryFile() as shared:
        shared.truncate(slots * math.prod(shape))
        frames = np.memmap(shared.name, np.uint8, "r+", shape=(slots, *shape))
        context = multiprocessing.get_context("spawn")  # the same on every platform
        with context.Pool(workers, _start_worker, (make_scene, scale, shared.name, frames.shape)) as pool:
            pending = deque()
            for index, t in enumerate(times):
                if len(pending) == slots:  # wait for the oldest, whose slot this frame reuses
                    slot, result = pending.popleft()
                    result.get()
                    yield frames[slot]
                pending.append((index % slots, pool.apply_async(_draw_in_worker, (t, index % slots))))
            while pending:
                slot, result = pending.popleft()
                result.get()
                yield frames[slot]


_worker: tuple | None = None  # this process's renderer and the shared slots


def _start_worker(make_scene, scale: float, path: str, shape: tuple) -> None:
    global _worker
    _worker = (FrameRenderer(make_scene(), scale), np.memmap(path, np.uint8, "r+", shape=shape))


def _draw_in_worker(t: float, slot: int) -> None:
    renderer, frames = _worker
    frames[slot] = renderer.draw(t)


def _even(pixels: float) -> int:
    return max(2, 2 * round(pixels / 2))
