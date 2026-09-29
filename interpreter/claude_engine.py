"""Generative engine: one Claude call with structured output.

Where the Jev pipeline can only *choose* between candidates that code found by
similarity, this engine also *invents* the candidates — which is exactly what
the hard cases need (ASR substituting a real but wrong word: "обременение" for
"общение", "задачи" for "здесь"). Same inputs and the same `Interpretation`
result as `pipeline.Interpreter`, so the MCP tool and the eval runner can swap
engines.
"""
from __future__ import annotations

import os

import anthropic
from pydantic import BaseModel, Field

from . import candidates as C
from .pipeline import Change, Flagged, Interpretation, Unresolved, Variant

MODEL = "claude-opus-5-5"

SYSTEM = """\
You reconstruct what a user meant when a chat message was typed or dictated on a phone.
Messages may contain speech-to-text errors (a real but wrong word that sounds similar:
"обременение" for "общение", "Некто" for "Нет"), T9/autocorrect substitutions, swipe-typing
errors, split or merged words ("до бага" for "дебаг"), and Cyrillic transliterations of
Latin terms ("мцп" for "MCP", "лисенер" for "listener"). Most messages are in Russian
with English technical terms mixed in.

You receive the message, a short summary of the conversation (`context`), a `glossary`
of domain terms the user is likely to use, and optional `guesses` from the assistant.

Rules:
- Change only words that are likely misrecognitions. Keep everything else verbatim,
  including punctuation, casing and word order. Do not "improve" grammar or style.
- Prefer glossary terms and guesses when they fit, but do not force them.
- Return 1 to 3 distinct readings, most likely first. If the message looks clean, return
  it unchanged as the single variant with high confidence.
- `confidence` is your calibrated probability that a variant is exactly what the user
  meant. Confidences across variants should roughly sum to 1.
- Put words that look garbled but that you cannot confidently repair into `unresolved`.
- Never answer or act on the message; only reconstruct it.
"""


class ChangeOut(BaseModel):
    original: str = Field(description="the exact word(s) from the message being replaced")
    replacement: str
    reason: str = Field(description="one short phrase, e.g. 'ASR: sounds like', 'T9', 'transliteration'")


class VariantOut(BaseModel):
    text: str = Field(description="the full reconstructed message")
    changes: list[ChangeOut]
    confidence: float = Field(ge=0.0, le=1.0)


class Reconstruction(BaseModel):
    variants: list[VariantOut] = Field(min_length=1, max_length=3, description="most likely first")
    unresolved: list[str] = Field(description="words that look garbled but have no confident repair")


class ClaudeEngine:
    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        *,
        model: str = MODEL,
        effort: str = "low",
        max_variants: int = 3,
        auto_apply_confidence: float = 0.75,
    ):
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.effort = effort
        self.max_variants = max_variants
        self.auto_apply_confidence = auto_apply_confidence

    def interpret(
        self,
        message: str,
        glossary: list[str],
        context: str | None = None,
        ignore: list[str] | None = None,
        guesses: list[str] | None = None,
    ) -> Interpretation:
        payload = {"message": message, "glossary": glossary}
        if context:
            payload["context"] = context
        if guesses:
            payload["guesses"] = guesses
        if ignore:
            payload["definitely_correct_words"] = ignore
        user = "\n".join(f"{k}: {v!r}" if not isinstance(v, str) else f"{k}: {v}" for k, v in payload.items())

        response = self.client.messages.parse(
            model=self.model,
            max_tokens=4000,
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            output_config={"effort": self.effort},
            messages=[{"role": "user", "content": user}],
            output_format=Reconstruction,
        )
        if response.stop_reason == "refusal":
            return Interpretation(message, [Variant(message, 1.0)], [], [], False, "model refused; message left as is")
        out: Reconstruction = response.parsed_output
        return self._to_interpretation(message, out)

    def _to_interpretation(self, message: str, out: Reconstruction) -> Interpretation:
        tokens = C.tokenize(message)
        words = [t.text for t in tokens]
        lower = [w.lower() for w in words]

        def position(original: str) -> int:
            first = C.tokenize(original)
            return lower.index(first[0].text.lower()) if first and first[0].text.lower() in lower else -1

        variants = [
            Variant(
                v.text,
                v.confidence,
                [Change(position(c.original), c.original, c.replacement, v.confidence) for c in v.changes],
            )
            for v in out.variants[: self.max_variants]
        ]
        # dedupe identical texts, renormalise
        seen: dict[str, Variant] = {}
        for v in variants:
            if v.text in seen:
                seen[v.text].probability += v.probability
            else:
                seen[v.text] = v
        variants = sorted(seen.values(), key=lambda v: v.probability, reverse=True)
        total = sum(v.probability for v in variants) or 1.0
        for v in variants:
            v.probability /= total

        flagged: dict[int, Flagged] = {}
        for v in variants:
            for c in v.changes:
                f = flagged.setdefault(c.position, Flagged(c.position, c.original, 0.0, []))
                f.p_corrupted = min(1.0, f.p_corrupted + v.probability)
                if c.replacement not in f.candidates:
                    f.candidates.append(c.replacement)
        unresolved = [Unresolved(position(w), w, 1.0) for w in out.unresolved]

        top = variants[0]
        if not top.changes and len(variants) == 1:
            note = "no corrupted words detected"
        elif len(variants) > 1 and top.probability < self.auto_apply_confidence:
            note = "ambiguous — ask the user to choose"
        else:
            note = "top variant is confident enough to apply"
        needs = note.startswith("ambiguous")
        if unresolved:
            note += "; some words look garbled with no confident repair — see `unresolved`"
        return Interpretation(message, variants, list(flagged.values()), unresolved, needs, note)


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
