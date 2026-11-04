"""The scene: a tree of elements whose properties change over time.

Effects write keys onto the tree, and the renderer only reads it, so neither knows the other.
World space has its origin where the camera starts, and y points down.
"""

import math
from dataclasses import dataclass, field
from importlib.resources import files

import skia

FONT_PATH = str(files("kinetic_typography") / "fonts" / "ArchivoBlack-Regular.ttf")
_REFERENCE_SIZE = 100.0

EASES = {
    "linear": lambda u: u,
    "in": lambda u: u**3,
    "out": lambda u: 1 - (1 - u) ** 3,
    "inout": lambda u: 4 * u**3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2,
    "back": lambda u: 1 + 2.70158 * (u - 1) ** 3 + 1.70158 * (u - 1) ** 2,
    "hold": lambda u: 0.0,  # jump at the key, for camera cuts
}

PROPS = {"x": 0.0, "y": 0.0, "rot": 0.0, "scale": 1.0, "opacity": 1.0, "blur": 0.0}


class Node:
    """An element. A property is its base value unless a track of keys overrides it."""

    def __init__(self, parent: "Node | None" = None, **base: float):
        self.parent = parent
        self.children: list[Node] = []
        self.base = dict(PROPS, **base)
        self.tracks: dict[str, list[tuple[float, float, str]]] = {}
        if parent is not None:
            parent.children.append(self)

    def key(self, prop: str, t: float, value: float, ease: str = "inout") -> None:
        """Reach value at time t. The ease shapes the segment arriving at this key."""
        if prop not in self.base:
            raise KeyError(f"{type(self).__name__} has no property {prop!r}. Properties: {', '.join(self.base)}")
        if ease not in EASES:
            raise KeyError(f"Unknown ease {ease!r}. Eases: {', '.join(EASES)}")
        keys = self.tracks.setdefault(prop, [])
        keys.append((t, float(value), ease))
        keys.sort(key=lambda k: k[0])

    def get(self, prop: str, t: float) -> float:
        """The value at time t, held at the first and last keys outside them."""
        keys = self.tracks.get(prop)
        if not keys:
            return self.base[prop]
        if t <= keys[0][0]:
            return keys[0][1]
        for (t0, v0, _), (t1, v1, ease) in zip(keys, keys[1:]):
            if t < t1:
                return v0 + (v1 - v0) * EASES[ease]((t - t0) / (t1 - t0))
        return keys[-1][1]

    def matrix(self, t: float) -> skia.Matrix:
        """Place this node in its parent: translate, then rotate, then scale."""
        m = skia.Matrix.Translate(self.get("x", t), self.get("y", t))
        m.preRotate(self.get("rot", t))
        scale = self.get("scale", t)
        m.preScale(scale, scale)
        return m

    def world_matrix(self, t: float) -> skia.Matrix:
        m = self.matrix(t)
        node = self.parent
        while node is not None:
            m.postConcat(node.matrix(t))
            node = node.parent
        return m

    def opacity(self, t: float) -> float:
        """Opacity after multiplying in every parent's."""
        value, node = 1.0, self
        while node is not None:
            value *= node.get("opacity", t)
            node = node.parent
        return value


class Fonts:
    """One typeface at any size, with measurements that scale with the size."""

    def __init__(self, path: str = FONT_PATH):
        self.typeface = skia.Typeface.MakeFromFile(path)
        if self.typeface is None:
            raise RuntimeError(f"Could not load the font at {path}")
        self._fonts: dict[float, skia.Font] = {}
        self._measured: dict[str, tuple[float, float, float]] = {}
        self.space = self.font(_REFERENCE_SIZE).measureText(" ") / _REFERENCE_SIZE

    def font(self, size: float) -> skia.Font:
        font = self._fonts.get(size)
        if font is None:
            font = skia.Font(self.typeface, size)
            font.setSubpixel(True)
            font.setHinting(skia.FontHinting.kNone)
            font.setEdging(skia.Font.Edging.kAntiAlias)
            self._fonts[size] = font
        return font

    def measure(self, text: str) -> tuple[float, float, float]:
        """Advance width, ink above the baseline and ink below it, at size 1."""
        if text not in self._measured:
            ink = skia.Rect()
            advance = self.font(_REFERENCE_SIZE).measureText(text, skia.TextEncoding.kUTF8, ink)
            self._measured[text] = (advance / _REFERENCE_SIZE, max(0.0, -ink.top() / _REFERENCE_SIZE),
                                    max(0.0, ink.bottom() / _REFERENCE_SIZE))  # fmt: skip
        return self._measured[text]


@dataclass(frozen=True)
class Look:
    """How the whole video appears, apart from its motion."""

    width: int = 1080
    height: int = 1080
    fps: int = 30
    size: float = 64.0  # text size for placements that don't choose one
    line_gap: float = 0.28  # space between one line's ink and the next, relative to text size
    background: tuple[int, int, int] = (17, 17, 17)
    fonts: Fonts = field(default_factory=Fonts, compare=False, repr=False)


@dataclass(frozen=True)
class WordSpec:
    """A spoken word as it should appear: its text, timing and resolved appearance."""

    text: str
    start: float
    end: float
    size: float = 1.0  # relative to its group's text size
    color: tuple[int, int, int] = (245, 245, 240)


@dataclass(frozen=True)
class GroupSpec:
    """Words shown together. The hints are read by whichever effects use them."""

    words: tuple[WordSpec, ...]
    lines: tuple[int, ...] | None = None  # words per line; default one line
    size: float = 1.0  # relative to the look's text size
    align: str = "left"  # of its lines: left, center or right
    section: bool = False  # starts a new section
    at: dict = field(default_factory=dict)  # hints for the place effect
    camera: dict = field(default_factory=dict)  # hints for the camera effect
    arrive: str | dict | None = None  # overrides the default effect for this group
    retire: str | dict | None = None


