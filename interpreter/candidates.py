"""Candidate generation — the part Jev cannot do.

Jev only picks from options we give it, so for every suspicious token we
build a bounded list of plausible intended words from the glossary using
orthographic + phonetic similarity, including merges of two adjacent tokens
("до бага" -> "дебаг").
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

WORD_RE = re.compile(r"\w+|[^\w\s]+", re.UNICODE)

# Words too short/common to be worth a question. Kept deliberately small;
# the caller can pass extra `ignore` words.
STOPWORDS = {
    "и", "в", "во", "не", "на", "с", "со", "что", "это", "как", "но", "или",
    "то", "же", "бы", "ли", "по", "из", "за", "от", "до", "для", "у", "о", "об",
    "а", "я", "ты", "он", "она", "мы", "вы", "они", "все", "всё", "так", "там",
    "тут", "еще", "ещё", "уже", "вот", "да", "нет", "если", "когда", "чтобы",
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "is", "it", "for",
}

_PHONETIC_RU = [
    (r"[ъь]", ""),
    (r"тс|тьс|дс", "ц"),
    (r"щ", "ш"),
    (r"ё", "о"),
    (r"[ыий]", "и"),
    (r"[эе]", "е"),
    (r"я", "а"),
    (r"ю", "у"),
    (r"о", "а"),      # unstressed vowel reduction, crude but useful for ASR errors
    (r"(.)\1+", r"\1"),
]


# Rough Latin -> Cyrillic transliteration so "MCP"/"мцп", "debug"/"дебак",
# "listener"/"лисенер" compare in one alphabet. Multi-letter rules first.
_TRANSLIT = [
    ("sch", "ш"), ("sh", "ш"), ("ch", "ч"), ("th", "т"), ("ph", "ф"), ("ck", "к"),
    ("ee", "и"), ("oo", "у"), ("ea", "и"), ("ou", "ау"), ("qu", "кв"),
    ("a", "а"), ("b", "б"), ("c", "к"), ("d", "д"), ("e", "е"), ("f", "ф"), ("g", "г"),
    ("h", "х"), ("i", "и"), ("j", "дж"), ("k", "к"), ("l", "л"), ("m", "м"), ("n", "н"),
    ("o", "о"), ("p", "п"), ("q", "к"), ("r", "р"), ("s", "с"), ("t", "т"), ("u", "у"),
    ("v", "в"), ("w", "в"), ("x", "кс"), ("y", "и"), ("z", "з"),
]


def transliterate(word: str) -> str:
    w = word.lower()
    if not re.search(r"[a-z]", w):
        return w
    for src, dst in _TRANSLIT:
        w = w.replace(src, dst)
    return w


def phonetic_key(word: str) -> str:
    w = transliterate(word)
    for pat, rep in _PHONETIC_RU:
        w = re.sub(pat, rep, w)
    return w


def similarity(a: str, b: str) -> float:
    """0..1 — max of raw and phonetic similarity."""
    a, b = a.lower(), b.lower()
    raw = fuzz.ratio(a, b) / 100.0
    lit = fuzz.ratio(transliterate(a), transliterate(b)) / 100.0
    phon = fuzz.ratio(phonetic_key(a), phonetic_key(b)) / 100.0
    return max(raw, lit, phon)


@dataclass(frozen=True)
class Token:
    text: str
    start: int
    end: int

    @property
    def is_word(self) -> bool:
        return bool(re.match(r"\w", self.text))


def tokenize(text: str) -> list[Token]:
    return [Token(m.group(), m.start(), m.end()) for m in WORD_RE.finditer(text)]


def checkable_indices(tokens: list[Token], ignore: set[str] | None = None) -> list[int]:
    ignore = {w.lower() for w in (ignore or set())} | STOPWORDS
    return [
        i for i, t in enumerate(tokens)
        if t.is_word and len(t.text) >= 3 and t.text.lower() not in ignore and not t.text.isdigit()
    ]


@dataclass(frozen=True)
class Candidate:
    text: str          # replacement text
    start: int         # first token index it replaces
    span: int          # how many tokens it replaces (1 or 2)
    score: float       # our fuzzy score, used as a hint / tie-breaker only


def generate(
    tokens: list[Token],
    index: int,
    glossary: list[str],
    *,
    min_score: float = 0.6,
    limit: int = 6,
    merge_min_score: float = 0.6,
) -> list[Candidate]:
    """Glossary terms similar to tokens[index], or to it merged with a neighbour.

    Merging covers ASR splitting one word into two: "до бага" -> "дебаг" must be
    found whether the flagged token is "до" or "бага".
    """
    word = tokens[index].text
    known = {g.lower() for g in glossary}

    def mergeable(j: int) -> bool:
        # never swallow a neighbour that is already a correct glossary term
        return 0 <= j < len(tokens) and tokens[j].is_word and tokens[j].text.lower() not in known

    windows: list[tuple[str, int, int]] = [(word, index, 1)]
    if mergeable(index + 1):
        windows.append((word + tokens[index + 1].text, index, 2))
    if mergeable(index - 1):
        windows.append((tokens[index - 1].text + word, index - 1, 2))

    found: dict[str, Candidate] = {}
    for term in glossary:
        if term.lower() == word.lower():
            continue
        for text, start, span in windows:
            s = similarity(text, term)
            # merged windows must clear the stricter bar: a loose match that
            # swallows a neighbour ("Некто обременение" -> "общение") is worse than none
            if s < (merge_min_score if span > 1 else min_score):
                continue
            if s > found.get(term, Candidate(term, start, span, -1.0)).score:
                found[term] = Candidate(term, start, span, s)

    return sorted(found.values(), key=lambda c: c.score, reverse=True)[:limit]


def best_glossary_score(tokens: list[Token], index: int, glossary: list[str]) -> float:
    cands = generate(tokens, index, glossary, min_score=0.0, limit=1)
    return cands[0].score if cands else 0.0
