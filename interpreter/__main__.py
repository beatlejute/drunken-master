"""CLI for quick manual testing:

    python -m interpreter "нужно провести до бага" --glossary дебаг скилы лисенер
"""
from __future__ import annotations

import argparse
import json
import logging
import os

from .engines import make_engine
from .jev import FakeJev
from .server import _log_call


def main() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser(description="Interpret a possibly-garbled message.")
    ap.add_argument("message")
    ap.add_argument("--glossary", nargs="*", default=[], help="domain terms")
    ap.add_argument("--guesses", nargs="*", default=[], help="speculative replacements (marked as such for Jev)")
    ap.add_argument("--context", default=None)
    ap.add_argument("--variants", type=int, default=3)
    ap.add_argument("--engine", choices=["claude", "jev"], default=None, help="default: claude if ANTHROPIC_API_KEY is set, else jev")
    ap.add_argument("--json", action="store_true", help="dump full result as JSON")
    args = ap.parse_args()

    engine = make_engine(args.engine, max_variants=args.variants)
    if isinstance(getattr(engine, "backend", None), FakeJev):
        print("[offline: TYPESAFE_API_KEY not set, using FakeJev]\n")

    result = engine.interpret(args.message, args.glossary, args.context, guesses=args.guesses)
    if os.environ.get("INTERPRETER_LOG"):
        _log_call(
            {"message": args.message, "glossary": args.glossary, "guesses": args.guesses, "context": args.context, "ignore": None,
             "engine": type(engine).__name__},
            result.to_dict(),
        )
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    print(f"engine:   {type(engine).__name__}")
    print(f"original: {result.original}")
    if result.flagged:
        print("flagged:    " + ", ".join(f"{f.word}(p={f.p_corrupted:.2f})" for f in result.flagged))
    if result.unresolved:
        print("unresolved: " + ", ".join(f"{u.word}(p={u.p_corrupted:.2f})" for u in result.unresolved))
    print(f"\n{result.note}\n")
    for i, v in enumerate(result.variants, 1):
        print(f"{i}. [{v.probability:.2f}] {v.text}")
        for c in v.changes:
            print(f"     {c.original} -> {c.replacement} ({c.probability:.2f})")


if __name__ == "__main__":
    main()
