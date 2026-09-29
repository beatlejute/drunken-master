"""Interpretation pipeline.

    message ──► tokenize ──► code: glossary candidates per word (fuzzy + phonetic
            + transliteration + adjacent-token merge)
            ──► Jev, ONE request:
                  Choice per word that has candidates: {candidates…, keep_original}
                  Noul  per word that has none:       "is this misrecognised?" (→ unresolved)
            ──► code: beam over per-word distributions ──► top-k variants
            ──► code: needs_clarification from the top variant's probability

Jev never generates text; all wording comes from the glossary the caller
(the agent) supplies. Arithmetic stays in code, per the Jev guidance.

Why no separate "is this word corrupted?" step: a bare yes/no on a word sat
around 0.5 for real errors and flipped between runs, while a Choice that shows
Jev the concrete replacement ("дебак" vs "дебаг") is stable. Why no final
Choice between whole sentences: it disagreed with the per-word answers and
mostly preferred the untouched text.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field, asdict
from typing import Any

from . import candidates as C
from .jev import JevBackend, choice, noul, strip_hints, FakeJev

KEEP = "keep_original"


@dataclass
class Change:
    position: int          # first token index replaced
    original: str
    replacement: str
    probability: float


@dataclass
class Variant:
    text: str
    probability: float               # product of per-word probabilities, renormalised
    changes: list[Change] = field(default_factory=list)


@dataclass
class Flagged:
    """A word Jev thinks was misrecognised and for which we had a replacement."""
    position: int
    word: str
    p_corrupted: float               # 1 - P(keep_original)
    candidates: list[str]


@dataclass
class Unresolved:
    """A word Jev thinks was misrecognised but the glossary offers nothing for.

    The agent should extend `glossary` (or `guesses`) and call again.
    """
    position: int
    word: str
    p_corrupted: float


@dataclass
class Interpretation:
    original: str
    variants: list[Variant]
    flagged: list[Flagged]
    unresolved: list[Unresolved]
    needs_clarification: bool
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Interpreter:
    def __init__(
        self,
        backend: JevBackend,
        *,
        corrupted_threshold: float = 0.5,
        max_variants: int = 3,
        auto_apply_confidence: float = 0.75,
    ):
        self.backend = backend
        self.corrupted_threshold = corrupted_threshold
        self.max_variants = max_variants
        self.auto_apply_confidence = auto_apply_confidence

    def _ask(self, state: Any, questions: dict[str, dict]) -> dict[str, dict]:
        if not questions:
            return {}
        if isinstance(self.backend, FakeJev):
            return self.backend.ask(state, questions)
        return self.backend.ask(state, strip_hints(questions))

    def interpret(
        self,
        message: str,
        glossary: list[str],
        context: str | None = None,
        ignore: list[str] | None = None,
        guesses: list[str] | None = None,
    ) -> Interpretation:
        tokens = C.tokenize(message)
        words = [t.text for t in tokens]
        idxs = C.checkable_indices(tokens, set(ignore or []))
        guesses = [g for g in (guesses or []) if g not in glossary]
        speculative = {g.lower() for g in guesses}
        state: dict[str, Any] = {"message": message, "tokens": words, "glossary": glossary + guesses}
        if context:
            state["context"] = context

        # Candidates in code. Words with candidates get a Choice, others a Noul.
        cand_objs: dict[int, list[C.Candidate]] = {}
        questions: dict[str, dict] = {}
        for i in idxs:
            # Glossary terms need real similarity; guesses are the agent's own
            # hypotheses for this very message, so a loose match is enough.
            cands = C.generate(tokens, i, glossary)
            if guesses:
                have = {c.text for c in cands}
                cands += [c for c in C.generate(tokens, i, guesses, min_score=0.35) if c.text not in have]
            if cands:
                cand_objs[i] = cands
                options: dict[str, Any] = {}
                for c in cands:
                    desc: dict[str, Any] = {"_fake_score": c.score}
                    if c.span > 1:
                        desc["replaces"] = " ".join(words[c.start:c.start + c.span])
                    if c.text.lower() in speculative:
                        desc["note"] = "suggested by the assistant from the conversation context"
                    options[c.text] = desc
                options[KEEP] = f"`{words[i]}` is correct as written"
                questions[f"fix_{i}"] = choice(
                    {
                        "position": i,
                        "original": words[i],
                        "question": (
                            "The user typed `message` on a phone; speech-to-text, T9 and swipe "
                            "errors are possible. Which word did they actually mean at "
                            "`tokens[position]`, given `context` and `glossary`? The other options "
                            f"are candidate replacements; `{KEEP}` means the original word is right."
                        ),
                    },
                    options,
                )
            else:
                questions[f"sus_{i}"] = noul(
                    {
                        "position": i,
                        "word": words[i],
                        "question": (
                            "Is `word` at `tokens[position]` in `message` a misrecognition "
                            "(speech-to-text, T9 or swipe error) where the user meant a different word?"
                        ),
                    },
                    true="the word does not fit its neighbours and looks like a garbled version of another word",
                    false="the word is appropriate in this context as written",
                )
                questions[f"sus_{i}"]["_fake_hint"] = 0.0
        answers = self._ask(state, questions)

        unresolved = [
            Unresolved(i, words[i], answers[f"sus_{i}"]["noul"])
            for i in idxs if f"sus_{i}" in answers and answers[f"sus_{i}"]["noul"] >= self.corrupted_threshold
        ]

        # option = (text, start, span, prob); the "keep" option has text == original word
        flagged: list[Flagged] = []
        per_pos: list[list[tuple[str, int, int, float]]] = []
        for i, cands in cand_objs.items():
            probs = answers[f"fix_{i}"]["probabilities"]
            p_keep = probs.get(KEEP, 0.0)
            if 1.0 - p_keep < self.corrupted_threshold:
                continue
            where = {c.text: (c.start, c.span) for c in cands}
            flagged.append(Flagged(i, words[i], 1.0 - p_keep, [c.text for c in cands]))
            opts = [(words[i], i, 1, p_keep)]
            opts += [(t, *where[t], p) for t, p in probs.items() if t in where]
            opts.sort(key=lambda o: o[3], reverse=True)
            per_pos.append(opts[: self.max_variants + 1])

        if not flagged:
            note = "no corrupted words detected" if not unresolved else \
                "suspicious words found but the glossary has no replacement for them — see `unresolved`"
            return Interpretation(message, [Variant(message, 1.0)], [], unresolved, False, note)

        variants: list[Variant] = []
        for combo in itertools.product(*per_pos):
            prob = 1.0
            replacements: dict[int, tuple[str, int]] = {}
            changes: list[Change] = []
            covered: set[int] = set()
            for f, (text, start, span, p) in zip(flagged, combo):
                prob *= p
                if text == words[f.position]:
                    continue
                rng = set(range(start, start + span))
                if rng & covered:          # two fixes claim the same token — impossible reading
                    prob = 0.0
                    break
                covered |= rng
                replacements[start] = (text, span)
                changes.append(Change(start, " ".join(words[start:start + span]), text, p))
            if prob > 0:
                variants.append(Variant(_render(message, tokens, replacements), prob, changes))

        merged: dict[str, Variant] = {}
        for v in variants:
            if v.text in merged:
                merged[v.text].probability += v.probability
            else:
                merged[v.text] = v
        variants = sorted(merged.values(), key=lambda v: v.probability, reverse=True)[: self.max_variants]
        total = sum(v.probability for v in variants) or 1.0
        for v in variants:
            v.probability /= total

        needs_clarification = len(variants) > 1 and variants[0].probability < self.auto_apply_confidence
        note = "ambiguous — ask the user to choose" if needs_clarification else "top variant is confident enough to apply"
        if unresolved:
            note += "; some suspicious words had no glossary match — see `unresolved`"
        return Interpretation(message, variants, flagged, unresolved, needs_clarification, note)


def _render(message: str, tokens: list[C.Token], replacements: dict[int, tuple[str, int]]) -> str:
    """Rebuild the message applying `{token_index: (text, span)}` replacements."""
    out, cursor, i = [], 0, 0
    while i < len(tokens):
        t = tokens[i]
        out.append(message[cursor:t.start])
        if i in replacements:
            text, span = replacements[i]
            last = tokens[i + span - 1]
            out.append(_match_case(t.text, text))
            cursor = last.end
            i += span
        else:
            out.append(t.text)
            cursor = t.end
            i += 1
    out.append(message[cursor:])
    return "".join(out)


def _match_case(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement
