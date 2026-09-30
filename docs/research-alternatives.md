# Survey of existing solutions (2026-09-29)

Task: recover the meaning of a message garbled by ASR / autocorrect / swipe —
Russian plus English jargon plus project names — with 2–3 readings and
probabilities, using a user glossary.

| Solution | Type | RU | Real-word / phonetic errors | Custom glossary | Cost | Verdict |
|---|---|---|---|---|---|---|
| [Yandex Speller](https://yandex.ru/dev/speller) + [pyaspeller](https://github.com/oriontvv/pyaspeller) | API | yes | partial (CatBoost context, but corrects single-word spelling; misses «Некто→Нет») | no | free, 10k req/day, attribution required | cheap pre-pass for non-word typos; measured: 0.20 top-1 and breaks jargon |
| [ai-forever/sage](https://github.com/ai-forever/sage) (fredt5-large / m2m100-1.2B / distilled-95m) | OSS MIT | yes, best open | spelling/punctuation; ASR substitutions and transliteration not covered; F1 RUSpellRU 84.5 | no; "normalises" jargon | free; 95M on CPU | baseline candidate; likely damages terms |
| [DeepPavlov spelling](https://docs.deeppavlov.ai/en/master/features/models/spelling_correction.html) | OSS | yes | non-word only, F1 ~53 | yes | free, heavy | outdated |
| JamSpell / SymSpell | OSS | own model | non-word | yes | free | SymSpell = fast candidate generator over a glossary |
| Hunspell / [SpellChecker-MCP](https://github.com/morahan/SpellChecker-MCP) | OSS/MCP | yes | no | yes | free | the only "MCP spellchecker"; useless here |
| [LanguageTool](https://languagetool.org) | OSS/Premium | basic | confusion pairs only en/de/es/fr/nl ([#569](https://github.com/languagetool-org/languagetool/issues/569)) | — | free / ~$5–8/mo | no RU real-word support |
| TextGears / Sapling / Bing Spell Check | API | partial | not claimed | partial | $ / free tier | no better than Speller; Bing half-retired |
| Grammarly / MS Editor | SaaS | no / no API | — | — | — | not applicable |
| Yandex SpeechKit biasing | ASR | yes | at recognition time | yes | per audio | we already have text |
| LLM GER ([HyPoradise](https://arxiv.org/abs/2309.15701), [Cambridge](https://arxiv.org/html/2409.09554v1), [Fewer Hallucinations](https://arxiv.org/abs/2505.24347)) | papers | EN datasets; RU — [t5-russian-spell](https://huggingface.co/UrukHan/t5-russian-spell) | exactly this problem | via prompt | LLM | same approach as ours; no ready RU tool |
| Claude Code `UserPromptSubmit` hook | plugin | — | — | — | — | cannot rewrite the prompt ([#34390](https://github.com/anthropics/claude-code/issues/34390)); no ready hooks |

Negative result on LLM post-correction: [Vosk, 2025](https://alphacephei.com/nsh/2025/03/15/generative-error-correction.html)
— eight 4–9B models plus Gemini Flash Lite on Russian telephony: WER 15.9 → best
14.6; local 8B models worse than baseline; strong over-correction of rare names
unknown to the LLM; very prompt-sensitive. Consequence for us: project names must
be in context, or the model "fixes" them.

## Conclusions

1. **Nothing off the shelf** does contextual real-word ASR correction for
   Russian with a user glossary, returns 2–3 readings with probabilities, or
   hooks into Claude Code input. The skill fills that gap.
2. Speller and `sage` were worth measuring as baselines; Speller measured 0.20
   top-1 and damaged jargon.
3. From the literature: "LLM + domain word list + do not change words outside
   the list", and the three-stage detect → candidates → verify scheme — which
   is the skill's structure (agent generates, code/Jev can verify).
4. Synthetic eval data: `sage`'s SBSC corruptor yields typos but not phonetic
   substitutions — those only come from the real inbox.

Not verified: TextGears quality on RU; Bing's RU context; t5-russian-spell license.
