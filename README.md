# Drunken Master

A Claude Code skill that reads garbled messages the way they were meant — and
shows you its reading **before** it acts.

Messages reach an agent mangled all the time: speech-to-text, autocorrect,
swipe typing, hurried thumbs, OCR, copy-paste. The nasty part is that words
often turn into *other real words*: "sever" for server, "stagging" for staging,
"sea eye" for CI, «обременение» for «общение». Spellcheckers do not catch
those, and an agent acting on the literal text does the wrong thing.

```
User:   Can you run the ingratiation tests and push to stagging when the sea eye is green

Agent:  Read as: "run the **integration** tests and push to **staging** when the **CI** is green"
        Running the integration suite now; will push to staging once CI passes…
```

```
User:   merge the login one and delete the loging branch

Agent:  Read as: "merge feature/login and delete the **loging** branch"
        Merged feature/login. "loging" could be feature/login (just merged) or
        feature/logging — which one should I delete?
        1. feature/login
        2. feature/logging
        3. Neither
```

No services, no API keys, no dictionaries: the agent's own model does the
reading, using the conversation context. The skill works in any language; it
was built and tested on Russian and English.

## Install

**From the repository, as a plugin** (recommended — updates with the repo):

```
/plugin marketplace add beatlejute/drunken-master
/plugin install drunken-master@drunken-master
```

From a terminal: `claude plugin marketplace add beatlejute/drunken-master && claude plugin install drunken-master@drunken-master`.

**Manually**: the skill is a single folder, [`plugin/skills/drunken-master/`](plugin/skills/drunken-master/).
Copy it to `~/.claude/skills/drunken-master` (all projects) or to
`<project>/.claude/skills/drunken-master` (one project).

Check: in a new session, type something deliberately garbled — the first line
of the reply should be `Read as: …`.

## How it works

The skill is a five-step procedure in [`SKILL.md`](plugin/skills/drunken-master/SKILL.md):

1. **Find suspicious words** — ones that disagree with their neighbours, sound
   like a term from context, are not words at all, or are real words that do
   not belong to the topic.
2. **Run through the distortion classes**, most frequent first:

   | Class | Examples |
   | - | - |
   | ASR substituted a real but wrong word | sever ← server; sea eye ← CI; «Некто» ← Нет; «соврать» ← словарь |
   | Phonetic distortion of a term | ingratiation ← integration; «лиционер» ← лисенер |
   | Split / merge | de bug ← debug; «иеть» ← и есть |
   | Wrong script / transliteration | Jane ← Jev; «мцп» ← MCP |
   | Autocorrect / swipe | «фвлм» ← вообще; asdgh ← junk |

3. **Compose 1–3 complete readings** with confidences; change only what is
   garbled, never reorder or "improve"; check word by word against the
   original before showing.
4. **Act or ask**: top confidence ≥ 0.75 → one `Read as:` line, then act;
   lower → a numbered list of readings and wait. The reading is shown
   **whenever any word was replaced**, even a trivial one, and **before any
   tool call**. Irreversible actions (approve, deploy, delete, send) need ≥ 0.9.
5. Record the reading if the session has a `record_interpretation` tool
   (optional; the skill works without it).

## Evaluation

12 cases — 9 real garbled messages from live sessions (Russian: voice input,
swipe, autocorrect) and 3 English cases, plus clean-message controls — and
~40 assertions ("reading shown before the answer", "substitutions correct",
"asked when ambiguous", "clean message untouched", "reading before tool calls").
Runs were independent agents that saw only `SKILL.md`.

| Model | Passed | Notes |
| - | - | - |
| Opus 5.5 | 100% | without the skill — 81%: on the hard case it read «задачи» literally and offered no alternatives |
| Sonnet 5.5 | 96% | every reading correct, ~2× faster than Opus; one miss in the substantive answer |
| Haiku 4.5 | 84% | detects and shows the reading everywhere, but drops/reorders words; instructions do not fix that |

The skill is self-sufficient from Sonnet class up. Iteration history:
[`docs/NOTES.md`](docs/NOTES.md); cases and assertions:
[`plugin/skills/drunken-master/evals/evals.json`](plugin/skills/drunken-master/evals/evals.json).

## Why a skill and not a service

This started as an MCP server on top of [TypeSafe Jev](https://docs.typesafe.ai/),
a model that picks among given options with calibrated probabilities. Live
testing showed the bottleneck is not choosing but **generating hypotheses**:
only a model with the conversation context can tell that "encumbrance" is
"communication". The agent already has that context, for free, without keys. A
survey of existing tools ([`docs/research-alternatives.md`](docs/research-alternatives.md))
confirmed nothing off the shelf does contextual real-word correction with
alternatives to choose from, and spellcheckers break jargon.

The helper server survives as a development tool — [`docs/mcp-server.md`](docs/mcp-server.md):
it logs readings into the eval set, compares engines, and offers a
deterministic path for weaker models. Nothing in the plugin depends on it.

## Repository layout

- [`plugin/`](plugin/) — **the published plugin**: the skill, its README, license and
  icon. Nothing else ships. It makes no network calls, runs no scripts,
  installs no packages and touches no settings.
- `interpreter/`, `dev/`, `tests/`, `evals/` — development helper: an MCP server
  that logs readings into the eval set and compares engines. Not part of the plugin.
- `docs/` — notes, engine docs, survey of alternatives.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e .[dev]
.venv/bin/python -m pytest                      # helper server mechanics
.venv/bin/python -m interpreter.eval -v         # compare engines on labelled cases
claude plugin validate plugin                      # plugin manifest / skill checks
```

To use the helper MCP server in this repo: `claude --mcp-config dev/mcp.json`.
Skill iterations are run with `skill-creator`; results live in
`.claude/skills/*-workspace/` (not in git).

## License

MIT.
