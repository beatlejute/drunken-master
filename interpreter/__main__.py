"""CLI for quick manual testing:

    python -m interpreter "нужно провести до бага" --glossary дебаг скилы лисенер
"""
from __future__ import annotations

import argparse
import json

from .jev import backend_from_env, FakeJev
from .pipeline import Interpreter


def main() -> None:
    ap = argparse.ArgumentParser(description="Interpret a possibly-garbled message.")
    ap.add_argument("message")
    ap.add_argument("--glossary", nargs="*", default=[], help="domain terms")
    ap.add_argument("--context", default=None)
    ap.add_argument("--variants", type=int, default=3)
    ap.add_argument("--json", action="store_true", help="dump full result as JSON")
    args = ap.parse_args()

    backend = backend_from_env()
    if isinstance(backend, FakeJev):
        print("[offline: TYPESAFE_API_KEY not set, using FakeJev]\n")

    result = Interpreter(backend, max_variants=args.variants).interpret(args.message, args.glossary, args.context)
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    print(f"original: {result.original}")
    if result.flagged:
        print("flagged:  " + ", ".join(f"{f.word}(p={f.p_corrupted:.2f})" for f in result.flagged))
    print(f"\n{result.note}\n")
    for i, v in enumerate(result.variants, 1):
        extra = f" jev={v.jev_preference:.2f} coh={v.coherence:.2f}" if v.jev_preference is not None else ""
        print(f"{i}. [{v.probability:.2f}{extra}] {v.text}")
        for c in v.changes:
            print(f"     {c.original} -> {c.replacement} ({c.probability:.2f})")


if __name__ == "__main__":
    main()
