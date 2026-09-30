---
name: drunken-master
description: Recover what the user actually meant when their message arrived garbled from any input path — speech-to-text, T9/autocorrect, swipe typing, hurried typing, OCR, copy-paste. Always apply this skill when a word does not fit its neighbours ("Some encumbrance and tests" / «Некто обременение и тесты»), a word sounds like a project term or name ("Jane" for Jev, "мцп" for MCP, "sever" for server), there is a nonsense letter cluster ("фвлм", "asdgh"), or the sentence becomes meaningful after swapping 1–3 words — even when the user says nothing about typos, and even when you "roughly got it". Do not apply to clean messages or to deliberate slang and coinages.
---

# Drunken Master — reading garbled messages

A message can arrive garbled from anywhere: speech-to-text swaps words for
sound-alikes, autocorrect swaps them for frequent ones, swipe and hurried typing
produce junk and merged words, OCR and copy-paste mangle letters. The result:
"Sezonal possibility that we'll have to mow a very big lie" for "Is there a
chance we'll have to build a very big dictionary". Act on the literal text and
you do the wrong thing; silently "get the gist" and you sometimes guess wrong
where the user never sees it. This skill makes the recovery explicit,
checkable and — where it matters — agreed with the user before anything happens.

You are the best tool for this: you hold the conversation context, the project
files and the language. External spellcheckers cannot catch real-but-wrong
words and they break jargon (Yandex Speller: «лиционер → милиционер»). No
external calls are needed. The skill is language-agnostic; the examples are
in English and Russian because that is where it was built and tested.

## Step 1. Find suspicious words

Walk through the message and mark words that:
- do not agree grammatically or semantically with their neighbours;
- sound like a term, a name, or a word from the conversation context;
- are not words at all (swipe junk);
- are oddly placed — a real word, but not from this topic ("encumbrance" in a
  chat about tests; «обременение» in a chat about тесты).

Marked nothing? The message is clean: the skill is done, say nothing about it.

## Step 2. Run through the distortion classes

For every marked word, check the classes in descending order of frequency:

| Class | Mechanism | Real examples |
| - | - | - |
| ASR substituted a real but wrong word | similar sound, often a different part of speech | "sever" ← server; "pee are" ← PR; "sea eye" ← CI; "stagging" ← staging; «Некто» ← Нет; «обременение» ← общение; «соврать» ← словарь |
| Phonetic distortion of a term | the term is not in the ASR vocabulary | "ingratiation tests" ← integration tests; "cubernetes" ← Kubernetes; «лиционер» ← лисенер; «силы» ← скилы |
| Split / merge | ASR cut one word into two known ones, or glued two | "de bug" ← debug; "alot" ← a lot; «до бага» ← дебаг; «иеть» ← и есть |
| Wrong script / transliteration | a term written in the wrong alphabet | "Jane" ← Jev; «мцп» ← MCP; «дебак» ← debug |
| Autocorrect / swipe | adjacent keys, autocorrect to a frequent word, junk | "ducking" ← (you know); "фвлм" ← вообще; "asdgh" ← junk |
| Wrong keyboard layout | typed with the other layout active; letters map key-for-key | "ujnjdj" ← готово; "ghbdtn" ← привет; "Ghbdtn" ← Привет; «руддщ» ← hello |

