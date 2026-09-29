"""Pick an interpretation engine by name.

    claude — one generative call with structured output (default when an
             Anthropic credential is present); best at inventing repairs.
    jev    — TypeSafe Jev choosing among similarity-based candidates; cheap
             and fast, kept for comparison on the eval set.
"""
from __future__ import annotations

import os
from typing import Protocol

from .pipeline import Interpretation


class Engine(Protocol):
    max_variants: int

    def interpret(
        self,
        message: str,
        glossary: list[str],
        context: str | None = None,
        ignore: list[str] | None = None,
        guesses: list[str] | None = None,
    ) -> Interpretation: ...


def default_engine_name() -> str:
    explicit = os.environ.get("INTERPRETER_ENGINE")
    if explicit:
        return explicit
    from .claude_engine import available
    return "claude" if available() else "jev"


def make_engine(name: str | None = None, **kwargs) -> Engine:
    name = name or default_engine_name()
    if name == "claude":
        from .claude_engine import ClaudeEngine
        return ClaudeEngine(**kwargs)
    if name == "jev":
        from .jev import backend_from_env
        from .pipeline import Interpreter
        return Interpreter(backend_from_env(), **kwargs)
    raise ValueError(f"unknown engine {name!r}; use 'claude' or 'jev'")
