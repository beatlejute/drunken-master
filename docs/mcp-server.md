# Helper MCP server `interpreter` (development tool)

> The product of this repository is the [Drunken Master skill](../skills/drunken-master/SKILL.md);
> see the [README](../README.md). The server and engines below are for logging
> eval data, comparing engines, and as a deterministic path for weaker models.
> They are **not** part of the plugin and are not installed with it.

## Tools

| Tool | Purpose |
| - | - |
| `record_interpretation(message, variants, chosen?, engine="agent")` | Record a reading the agent made itself; `chosen` after the user confirms. Appends to `INTERPRETER_LOG`. |
| `interpret_message(message, glossary, context?, ignore?, guesses?, max_variants=3, engine?)` | Run an engine: `jev` (TypeSafe Jev choosing among similarity-based candidates) or `claude` (one structured-output call). Returns `variants`, `flagged`, `unresolved`, `needs_clarification`. |
| `format_clarification(variants)` | Render a numbered "did you mean" question. |

## Jev engine

1. Code: candidates per word from the glossary (orthographic + phonetic
   similarity, Latin→Cyrillic transliteration, adjacent-token merge
   «до бага → дебаг»). Agent `guesses` are matched more loosely and marked.
2. Jev, **one request**: `Choice {candidates…, keep_original}` per word with
   candidates; `Noul` "does this look misrecognised?" per word without →
   `unresolved`.
3. Code: beam over per-word distributions → top-N sentence variants;
   `needs_clarification` from the top variant's probability.

Engine selection: `INTERPRETER_ENGINE`, or the `engine` argument; default is
`claude` when an Anthropic credential is present, else `jev`. Without
`TYPESAFE_API_KEY` a deterministic `FakeJev` serves tests and the offline CLI.

## Running

```bash
python -m venv .venv && .venv/bin/pip install -e .[dev]
export TYPESAFE_API_KEY=...          # optional; FakeJev otherwise
.venv/bin/python -m interpreter "text" --glossary term1 term2 --guesses g1 --context "…"
.venv/bin/python -m interpreter.server            # stdio MCP
claude --mcp-config dev/mcp.json                  # load it in this repo
.venv/bin/python -m interpreter.eval -v --engines agent jev speller
```

`dev/mcp.json` sets `INTERPRETER_LOG=evals/inbox.jsonl`; every tool call is
appended there with an empty `intended` to fill by hand.

## Measured (10 labelled cases, 2026-09-29)

| engine | top1 | WER | repaired | asked |
| - | - | - | - | - |
| jev + agent guesses | 0.60 | 0.09 | 0.59 | 0.40 |
| jev alone | 0.50 | 0.14 | 0.38 | 0.10 |
| Yandex Speller | 0.20 | 0.21 | 0.06 | 0 — and it damages jargon («лиционер → милиционер») |
