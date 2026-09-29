"""Interpretation pipeline.

    message ──► tokenize ──► Jev: noul per word ("is this misrecognized?")
            ──► code: candidates from glossary ──► Jev: choice per flagged word
            ──► code: beam over per-word distributions ──► top-k variants
            ──► (k>1) Jev: choice over variants + noul "coherent?" per variant

Jev never generates text; all wording comes from the glossary the caller
(the agent) supplies. Arithmetic stays in code, per the Jev guidance.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field, asdict
from typing import Any

from . import candidates as C
from .jev import JevBackend, choice, noul, strip_hints, FakeJev

KEEP = "keep_original"
NONE = "none_of_these"


@dataclass
class Change:
    position: int          # token index
    original: str
    replacement: str
    probability: float


@dataclass
class Variant:
    text: str
    probability: float               # product of per-word probabilities, renormalised
    changes: list[Change] = field(default_factory=list)
    jev_preference: float | None = None   # from the final Choice over variants
    coherence: float | None = None        # from the final Noul per variant


@dataclass
class Flagged:
    position: int
    word: str
    p_corrupted: float
    candidates: list[str]


@dataclass
class Interpretation:
    original: str
    variants: list[Variant]
    flagged: list[Flagged]
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
        auto_apply_confidence: float = 0.8,
    ):
        self.backend = backend
        self.corrupted_threshold = corrupted_threshold
        self.max_variants = max_variants
        self.auto_apply_confidence = auto_apply_confidence

    # -- Jev call wrapper -------------------------------------------------
    def _ask(self, state: Any, questions: dict[str, dict]) -> dict[str, dict]:
        if not questions:
            return {}
        if isinstance(self.backend, FakeJev):
            return self.backend.ask(state, questions)
        return self.backend.ask(state, strip_hints(questions))

    # -- main entry ----------------------------------------------------------
    def interpret(
        self,
        message: str,
        glossary: list[str],
        context: str | None = None,
        ignore: list[str] | None = None,
    ) -> Interpretation:
        tokens = C.tokenize(message)
        words = [t.text for t in tokens]
        idxs = C.checkable_indices(tokens, set(ignore or []))
        state: dict[str, Any] = {"message": message, "tokens": words, "glossary": glossary}
        if context:
            state["context"] = context

        # Step 1: which words look misrecognised?
        q1 = {}
        for i in idxs:
            q1[f"tok_{i}"] = noul(
                {
                    "position": i,
                    "word": words[i],
                    "question": (
                        "Is `word` at `tokens[position]` in `message` a misrecognition "
                        "(speech-to-text, T9 autocorrect or swipe typing error) where the user "
                        "meant a different word — in particular one of the terms in `glossary`?"
                    ),
                },
                true="the word does not fit its neighbours and resembles another word in sound or spelling",
                false="the word is appropriate in this context as written",
            )
            q1[f"tok_{i}"]["_fake_hint"] = C.best_glossary_score(tokens, i, glossary)
        a1 = self._ask(state, q1)

        flagged: list[Flagged] = []
        for i in idxs:
            p = a1[f"tok_{i}"]["noul"]
            if p >= self.corrupted_threshold:
                cands = C.generate(tokens, i, glossary)
                flagged.append(Flagged(i, words[i], p, [c.text for c in cands]))

        if not flagged:
            return Interpretation(message, [Variant(message, 1.0)], [], False, "no corrupted words detected")

        # Step 2: pick the intended word for each flagged position.
        cand_objs: dict[int, list[C.Candidate]] = {f.position: C.generate(tokens, f.position, glossary) for f in flagged}
        q2 = {}
        for f in flagged:
            options: dict[str, Any] = {}
            for c in cand_objs[f.position]:
                desc: dict[str, Any] = {"_fake_score": c.score}
                if c.span > 1:
                    desc["replaces"] = " ".join(words[c.start:c.start + c.span])
                options[c.text] = desc
            options[KEEP] = "the word is correct as written"
            options[NONE] = "the user meant a word not listed here"
            q2[f"fix_{f.position}"] = choice(
                {
                    "position": f.position,
                    "original": f.word,
                    "question": (
                        "Which word did the user actually mean at `tokens[position]` in `message`, "
                        "given `context` and `glossary`? Options are candidate replacements; "
                        f"`{KEEP}` means the original word is right."
                    ),
                },
                options,
            )
        a2 = self._ask(state, q2)

        # Step 3: combine in code — beam over independent per-word distributions.
        # option = (text, start, span, prob); the "keep" option has text == original word
        per_pos: list[tuple[int, list[tuple[str, int, int, float]]]] = []
        for f in flagged:
            probs = a2[f"fix_{f.position}"]["probabilities"]
            where = {c.text: (c.start, c.span) for c in cand_objs[f.position]}
            opts = [(words[f.position], f.position, 1, probs.get(KEEP, 0.0) + probs.get(NONE, 0.0))]
            opts += [(t, *where[t], p) for t, p in probs.items() if t in where]
            opts.sort(key=lambda o: o[3], reverse=True)
            per_pos.append((f.position, opts[: self.max_variants + 1]))

        variants: list[Variant] = []
        for combo in itertools.product(*[o for _, o in per_pos]):
            prob = 1.0
            replacements: dict[int, tuple[str, int]] = {}
            changes: list[Change] = []
            covered: set[int] = set()
            for (pos, _), (text, start, span, p) in zip(per_pos, combo):
                prob *= p
                if text == words[pos]:
                    continue
                rng = set(range(start, start + span))
                if rng & covered:          # two fixes claim the same token — impossible reading
                    prob = 0.0
                    break
                covered |= rng
                replacements[start] = (text, span)
                changes.append(Change(pos, " ".join(words[start:start + span]), text, p))
            if prob > 0:
                variants.append(Variant(_render(message, tokens, replacements), prob, changes))

        # merge identical renderings, normalise, cut
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

        # Step 4: let Jev compare whole sentences when there is a real choice.
        if len(variants) > 1:
            vstate = {"original": message, "variants": [v.text for v in variants]}
            if context:
                vstate["context"] = context
            q3: dict[str, dict] = {
                "best": choice(
                    "Which of `variants` is the sentence the user most likely intended when they "
                    "produced `original` (a message with possible speech-to-text / autocorrect errors)?",
                    {str(i): {"_fake_score": v.probability} for i, v in enumerate(variants)},
                )
            }
            for i in range(len(variants)):
                q3[f"coherent_{i}"] = noul(
                    {"index": i, "question": "Is `variants[index]` a coherent, meaningful sentence given `context`?"}
                )
                q3[f"coherent_{i}"]["_fake_hint"] = 1.0
            a3 = self._ask(vstate, q3)
            for i, v in enumerate(variants):
                v.jev_preference = a3["best"]["probabilities"][str(i)]
                v.coherence = a3[f"coherent_{i}"]["noul"]
            variants.sort(key=lambda v: (v.jev_preference or 0) * v.probability, reverse=True)
            top_conf = a3["best"]["confidence"]
        else:
            top_conf = 1.0

        needs_clarification = len(variants) > 1 and top_conf < self.auto_apply_confidence
        note = (
            "ambiguous — ask the user to choose" if needs_clarification
            else "top variant is confident enough to apply"
        )
        return Interpretation(message, variants, flagged, needs_clarification, note)


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