Wrong layout is the one deterministic class: the string looks like pure junk,
but mapping each key to the other layout recovers it exactly (QWERTY ↔ ЙЦУКЕН:
q→й w→ц e→у r→к t→е y→н u→г i→ш o→щ p→з [→х ]→ъ a→ф s→ы d→в f→а g→п h→р
j→о k→л l→д ;→ж '→э z→я x→ч c→с v→м b→и n→т m→ь ,→б .→ю). If a junk-looking
word decodes into a real word this way, that is the reading, at 0.95+.

The first class is the most frequent and the hardest: the word looks normal and
only the mismatch with context gives it away. That is exactly why this needs
you rather than a dictionary.

For candidates use: names of projects, modules, people and tools from the
context; terms the user already used; whatever is *logical to say* at this
point of the conversation. Say the garbled word out loud (in your head) — the
right one is often audible: "sea eye" → "CI", «со-врать» → «сло-варь».

## Step 3. Compose readings

Build 1–3 **complete** readings of the whole message. Change only what is
garbled: punctuation, word order, style, profanity stay untouched — you are
restoring, not editing. Order by likelihood and give each a `confidence` so the
sum is ≈ 1. Do not inflate: if two readings are equally plausible, 0.5/0.5 is
more honest than 0.8/0.2. Rule of thumb: one swapped word with an obvious
sound-alike — 0.9; two or three words each of which could be heard differently
— 0.5–0.6, and that is a reason to ask even when the reading feels smooth.

**Check before showing.** Walk the original word by word: every word is either
in the reading at its place or in your list of substitutions. Nothing dropped,
reordered or added. A reading is the original with point fixes, not a
paraphrase. Typical drift: "you he iss why the hell a key" → "why the hell a
key" («ты он» dropped, «иеть» never resolved); "did you connectedd here skill"
→ "did you connect skill here" (reordered). If a word of the original is still
unresolved after the check, go back to step 2 — do not stop at the first fix.

## Step 4. Decide: act or ask

Rule without exceptions: **if you mentally replaced even one word, show it
first — before anything else.** "First" is literal: the "Read as: …" line is the
first text of your turn, **before any tool call**. Not "before the text reply"
— before the action. Reading "Saratoga the pipeline" as "start the pipeline",
starting the pipeline and only then writing "Read as" is a violation: the user
learns how you read them when the pipeline is already running. Even
"connectedd → connected", even when the meaning is obvious. A silent fix looks
like understanding, but the user cannot see *what exactly* you understood and
cannot correct you until you have done the wrong thing. One line costs nothing;
a mistake found three messages later — or after a deploy — is expensive.

- **Top reading confidence ≥ 0.75** — act on it. Show one line, in the user's
  language, with the substitutions highlighted: `Read as: "…"` / «Понял как:
  „…“». Then act and answer.
- **The reading leads to an irreversible or costly action** (approve, start a
  pipeline, deploy, delete, send, pay) — the bar is higher: act without asking
  only at ≥ 0.9 and when the garbled word does not affect *what exactly* is
  done. "Approve the plan and Saratoga the pipeline" → "start the pipeline"
  0.95, the verb is obvious — fine. "Delete the <unresolved word>" — ask, even
  if the rest is clear.
- **Below the bar** — do not guess silently. Show the options and wait:

  ```
  Looks like the message has recognition errors. Did you mean:
  1. <reading 1>
  2. <reading 2>
  3. None of these
  ```

  Exception: if every reading leads to the same reply from you (they differ in
  an immaterial word), say "Read as: …", answer, and mention the alternative in
  one phrase. Do not make the user choose between things that make no
  difference to the task.

## Step 5. Record (if a `record_interpretation` tool is available)

If the session exposes an MCP tool `record_interpretation`, call it right away
with the readings, and again with `chosen` after the user answers. Those records
are the only evaluation data for this skill; without them nobody can tell where
it fails. If the tool is absent, skip this step — the skill works the same.

## Examples

**Input:** "Can you run the ingratiation tests and push to stagging"
**Output:** `Read as: "run the **integration** tests and push to **staging**"` —
0.95, act.

**Input:** «Меня интересует максимальная эффективность я даже не держусь за Джейн»
(context: the model Jev was under discussion)
**Output:** `Понял как: «…не держусь за **Jev**»` — 0.95, act.

**Input:** "Some encumbrance and tests will now be conducted tasks so we don't run around"
(context: we were deciding whether to test here or in another session)
**Readings:** "No, communication and tests will now be conducted here so we
don't run around" 0.5; the literal text 0.3; "Communication and tests will now
be run by tasks…" 0.2.
**Output:** the numbered list — the top is below 0.75 and the readings change
the meaning.

**Input:** "ujnjdj"
**Output:** `Read as: "готово"` (wrong keyboard layout) — 0.95, act.

**Input:** "run the tests, then commit"
**Output:** nothing — the message is clean.

## What not to do

- Do not "improve" the text: if the user wrote rudely or without commas, leave
  it. Replace only the garbled word, or the user stops trusting the readings.
- Do not correct unfamiliar proper names into familiar ones: "Vannevar" is not
  a typo of "Van Gogh". If the name appeared in context, it is correct.
- Do not call external spellcheckers or models for this task.
- Do not answer and **do not call tools** before you have shown the reading
  (step 4). Check before the first action of the turn: "did I change any word in
  my head? — then where is the `Read as` line?"
