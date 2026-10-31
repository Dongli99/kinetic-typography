"""Turn phrases into scenes: split each into lines and size it to fill the canvas."""

from importlib.resources import files
from itertools import combinations

import skia

from .model import Phrase, PlacedWord, Scene, Style

FONT_PATH = str(files("kinetic_typography") / "fonts" / "ArchivoBlack-Regular.ttf")
EXTRA_LINE_PENALTY = 0.07
TRIM_CHARS = " ,.;:—-\"“”‘()[]…"
_REFERENCE_SIZE = 100.0


def load_typeface() -> skia.Typeface:
    typeface = skia.Typeface.MakeFromFile(FONT_PATH)
    if typeface is None:
        raise RuntimeError(f"Could not load the font at {FONT_PATH}")
    return typeface


def display_text(token: str) -> str:
    return token.replace("’", "'").strip(TRIM_CHARS).upper()


def build_scenes(phrases: list[Phrase], duration: float, style: Style, typeface=None) -> list[Scene]:
    typeface = typeface or load_typeface()
    font = skia.Font(typeface, _REFERENCE_SIZE)
    scenes = []
    for index, phrase in enumerate(phrases):
        start = max(0.0, phrase.words[0].start - style.lead_in)
        end = min(duration, phrase.words[-1].end + style.hold)
        if index + 1 < len(phrases):
            end = min(end, max(start, phrases[index + 1].words[0].start - style.lead_in))
        scenes.append(Scene(_place_words(phrase, font, style), start, end))
    return scenes


def _place_words(phrase: Phrase, font: skia.Font, style: Style) -> tuple[PlacedWord, ...]:
    texts = [display_text(word.text) for word in phrase.words]
    weights = [
        style.emphasis_scale if index == phrase.emphasis else 1.0 for index in range(len(texts))
    ]
    widths = [font.measureText(text) / _REFERENCE_SIZE * weight for text, weight in zip(texts, weights)]
    space = font.measureText(" ") / _REFERENCE_SIZE
    cap_height = font.getMetrics().fCapHeight / _REFERENCE_SIZE

    lines, size = _best_lines(widths, weights, space, cap_height, style)

    line_heights = [max(weights[i] for i in line) * cap_height * size for line in lines]
    total_height = sum(line_heights) + style.line_gap * size * (len(lines) - 1)
    baseline = -total_height / 2
    placed = []
    for line, line_height in zip(lines, line_heights):
        baseline += line_height
        line_width = (sum(widths[i] for i in line) + space * (len(line) - 1)) * size
        x = -line_width / 2
        for i in line:
            width = widths[i] * size
            placed.append(
                PlacedWord(
                    text=texts[i],
                    x=x,
                    y=baseline,
                    width=width,
                    size=weights[i] * size,
                    start=phrase.words[i].start,
                    emphasized=i == phrase.emphasis,
                )
            )
            x += width + space * size
        baseline += style.line_gap * size
    return tuple(placed)


def _best_lines(widths, weights, space, cap_height, style):
    """Try every way of breaking the phrase and keep the one that reads largest."""
    max_width = style.width - 2 * style.margin
    max_height = style.height - 2 * style.margin
    best = None
    for lines in _partitions(len(widths)):
        widest = max(sum(widths[i] for i in line) + space * (len(line) - 1) for line in lines)
        tallest = sum(max(weights[i] for i in line) * cap_height for line in lines)
        tallest += style.line_gap * (len(lines) - 1)
        size = min(style.max_font_size, max_width / widest, max_height / tallest)
        score = size * (1 - EXTRA_LINE_PENALTY * (len(lines) - 1))
        if best is None or score > best[0]:
            best = (score, lines, size)
    return best[1], best[2]


def _partitions(count: int):
    """Yield every split of word indexes 0..count-1 into consecutive lines."""
    for line_count in range(1, count + 1):
        for cuts in combinations(range(1, count), line_count - 1):
            edges = (0, *cuts, count)
            yield [list(range(edges[i], edges[i + 1])) for i in range(line_count)]
