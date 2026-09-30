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
        "loging" could be feature/login (just merged) or feature/logging —
        which one should I delete?
        1. feature/login   2. feature/logging   3. Neither
```

## What it does

1. Finds words that do not fit their neighbours, sound like a term from
   context, are not words at all, or are real words from the wrong topic.
2. Runs them through the distortion classes: sound-alike substitution
   (sever ← server), phonetic distortion of a term (ingratiation ← integration),
   split/merge (de bug ← debug), wrong script («мцп» ← MCP), autocorrect/swipe junk.
3. Composes 1–3 complete readings with confidences, changing only what is
   garbled — no reordering, no "improving" — and checks them word by word
   against the original.
4. Shows the reading as the **first line of the turn, before any tool call**.
   Confidence ≥ 0.75: acts. Lower: lists the readings and waits. Irreversible
   actions (approve, deploy, delete, send) need ≥ 0.9.

Works in any language; the reading is shown in the user's language. Built and
tested on Russian and English. Evaluated on 12 cases (9 real garbled messages
from live sessions): Opus 100%, Sonnet 96%, Haiku 84% of assertions.

## What the plugin runs

Nothing. It is a single Markdown skill file. No network calls, no scripts, no
packages, no settings changes, no credentials.

## Install

```
/plugin marketplace add beatlejute/drunken-master
/plugin install drunken-master@drunken-master
```

Or copy `skills/drunken-master/` into `~/.claude/skills/`.

Source, evaluation cases and the development notes:
https://github.com/beatlejute/drunken-master

## License

MIT.
