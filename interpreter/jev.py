"""Thin client for the TypeSafe Jev `POST /v1/systemone` endpoint, plus a fake
backend so the pipeline can be exercised without an API key.

Jev is a System One model: it does not generate text. Every call is
`state` + a map of typed questions (noul / choice / score) and returns one
structured answer per question. See https://docs.typesafe.ai/api
"""
from __future__ import annotations

import os
from typing import Any, Protocol

import httpx

API_URL = "https://api.typesafe.ai/v1/systemone"
DEFAULT_MODEL = "jev-latest"

Questions = dict[str, dict[str, Any]]
Answers = dict[str, dict[str, Any]]


class JevBackend(Protocol):
    def ask(self, state: Any, questions: Questions) -> Answers: ...


def noul(instructions: Any, true: Any = None, false: Any = None) -> dict[str, Any]:
    q: dict[str, Any] = {"type": "noul", "instructions": instructions}
    if true is not None or false is not None:
        q["criteria"] = {"true": true, "false": false}
    return q


def choice(instructions: Any, options: dict[str, Any]) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions, "criteria": options}


class HttpJev:
    """Real backend. Reads TYPESAFE_API_KEY from the environment by default."""

    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL, timeout: float = 30.0):
        self.api_key = api_key or os.environ.get("TYPESAFE_API_KEY")
        if not self.api_key:
            raise RuntimeError("TYPESAFE_API_KEY is not set")
        self.model = model
        self._client = httpx.Client(timeout=timeout)

    def ask(self, state: Any, questions: Questions) -> Answers:
        if not questions:
            return {}
        resp = self._client.post(
            API_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"state": state, "model": self.model, "questions": questions},
        )
        resp.raise_for_status()
        return resp.json()["answers"]


class FakeJev:
    """Deterministic stand-in used by tests and the offline demo.

    It understands the two question shapes the pipeline emits:
    * noul over a token: "suspicious" if the pipeline attached a
      `_fake_hint` (the best fuzzy score to any glossary term);
    * choice over candidates: probability proportional to the `_fake_score`
      attached to each option, `keep_original` gets a fixed floor.
    Hints are stripped before a real request, so they never reach Jev.
    """

    def __init__(self, suspicious_at: float = 0.6):
        self.suspicious_at = suspicious_at
        self.calls: list[tuple[Any, Questions]] = []

    def ask(self, state: Any, questions: Questions) -> Answers:
        self.calls.append((state, questions))
        answers: Answers = {}
        for qid, q in questions.items():
            if q["type"] == "noul":
                hint = float(q.get("_fake_hint", 0.0))
                answers[qid] = {"type": "noul", "noul": 0.9 if hint >= self.suspicious_at else 0.1}
            elif q["type"] == "choice":
                weights = {}
                for opt, desc in q["criteria"].items():
                    if isinstance(desc, dict) and "_fake_score" in desc:
                        weights[opt] = float(desc["_fake_score"])
                    elif opt == "keep_original":
                        weights[opt] = 0.3
                    else:
                        weights[opt] = 0.05
                total = sum(weights.values()) or 1.0
                probs = {k: v / total for k, v in weights.items()}
                best = max(probs, key=probs.get)
                answers[qid] = {
                    "type": "choice",
                    "choice": best,
                    "probabilities": probs,
                    "confidence": probs[best],
                }
            else:
                raise ValueError(f"unsupported question type {q['type']}")
        return answers


def strip_hints(questions: Questions) -> Questions:
    """Remove `_fake_*` keys so they are never sent to the real API."""
    out: Questions = {}
    for qid, q in questions.items():
        q = {k: v for k, v in q.items() if not k.startswith("_fake_")}
        crit = q.get("criteria")
        if isinstance(crit, dict):
            q["criteria"] = {
                k: ({kk: vv for kk, vv in v.items() if not kk.startswith("_fake_")} or None)
                if isinstance(v, dict) else v
                for k, v in crit.items()
            }
        out[qid] = q
    return out


def backend_from_env() -> JevBackend:
    if os.environ.get("TYPESAFE_API_KEY"):
        return HttpJev()
    return FakeJev()