class Word(Node):
    """A word drawn with its origin at the center of its baseline."""

    def __init__(self, parent: "Group", spec: WordSpec):
        super().__init__(parent)
        self.spec = spec
        self.text, self.start, self.end, self.color = spec.text, spec.start, spec.end, spec.color
        self.font: skia.Font | None = None
        self.width = self.top = self.bottom = 0.0

    def corners(self, t: float) -> list[tuple[float, float]]:
        """The word's ink box at time t, in world space."""
        m = self.world_matrix(t)
        half = self.width / 2
        points = [m.mapXY(x, y) for x, y in ((-half, -self.top), (half, -self.top), (half, self.bottom), (-half, self.bottom))]
        return [(p.x(), p.y()) for p in points]


class Group(Node):
    """Words set in lines, with the group's origin at the center of its box."""

    def __init__(self, parent: Node, spec: GroupSpec, look: Look):
        super().__init__(parent)
        self.spec, self.look = spec, look
        self.words = [Word(self, word) for word in spec.words]
        self.start, self.end = spec.words[0].start, spec.words[-1].end
        self.w = self.h = self.first_baseline = self.last_baseline = 0.0
        self.set_lines(spec.lines or (len(self.words),), look.size * spec.size)

    def line_box(self, lines: tuple[int, ...]) -> tuple[float, float]:
        """Width and height of these lines at size 1, without setting them."""
        rows = self._rows(lines)
        width = max(row[0] for row in rows)
        height = sum(row[1] + row[2] for row in rows) + self.look.line_gap * (len(rows) - 1)
        return width, height

    def set_lines(self, lines: tuple[int, ...], size: float) -> None:
        """Break the words into lines of the given lengths, at a text size."""
        if sum(lines) != len(self.words) or min(lines) < 1:
            raise ValueError(f"lines {list(lines)} don't add up to the group's {len(self.words)} words")
        rows = self._rows(lines)
        self.w, self.h = (value * size for value in self.line_box(lines))
        gap = self.look.line_gap * size
        baseline, first, index = 0.0, None, 0
        for count, (row_width, above, below) in zip(lines, rows):
            baseline += above * size if first is None else gap + above * size
            first = baseline if first is None else first
            x = {"left": 0.0, "center": (self.w - row_width * size) / 2, "right": self.w - row_width * size}[self.spec.align]
            for word in self.words[index : index + count]:
                advance, top, bottom = self.look.fonts.measure(word.text)
                word_size = size * word.spec.size
                word.font = self.look.fonts.font(word_size)
                word.width, word.top, word.bottom = advance * word_size, top * word_size, bottom * word_size
                word.base.update(x=x + word.width / 2 - self.w / 2, y=baseline - self.h / 2)
                x += word.width + self.look.fonts.space * size
            index += count
            baseline += below * size
        self.first_baseline, self.last_baseline = first, baseline - rows[-1][2] * size

    def _rows(self, lines: tuple[int, ...]) -> list[tuple[float, float, float]]:
        """Each line's width, ink above and ink below, at size 1."""
        rows, index = [], 0
        for count in lines:
            measured = [(self.look.fonts.measure(w.text), w.spec.size) for w in self.words[index : index + count]]
            width = sum(m[0] * s for m, s in measured) + self.look.fonts.space * (count - 1)
            rows.append((width, max(m[1] * s for m, s in measured), max(m[2] * s for m, s in measured)))
            index += count
        return rows

    def corners(self) -> list[tuple[float, float]]:
        """The group's box where it rests, in its parent's space."""
        s = self.base["scale"]
        points = [rotate(sx * self.w * s / 2, sy * self.h * s / 2, self.base["rot"]) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        return [(self.base["x"] + x, self.base["y"] + y) for x, y in points]


class Camera(Node):
    """Where the view is centered, how it's turned, and its zoom."""

    def __init__(self):
        super().__init__(zoom=1.0)


@dataclass
class Scene:
    world: Node
    camera: Camera
    groups: list[Group]
    look: Look
    duration: float

    def view(self, t: float, scale: float = 1.0) -> skia.Matrix:
        """World space to pixels at time t. Scale renders at a fraction of full size."""
        c = self.camera
        m = skia.Matrix.Translate(self.look.width * scale / 2, self.look.height * scale / 2)
        zoom = c.get("zoom", t) * scale
        m.preScale(zoom, zoom)
        m.preRotate(-c.get("rot", t))
        m.preTranslate(-c.get("x", t), -c.get("y", t))
        return m

    def on_screen(self, word: Word, t: float) -> list[tuple[float, float]]:
        """The word's ink box at time t, in pixels."""
        m = self.view(t)
        return [(p.x(), p.y()) for p in (m.mapXY(x, y) for x, y in word.corners(t))]


def rotate(x: float, y: float, degrees: float) -> tuple[float, float]:
    a = math.radians(degrees)
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)


def quads_overlap(a: list[tuple[float, float]], b: list[tuple[float, float]], margin: float = 4.0) -> bool:
    """Whether two rotated rectangles come within margin of each other (separating axis test)."""
    for quad in (a, b):
        for i in range(2):
            nx, ny = quad[i][1] - quad[i + 1][1], quad[i + 1][0] - quad[i][0]
            length = math.hypot(nx, ny)
            pa = [x * nx + y * ny for x, y in a]
            pb = [x * nx + y * ny for x, y in b]
            if max(pa) + margin * length <= min(pb) or max(pb) + margin * length <= min(pa):
                return False
    return True
