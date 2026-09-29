"""Eval runner: compare engines on labelled cases.

    python -m interpreter.eval                      # all engines that can run
    python -m interpreter.eval --engines jev speller
    python -m interpreter.eval --cases evals/cases.jsonl evals/inbox.jsonl

Cases come from two places:
  * evals/cases.jsonl  — curated, committed: {"garbled", "intended", "glossary", "guesses"?, "context"?, "kind"?}
  * evals/inbox.jsonl  — the tool log; rows with `intended` set are used, latest row per message wins.
    Rows with engine "agent" also supply the agent's own recorded variants, which
    cannot be re-run and are scored as logged.

Metrics per engine (over the cases it produced an answer for):
  top1      — top variant equals `intended` after normalisation (case, punctuation, spaces)
  top3      — `intended` is among the returned variants
  wer       — mean word error rate of the top variant vs `intended` (lower is better)
  fixed     — share of garbled words the top variant repaired (recall of corrections)
  broke     — share of correct words the top variant damaged (false corrections)
  ask       — how often the engine would ask the user (needs_clarification)
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from . import candidates as C

DEFAULT_GLOSSARY = [
    "interpreter", "pipeline", "candidates", "jev", "server", "дебаг", "скилы", "лисенер",
    "Ванневар", "Jev", "Noul", "Choice", "MCP", "глоссарий", "коммит", "деплой", "тесты",
    "eval", "inbox", "сессия", "хук", "скилл", "движок",
]


@dataclass
class Case:
    garbled: str
    intended: str
    glossary: list[str] = field(default_factory=list)
    guesses: list[str] = field(default_factory=list)
    context: str | None = None
    kind: str = ""
    agent_variants: list[dict[str, Any]] | None = None  # from the log, if any


def norm(s: str) -> str:
    return " ".join(re.findall(r"\w+", s.lower()))


def words(s: str) -> list[str]:
    return norm(s).split()


def wer(hyp: str, ref: str) -> float:
    h, r = words(hyp), words(ref)
    if not r:
        return 0.0 if not h else 1.0
    d = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        d[i][0] = i
    for j in range(len(h) + 1):
        d[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (r[i - 1] != h[j - 1]))
    return d[len(r)][len(h)] / len(r)


def _diff_words(a: str, b: str) -> tuple[set[int], set[int]]:
    """Indices of words in `a` that differ from `b`, and in `b` that differ from `a`."""
    aw, bw = words(a), words(b)
    sm = difflib.SequenceMatcher(a=aw, b=bw, autojunk=False)
    da, db = set(), set()
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "equal":
            da.update(range(i1, i2))
            db.update(range(j1, j2))
    return da, db


def fixed_and_broke(garbled: str, top: str, intended: str) -> tuple[float | None, float | None]:
    """recall of repairs on garbled words; rate of damage on words that were fine."""
    bad, _ = _diff_words(garbled, intended)          # garbled word positions that needed a fix
    changed, _ = _diff_words(garbled, top)            # garbled word positions the engine touched
    gw = words(garbled)
    good = set(range(len(gw))) - bad
    # a garbled word counts as fixed if the top text agrees with intended around it;
    # simplest robust proxy: word-level errors remaining vs originally present
    err_before = len(bad)
    err_after = len(_diff_words(top, intended)[0])
    fixed = None if err_before == 0 else max(0.0, (err_before - err_after) / err_before)
    broke = None if not good else len(changed & good) / len(good)
    return fixed, broke


# ---------------------------------------------------------------- engines

class SpellerEngine:
    """Yandex Speller as a baseline: one correction per word, first suggestion."""
    URL = "https://speller.yandex.net/services/spellservice.json/checkText"
    max_variants = 3

    def interpret(self, message, glossary, context=None, ignore=None, guesses=None):
        from .pipeline import Interpretation, Variant, Change
        r = httpx.get(self.URL, params={"lang": "ru,en", "text": message, "options": 0}, timeout=15)
        r.raise_for_status()
        text, changes, shift = message, [], 0
        for e in r.json():
            if not e.get("s"):
                continue
            pos, ln, rep = e["pos"] + shift, e["len"], e["s"][0]
            text = text[:pos] + rep + text[pos + ln:]
            shift += len(rep) - ln
            changes.append(Change(-1, e["word"], rep, 1.0))
        note = "speller: " + (f"{len(changes)} corrections" if changes else "no corrections")
        return Interpretation(message, [Variant(text, 1.0, changes)], [], [], False, note)


def make_engines(names: list[str]) -> dict[str, Any]:
    from .engines import make_engine
    out: dict[str, Any] = {}
    for n in names:
        if n == "agent":
            out[n] = None  # scored from the log
        elif n == "speller":
            out[n] = SpellerEngine()
        elif n == "sage":
            out[n] = _sage()
        else:
            out[n] = make_engine(n)
    return out


def _sage():
    try:
        from .sage_engine import SageEngine  # optional, heavy (torch + model download)
        return SageEngine()
    except Exception as e:  # noqa: BLE001
        print(f"[sage unavailable: {e}]", file=sys.stderr)
        return None


# ---------------------------------------------------------------- cases

def load_cases(paths: list[str]) -> list[Case]:
    by_msg: dict[str, Case] = {}
    for p in paths:
        path = Path(p)
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if "garbled" in row:                     # curated case
                c = Case(row["garbled"], row["intended"], row.get("glossary", []), row.get("guesses", []),
                         row.get("context"), row.get("kind", ""))
            else:                                    # inbox row
                req, res = row["request"], row.get("result", {})
                msg = req["message"]
                prev = by_msg.get(msg)
                c = Case(msg, row.get("intended") or (prev.intended if prev else ""),
                         req.get("glossary") or (prev.glossary if prev else []),
                         req.get("guesses") or (prev.guesses if prev else []),
                         req.get("context") or (prev.context if prev else None),
                         row.get("kind", prev.kind if prev else ""),
                         prev.agent_variants if prev else None)
                if req.get("engine") == "agent" and res.get("variants"):
                    c.agent_variants = res["variants"]
            if not c.intended:
                by_msg.setdefault(c.garbled, c)
                continue
            by_msg[c.garbled] = c
    return [c for c in by_msg.values() if c.intended]


# ---------------------------------------------------------------- run

def run(cases: list[Case], engines: dict[str, Any], verbose: bool, use_guesses: bool = True) -> dict[str, dict[str, float]]:
    summary: dict[str, dict[str, float]] = {}
    for name, eng in engines.items():
        if name != "agent" and eng is None:
            continue
        rows = []
        for c in cases:
            if name == "agent":
                if not c.agent_variants:
                    continue
                variants = [v["text"] for v in c.agent_variants]
                p_top = c.agent_variants[0].get("probability") or 0.0
                ask = len(variants) > 1 and p_top < 0.75
            else:
                glossary = c.glossary or DEFAULT_GLOSSARY
                try:
                    res = eng.interpret(c.garbled, glossary, c.context, None, (c.guesses or None) if use_guesses else None)
                except Exception as e:  # noqa: BLE001
                    print(f"[{name}] error on {c.garbled[:40]!r}: {e}", file=sys.stderr)
                    continue
                variants = [v.text for v in res.variants]
                ask = res.needs_clarification
            top = variants[0]
            f, b = fixed_and_broke(c.garbled, top, c.intended)
            rows.append({
                "top1": norm(top) == norm(c.intended),
                "top3": any(norm(v) == norm(c.intended) for v in variants),
                "wer": wer(top, c.intended),
                "fixed": f, "broke": b, "ask": ask,
            })
            if verbose:
                mark = "✓" if rows[-1]["top1"] else ("~" if rows[-1]["top3"] else "✗")
                print(f"  {mark} [{name}] {c.garbled}\n      → {top}" + ("" if rows[-1]["top1"] else f"\n      ≠ {c.intended}"))
        if not rows:
            continue
        def mean(k):
            vals = [r[k] for r in rows if r[k] is not None]
            return sum(vals) / len(vals) if vals else float("nan")
        summary[name] = {"n": len(rows), "top1": mean("top1"), "top3": mean("top3"), "wer": mean("wer"),
                         "fixed": mean("fixed"), "broke": mean("broke"), "ask": mean("ask")}
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", nargs="*", default=["evals/cases.jsonl", "evals/inbox.jsonl"])
    ap.add_argument("--engines", nargs="*", default=["agent", "jev", "speller"])
    ap.add_argument("--no-guesses", action="store_true",
                    help="run engines without the agent's logged guesses: what they do on their own")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    os.environ.pop("INTERPRETER_LOG", None)  # never log eval runs into the inbox
    cases = load_cases(args.cases)
    if not cases:
        sys.exit("no labelled cases found")
    print(f"{len(cases)} labelled cases\n")
    summary = run(cases, make_engines(args.engines), args.verbose, use_guesses=not args.no_guesses)
    print(f"\n{'engine':<9}{'n':>4}{'top1':>7}{'top3':>7}{'wer':>7}{'fixed':>7}{'broke':>7}{'ask':>6}")
    for name, s in summary.items():
        print(f"{name:<9}{s['n']:>4}{s['top1']:>7.2f}{s['top3']:>7.2f}{s['wer']:>7.2f}{s['fixed']:>7.2f}{s['broke']:>7.2f}{s['ask']:>6.2f}")


if __name__ == "__main__":
    main()
