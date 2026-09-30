# Working notes

Decisions, observed error classes and open problems. Read with `CLAUDE.md` and
`README.md`.

## What this is

Users write to agents from phones and by voice; ASR, autocorrect and swipe
distort words, terms especially («лиционер» ← «лисенер», «до бага» ← «дебаг»,
"sea eye" ← CI). The project recovers what was meant. It began as an MCP server
on [TypeSafe Jev](https://docs.typesafe.ai/) — a System One model that only
chooses among given options and returns probabilities — and ended as a skill
the agent runs itself.

## Decisions and why

- **Agent as the primary interpreter.** The agent is the strongest model
  available, holds the conversation context and needs no key. Live tests showed
  the bottleneck was hypothesis generation, not choice: "encumbrance" →
  "communication" needs meaning, not a dictionary. The skill lives in
  `skills/drunken-master/`; the MCP server (`interpreter/`) stays as a dev tool.
- **Jev pipeline: one request.** Earlier there were three (per-word Noul "is it
  garbled?" → Choice → Choice between whole sentences). The Noul sat near 0.5 and
  flipped between runs; the sentence-level Choice contradicted the per-word
  answers. Kept: `Choice {candidates…, keep_original}` per word with candidates,
  `Noul` per word without (→ `unresolved`).
- **`glossary` vs `guesses`.** Glossary = confident terms (similarity ≥ 0.6).
  Guesses = the agent's hypotheses for *this* message (≥ 0.35, marked as
  suggested). A guess put into the glossary once produced a false "ответные →
  отвлечённые".
- **Transliteration** in `candidates.similarity`; without it «мцп»/«MCP» = 0.0.
- **`needs_clarification`** = top-reading probability < 0.75 (computed in code).
- **Logging** of every call to `evals/inbox.jsonl`; `intended` filled by hand.

## Error classes seen

| Class | Example | Caught? |
| - | - | - |
| Phonetic distortion of a term | лиционер → лисенер, силы → скилы | yes, confidently |
| Word split | до бага → дебаг | yes (adjacent-token merge) |
| Cyrillic ↔ Latin | мцп → MCP, дебак → debug | yes, after transliteration |
| ASR substituted a **real, wrong word** | Некто ← Нет, обременение ← общение, задачи ← здесь, Сарат ← старт | only the agent; similarity search cannot reach it |
| Term not in glossary | нас → npm, гриха → github | no; reported as `unresolved` |

## Skill iterations (skill-creator)

Cases: `skills/drunken-master/evals/evals.json` (12: 9 real messages from live
sessions, 3 English, clean controls). Runs are independent subagents that see
only `SKILL.md`.

| Iteration | Compared | Result |
| - | - | - |
| 1 | skill vs no skill, 4 cases, Opus | 100% vs 81%; without the skill the hard case («Некто обременение… задачи») was read literally with no alternatives |
| 2 | "show the reading on any correction" vs previous version, 8 cases | 100% vs 92%; old version misread «фвлм … описание». On «подключилась» **both** versions showed the reading in a subagent — the silent fix happened in the live session, not in the skill |
| 3 | same skill on **Haiku 4.5** | 80%: detection and "Read as" everywhere; overconfident (0.80 on a 3-word ambiguity), drops/reorders words, stops after the first fix |
| 4 | Haiku, plus word-by-word check and confidence rule of thumb | 84%: calibration fixed (0.55 → asked); drift not fixed by text («ты он» → «Ты о чём», reorders) |
| 5 | same skill on **Sonnet 5.5** | 96%: all readings correct, no drift, 12–25 s per reply; one miss in the substantive answer |

Models: Opus 100% · Sonnet 96% · Haiku 84%. Self-sufficiency threshold: Sonnet
class. For Haiku the deterministic path (candidates in code, model only
chooses) remains justified.

Live finding after packaging: an agent read «Сарат райплайна» → «старт
пайплайна» correctly but **started the pipeline before writing "Read as"** — it
treated tool calls as preparation, not as the answer. The rule now says
"before any tool call", with a higher bar for irreversible actions.

## Open problems

1. **Trigger reliability in live sessions** is the main risk: subagents follow
   the skill; a busy agent mid-conversation may skip it. The only hard
   mechanism in Claude Code is a `UserPromptSubmit` hook that adds context (it
   cannot rewrite the prompt).
2. Jev jitter ≈ ±0.1 between identical requests; near-threshold cases flip.
   State quality (context, glossary) matters more than thresholds.
3. The 0.75 / 0.9 thresholds are not calibrated on enough data.
4. `unresolved` is noisy («подсмотреть» 0.70 false positive).

## How to test

- `pytest` — helper-server mechanics on FakeJev, no key.
- `python -m interpreter "text" --glossary … --guesses …` — real Jev.
- `python -m interpreter.eval -v` — engines vs labelled cases.
- Live: install the plugin in a fresh session, write garbled messages, watch
  whether the trigger fires and whether the reading precedes any action.
