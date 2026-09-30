# drunken-master

Repository of the **Drunken Master** skill (see README.md): the agent recovers
the meaning of messages garbled by any input path (speech-to-text, autocorrect,
swipe, OCR, hurried typing) and shows its reading before acting. The Python
package `interpreter/` is a development helper MCP server (logging readings into
the eval set, engine comparison); it is not part of the plugin.

## Rules for the agent in this project

- Does the message look garbled (odd words, words that sound like terms,
  broken grammar)? Apply the skill first — `skills/drunken-master/SKILL.md`:
  recover the readings **yourself**, with no external calls, then act or ask.
  The `Read as:` line comes before any tool call.
- Record every reading with `record_interpretation` (when the helper server is
  loaded), and again with `chosen` after the user answers. That log is the
  eval set.
- `interpret_message` (Jev / Claude engines) is auxiliary: for eval comparison
  and as a cheap check of your own hypotheses via `guesses`.
- Project glossary, in case of doubt: `drunken-master`, `interpreter`,
  `pipeline`, `candidates`, `jev`, `server`, `Jev`, `Noul`, `Choice`, `MCP`,
  `eval`, `inbox`, `skill`, `plugin`, `marketplace`, `дебаг`, `скилы`,
  `лисенер`, `Ванневар`, `глоссарий`, `коммит`, `деплой`, `тесты`.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e .[dev]
.venv/bin/python -m pytest
.venv/bin/python -m interpreter "text" --glossary word1 word2
claude --mcp-config dev/mcp.json     # load the helper server in this repo
claude plugin validate .             # check the plugin before publishing
```

Helper-server calls are appended to `evals/inbox.jsonl` (`INTERPRETER_LOG` in
`dev/mcp.json`); labelled rows become eval cases.
