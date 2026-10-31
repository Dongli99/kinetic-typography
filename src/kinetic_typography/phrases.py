"""Turn timed words into on-screen phrases and pick each phrase's key word.

Breaks are chosen per sentence by minimizing a cost over every possible split, so a good
break later can outweigh a mediocre one now. Emphasis is a best guess: to overrule it, or
any break, edit the plan file.
"""

import re

from .model import Phrase, Word
from .spoken import MAGNITUDES, letters_only, parse_number_words

MAX_WORDS = 5
MAX_CHARS = 30
CLOSING_MARKS = "\"'”’)]"
SENTENCE_MARKS = (".", "!", "?", "…")
CLAUSE_MARKS = (";", ":", "—")
SENTENCE_PAUSE_SECONDS = 0.7
MIN_READ_SECONDS = 0.45

MONTHS = frozenset(
    "january february march april may june july august september october november december".split()
)
STOP_WORDS = frozenset(
    """a about after all also am an and any are as at be because been but by can could did do
    does for from had has have he her here him his how i if in into is it its just like me more
    my no not of on one or our out said says she so some than that the their them then there these
    they this to too up us was we were what when where which who why will with would you your""".split()
)
# A phrase should not end on a word that promises another.
HANGING_WORDS = frozenset(
    """a an the and or but so if that which who because as of in on at to for from with by into
    about across over under after before than is are was were be been has have had can could
    will would should must not no my your our their his her its this these those he she we they
    i you it""".split()
)
OPENING_WORDS = frozenset(
    "in on at for from with by into across over under after before and or but because that which who".split()
)
UNBREAKABLE_COST = 20.0


def merge_numbers(words: list[Word]) -> list[Word]:
    """Rewrite spoken numbers as numerals: "six point three billion dollars" -> "$6.3 billion"."""
    merged = []
    index = 0
    while index < len(words):
        replacement, used = _read_number(words, index)
        if replacement is None:
            merged.append(words[index])
            index += 1
        else:
            merged.append(Word(replacement, words[index].start, words[index + used - 1].end))
            index += used
    return merged


def _read_number(words: list[Word], index: int) -> tuple[str | None, int]:
    keys = _keys_until_clause_end(words, index)
    if not keys:
        return None, 0

    written = re.fullmatch(r"\$?\d[\d,]*(\.\d+)?", words[index].text.rstrip(".,;:!?—"))
    if written:
        # Written as digits already: only a magnitude could join it.
        if _ends_clause(words[index]) or len(keys) < 2 or keys[1] not in MAGNITUDES:
            return None, 0
        return f"{written.group(0)} {keys[1]}{_trailing_marks(words[index + 1].text)}", 2

    parsed = parse_number_words(keys)
    if parsed is None:
        return None, 0
    numeral, used = parsed
    if used < len(keys) and keys[used] in MAGNITUDES:
        numeral = f"{numeral} {keys[used]}"
        used += 1
    if used < len(keys) and keys[used] == "dollars":
        numeral = "$" + numeral
        used += 1
    return numeral + _trailing_marks(words[index + used - 1].text), used


def _keys_until_clause_end(words: list[Word], index: int) -> list[str]:
    keys = []
    for word in words[index:]:
        keys.append(letters_only(word.text))
        if _ends_clause(word):
            break
    return keys


def _ends_clause(word: Word) -> bool:
    return _final_mark(word) in (*SENTENCE_MARKS, *CLAUSE_MARKS, ",")


def _trailing_marks(text: str) -> str:
    return text[len(text.rstrip(".,;:!?—\"'”’)]…")) :]


def _final_mark(word: Word) -> str:
    return word.text.rstrip(CLOSING_MARKS)[-1:]


def group_phrases(words: list[Word]) -> list[Phrase]:
    words = merge_numbers(words)
    seen: set[str] = set()
    phrases = []
    for sentence in _split_sentences(words):
        for group in _best_split(sentence):
            phrases.append(Phrase(tuple(group), _pick_emphasis(group, sentence, seen)))
            seen.update(_key(word) for word in group)
    return phrases


