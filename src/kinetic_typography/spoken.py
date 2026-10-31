"""How script words sound and how spoken numbers should read on screen."""

import re

ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
MAGNITUDES = ("thousand", "million", "billion", "trillion")
ORDINALS = {
    "one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth",
    "nine": "ninth", "twelve": "twelfth", "twenty": "twentieth", "thirty": "thirtieth",
    "forty": "fortieth", "fifty": "fiftieth", "sixty": "sixtieth", "seventy": "seventieth",
    "eighty": "eightieth", "ninety": "ninetieth",
}  # fmt: skip

_WORD_VALUES = {word: value for value, word in enumerate(ONES)}
_TENS_VALUES = {word: value * 10 for value, word in enumerate(TENS) if word != "_"}
_COMPOUND_VALUES = {  # "twenty-six" arrives as one script token
    tens + ones: _TENS_VALUES[tens] + _WORD_VALUES[ones]
    for tens in _TENS_VALUES
    for ones in ONES[1:10]
}
_NUMBER = re.compile(r"^(\$?)(\d[\d,]*)(\.\d+)?(%?)$")
_ORDINAL = re.compile(r"^(\d[\d,]*)(st|nd|rd|th)$")


def letters_only(word: str) -> str:
    word = word.lower().replace("’", "'")
    return re.sub(r"[^a-z']", "", word).strip("'")


def spell_integer(value: int) -> list[str]:
    if value < 20:
        return [ONES[value]]
    if value < 100:
        return [TENS[value // 10]] + ([ONES[value % 10]] if value % 10 else [])
    if value < 1000:
        rest = spell_integer(value % 100) if value % 100 else []
        return [ONES[value // 100], "hundred"] + rest
    for power, name in zip((10**12, 10**9, 10**6, 10**3), reversed(MAGNITUDES)):
        if value >= power:
            rest = spell_integer(value % power) if value % power else []
            return spell_integer(value // power) + [name] + rest
    raise ValueError(value)


def _spell_year(value: int) -> list[str]:
    high, low = value // 100, value % 100
    if low == 0:
        return spell_integer(high) + ["hundred"]
    if low < 10:
        return spell_integer(high) + ["oh"] + spell_integer(low)
    return spell_integer(high) + spell_integer(low)


def _spell_ordinal(value: int) -> list[str]:
    words = spell_integer(value)
    last = words[-1]
    words[-1] = ORDINALS.get(last, last + "th")
    return words


def spoken_words(tokens: list[str]) -> list[list[str]]:
    """Return the letters-only words each script token is expected to sound like."""
    spoken: list[list[str]] = []
    dollars_after_next = False
    for index, token in enumerate(tokens):
        bare = token.replace("’", "'").strip(".,;:!?—\"“”()[]…'")
        following = letters_only(tokens[index + 1]) if index + 1 < len(tokens) else ""
        number = _NUMBER.match(bare)
        ordinal = _ORDINAL.match(bare.lower())
        if number:
            currency, whole, fraction, percent = number.groups()
            value = int(whole.replace(",", ""))
            is_year = "," not in whole and 1100 <= value <= 2099 and not (currency or fraction or percent)
            words = _spell_year(value) if is_year else spell_integer(value)
            if fraction:
                words += ["point"] + [ONES[int(digit)] for digit in fraction[1:]]
            if percent:
                words.append("percent")
            if currency:
                if following in MAGNITUDES:
                    dollars_after_next = True  # "$6.3 billion" is said "six point three billion dollars"
                else:
                    words.append("dollars")
            spoken.append(words)
            continue
        if ordinal:
            spoken.append(_spell_ordinal(int(ordinal.group(1).replace(",", ""))))
            continue
        word = letters_only(bare)
        words = [word] if word else []
        if dollars_after_next:
            words.append("dollars")
            dollars_after_next = False
        spoken.append(words)
    return spoken


def _read_below_hundred(words: list[str], index: int) -> tuple[int, int] | None:
    if index >= len(words):
        return None
    word = words[index]
    if word in _COMPOUND_VALUES:
        return _COMPOUND_VALUES[word], index + 1
    if word in _TENS_VALUES:
        following = _WORD_VALUES.get(words[index + 1], 0) if index + 1 < len(words) else 0
        if 0 < following < 10:
            return _TENS_VALUES[word] + following, index + 2
        return _TENS_VALUES[word], index + 1
    if word in _WORD_VALUES:
        return _WORD_VALUES[word], index + 1
    return None


def _read_below_thousand(words: list[str], index: int) -> tuple[int, int] | None:
    read = _read_below_hundred(words, index)
    if read is None:
        return None
    value, index = read
    if index < len(words) and words[index] == "hundred" and 0 < value < 10:
        index += 1
        if index < len(words) and words[index] == "and":
            rest = _read_below_hundred(words, index + 1)
        else:
            rest = _read_below_hundred(words, index)
        if rest is None:
            return value * 100, index
        return value * 100 + rest[0], rest[1]
    return value, index


def parse_number_words(words: list[str]) -> tuple[str, int] | None:
    """Read number words from the start of `words` as a numeral.

    Returns the numeral text and how many words it used, or None if they should stay
    spelled out. Small whole numbers stay as words because they read better that way:
    "one copied key" is not "1 COPIED KEY".
    """
    read = _read_below_thousand(words, 0)
    if read is None:
        return None
    value, index = read

    # A year is said as two numbers: "twenty twenty six", "nineteen ninety".
    if 10 <= value <= 20:
        second = _read_below_hundred(words, index)
        if second is not None and 10 <= second[0] <= 99:
            return f"{value}{second[0]}", second[1]

    if index < len(words) and words[index] == "thousand" and value > 0:
        index += 1
        value *= 1000
        rest = _read_below_thousand(words, index)
        if rest is not None:
            value += rest[0]
            index = rest[1]

    fraction = ""
    if index + 1 < len(words) and words[index] == "point":
        cursor = index + 1
        while cursor < len(words) and _WORD_VALUES.get(words[cursor], 10) < 10:
            fraction += str(_WORD_VALUES[words[cursor]])
            cursor += 1
        if fraction:
            index = cursor

    following = words[index] if index < len(words) else ""
    if value < 10 and not fraction and following not in MAGNITUDES:
        return None
    numeral = f"{value:,}" if value >= 10000 else str(value)
    return numeral + (f".{fraction}" if fraction else ""), index
