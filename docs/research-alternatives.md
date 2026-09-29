# Обзор существующих решений (2026-09-29)

Задача: восстановить смысл сообщения с телефона (ASR / T9 / свайп), русский +
английский жаргон + имена проекта, 2–3 прочтения с вероятностями, свой глоссарий.

| Решение | Тип | RU | Real-word / фонетика | Свой глоссарий | Стоимость | Вердикт |
|---|---|---|---|---|---|---|
| [Yandex Speller](https://yandex.ru/dev/speller) + [pyaspeller](https://github.com/oriontvv/pyaspeller) | API | да | частично (контекст CatBoost, но правит орфографию отдельных слов; «Некто→Нет» не поймает) | нет | бесплатно, 10k запр./сут, нужна ссылка на сервис | дешёвый pre-pass для non-word опечаток/склеек |
| [ai-forever/sage](https://github.com/ai-forever/sage) (fredt5-large / m2m100-1.2B / distilled-95m) | OSS MIT | да, лучший открытый | орфография/пунктуация; ASR-подстановки и транслит не покрыты; F1 RUSpellRU 84.5 | нет; будет «нормализовать» жаргон | бесплатно; 95M на CPU | baseline для eval; вероятно портит термины |
| [DeepPavlov spelling](https://docs.deeppavlov.ai/en/master/features/models/spelling_correction.html) | OSS | да | только non-word, F1 ~53 | да | бесплатно, тяжёлый | устарел |
| JamSpell / SymSpell | OSS | своя модель | non-word | да | бесплатно | SymSpell — быстрый генератор кандидатов по глоссарию |
| Hunspell / [SpellChecker-MCP](https://github.com/morahan/SpellChecker-MCP) | OSS/MCP | да | нет | да | бесплатно | единственный «MCP-спеллчекер», бесполезен |
| [LanguageTool](https://languagetool.org) | OSS/Premium | базово | confusion-pairs только en/de/es/fr/nl ([#569](https://github.com/languagetool-org/languagetool/issues/569)) | — | free / ~$5–8 мес | для ru real-word — нет |
| TextGears / Sapling / Bing Spell Check | API | ru есть/частично | не заявлено | частично | $ / free-tier | не лучше Спеллера; Bing полуживой |
| Grammarly / MS Editor | SaaS | нет / нет API | — | — | — | мимо |
| Yandex SpeechKit biasing | ASR | да | на этапе распознавания | да | по времени | у нас уже текст — не применимо |
| LLM GER ([HyPoradise](https://arxiv.org/abs/2309.15701), [Cambridge](https://arxiv.org/html/2409.09554v1), [Fewer Hallucinations](https://arxiv.org/abs/2505.24347)) | papers | датасеты en; ru — [t5-russian-spell](https://huggingface.co/UrukHan/t5-russian-spell) | именно про это | через промпт | LLM | подход = наш; готового ru-инструмента нет |
| Claude Code hook `UserPromptSubmit` | plugin | — | — | — | — | хук не может заменить промпт ([#34390](https://github.com/anthropics/claude-code/issues/34390)); готовых хуков нет |

Отрицательный результат по LLM-постобработке: [Vosk, 2025](https://alphacephei.com/nsh/2025/03/15/generative-error-correction.html) —
8 моделей 4–9B + Gemini Flash Lite на русской телефонии: WER 15.9 → лучшее 14.6;
локальные 8B хуже baseline; сильная перекоррекция редких имён, неизвестных LLM;
качество очень чувствительно к промпту. Вывод для нас: глоссарий имён проекта в
промпте обязателен, иначе модель их «исправит».

## Выводы

1. **Off-the-shelf не существует**: контекстный корректор real-word ASR-ошибок для
   русского с пользовательским глоссарием; выдача 2–3 прочтений с вероятностями;
   MCP/хук для Claude Code, меняющий ввод. Наш `interpreter` закрывает эту нишу.
2. **Стоит прогнать как baseline** на `evals/inbox.jsonl`: Yandex Speller и
   `sage-fredt5-distilled-95m` — измерить, сколько ломают термины.
3. **Взять из литературы**: «LLM + список доменных слов + запрет менять слова не из
   списка»; трёхстадийная схема детект → кандидаты → верификация (совпадает с нашей
   архитектурой: агент генерирует, Jev/код верифицирует).
4. Синтетика для eval: SBSC-корруптор из `sage` даёт опечатки, но не фонетические
   подстановки — их только из реального inbox.

Не проверено: качество TextGears на ru; ru-контекст у Bing; лицензия t5-russian-spell.