def _split_sentences(words: list[Word]) -> list[list[Word]]:
    sentences, current = [], []
    for index, word in enumerate(words):
        current.append(word)
        following = words[index + 1] if index + 1 < len(words) else None
        long_pause = following is not None and following.start - word.end >= SENTENCE_PAUSE_SECONDS
        if following is None or _final_mark(word) in SENTENCE_MARKS or long_pause:
            sentences.append(current)
            current = []
    return sentences


def _best_split(sentence: list[Word]) -> list[list[Word]]:
    count = len(sentence)
    best = [0.0] + [float("inf")] * count
    previous = [0] * (count + 1)
    for stop in range(1, count + 1):
        for start in range(max(0, stop - MAX_WORDS), stop):
            group = sentence[start:stop]
            if len(group) > 1 and sum(len(word.text) for word in group) + len(group) - 1 > MAX_CHARS:
                continue
            cost = best[start] + _phrase_cost(group)
            if stop < count:
                cost += _break_cost(sentence, stop - 1)
            if cost < best[stop]:
                best[stop] = cost
                previous[stop] = start
    groups = []
    stop = count
    while stop > 0:
        groups.append(sentence[previous[stop] : stop])
        stop = previous[stop]
    groups.reverse()
    return groups


def _phrase_cost(group: list[Word]) -> float:
    cost = {1: 1.5, 2: 0.3, 3: 0.0, 4: 0.0, 5: 0.6}[len(group)]
    seconds = group[-1].end - group[0].start
    if seconds < MIN_READ_SECONDS:
        cost += 2.0 * (MIN_READ_SECONDS - seconds) / MIN_READ_SECONDS
    return cost


def _break_cost(sentence: list[Word], index: int) -> float:
    """Cost of ending a phrase after sentence[index]. Negative means a break is welcome."""
    word, following = sentence[index], sentence[index + 1]
    key, next_key = _key(word), _key(following)
    possessive = key.endswith("'s")
    if not _ends_clause(word):
        if _is_name(sentence, index) and _is_name(sentence, index + 1) and not possessive:
            return UNBREAKABLE_COST
        if key in MONTHS and _is_numeric(following):
            return UNBREAKABLE_COST
        # A bare count belongs with what it counts: "20 minutes", but not "$6.3 billion left".
        if _is_numeric(word) and " " not in word.text and next_key not in OPENING_WORDS:
            return UNBREAKABLE_COST

    cost = 0.0
    mark = _final_mark(word)
    if mark in CLAUSE_MARKS:
        cost -= 3.0
    elif mark == ",":
        cost -= 1.0
    elif key in HANGING_WORDS:
        cost += 3.0
    elif possessive:
        cost += 2.0
    if next_key in OPENING_WORDS:
        cost -= 1.0

    pause = following.start - word.end
    if pause >= 0.35:
        cost -= 4.0
    elif pause >= 0.2:
        cost -= 2.0
    return cost


def _is_name(sentence: list[Word], index: int) -> bool:
    """A capitalized word. The sentence's first word only counts if it isn't an ordinary word."""
    text = sentence[index].text.lstrip("\"“(")
    if not text[:1].isupper():
        return False
    return index > 0 or _key(sentence[index]) not in STOP_WORDS and text.isupper()


def _is_numeric(word: Word) -> bool:
    return any(character.isdigit() for character in word.text)


def _key(word: Word) -> str:
    return letters_only(word.text) or word.text


def _pick_emphasis(group: list[Word], sentence: list[Word], seen: set[str]) -> int | None:
    scores = {}
    for index, word in enumerate(group):
        key = _key(word)
        if key in STOP_WORDS:
            continue
        score = 1.0 + min(len(key), 12) * 0.05
        if _is_numeric(word):
            after_month = index > 0 and _key(group[index - 1]) in MONTHS
            score += 0.5 if after_month else 3.0
        if key in seen:
            score -= 1.2
        scores[index] = score
    if not scores:
        return None
    # English tends to put the point at the end of a phrase.
    last = max(scores)
    scores[last] += 0.8
    chosen = max(scores, key=lambda index: (scores[index], index))
    if len(group) == 1 and not _is_numeric(group[chosen]):
        return None
    return chosen
