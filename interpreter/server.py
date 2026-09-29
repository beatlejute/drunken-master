"""MCP server exposing the interpreter to an agent.

Conversation scenario (the agent is the MCP client):

1. User sends a message from a phone; it may contain speech-to-text / T9 /
   swipe errors.
2. The agent builds a glossary from what it knows (project names, tools,
   skills, terms used earlier in the chat) and calls `interpret_message`.
3. If `needs_clarification` is false, the agent proceeds with
   `variants[0].text` (optionally telling the user what it corrected).
4. If true, the agent shows `variants` to the user as numbered options and
   asks which one was meant (plus "none of these").

Run: `python -m interpreter.server` (stdio). Set TYPESAFE_API_KEY to talk to
Jev; without it a deterministic fake backend is used so the flow can be
tested end-to-end offline.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from mcp.server.mcpserver import MCPServer

from .engines import Engine, make_engine

mcp = MCPServer(
    "interpreter",
    instructions=(
        "Use `interpret_message` on user messages that look like they came from a phone "
        "(speech-to-text, T9, swipe) before acting on them. Supply a glossary of domain "
        "terms you know: project names, tool/skill names, jargon used earlier in the "
        "conversation. If the result says needs_clarification, present the variants to "
        "the user as a numbered list and ask which one they meant."
    ),
)

_engines: dict[str, Engine] = {}


def get_engine(name: str | None = None) -> Engine:
    from .engines import default_engine_name
    name = name or default_engine_name()
    if name not in _engines:
        _engines[name] = make_engine(name)
    return _engines[name]


@mcp.tool()
def interpret_message(
    message: str,
    glossary: list[str],
    context: str | None = None,
    ignore: list[str] | None = None,
    guesses: list[str] | None = None,
    max_variants: int = 3,
    engine: str | None = None,
) -> dict[str, Any]:
    """Detect misrecognised words in `message` and reconstruct what the user meant.

    Args:
        message: the raw user message.
        glossary: domain terms the user is likely to have meant (project names,
            tools, skills, jargon). Jev can only pick from words you provide, so
            the quality of this list drives the quality of the result.
        context: short summary of the preceding conversation (keep it small;
            irrelevant text lowers Jev accuracy).
        ignore: words that are definitely correct and should not be checked.
        guesses: speculative replacements you are not sure about. They are
            offered to Jev marked as speculative, so a wrong guess is less
            likely to be applied than a glossary term.
        max_variants: how many alternative readings to return.
        engine: "claude" (generative, default when available) or "jev".

    Returns a dict with `variants` (each: text, probability, changes),
    `flagged` words, `unresolved` words (look garbled but nothing in the
    glossary matches — extend the glossary and call again) and
    `needs_clarification`.
    """
    eng = get_engine(engine)
    eng.max_variants = max(1, max_variants)
    result = eng.interpret(message, glossary, context, ignore, guesses).to_dict()
    result["engine"] = engine or type(eng).__name__
    _log_call({"message": message, "glossary": glossary, "guesses": guesses, "context": context, "ignore": ignore,
               "engine": result["engine"]}, result)
    return result


def _log_call(request: dict[str, Any], result: dict[str, Any]) -> None:
    """Append the call to INTERPRETER_LOG (JSONL) so real traffic can become eval cases."""
    path = os.environ.get("INTERPRETER_LOG")
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(
                {"ts": datetime.now(timezone.utc).isoformat(), "request": request, "result": result, "intended": None},
                ensure_ascii=False,
            ) + "\n")
    except OSError:
        pass  # logging must never break the tool


@mcp.tool()
def format_clarification(variants: list[str]) -> str:
    """Render variants as a numbered question to show the user.

    Purely a convenience so all agents phrase the clarification the same way.
    """
    lines = ["Похоже, в сообщении есть опечатки или ошибки распознавания. Вы имели в виду:"]
    for i, v in enumerate(variants, 1):
        lines.append(f"{i}. {v}")
    lines.append(f"{len(variants) + 1}. Ничего из этого — оставить как есть")
    return "\n".join(lines)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
