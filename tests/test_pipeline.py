from interpreter import candidates as C
from interpreter.jev import FakeJev, strip_hints
from interpreter.pipeline import Interpreter

GLOSSARY = ["дебаг", "скилы", "лисенер", "Ванневар", "коммит", "деплой"]
MESSAGE = (
    "нужно провести до бага и подсмотреть все силы возможно какой-то лиционер отвалился. "
    "Или названия проекта, например Анвар, может быть непонятно."
)


def test_candidates_merge_two_tokens():
    toks = C.tokenize("провести до бага и")
    names = [t.text for t in toks]
    for word in ("до", "бага"):
        cands = C.generate(toks, names.index(word), GLOSSARY)
        assert cands and cands[0].text == "дебаг"
        assert (cands[0].start, cands[0].span) == (names.index("до"), 2)


def test_phonetic_match():
    assert C.similarity("лиционер", "лисенер") >= 0.6
    assert C.similarity("Анвар", "Ванневар") >= 0.6


def test_cross_script_match():
    assert C.similarity("мцп", "MCP") >= 0.6
    assert C.similarity("лисинер", "listener") >= 0.6
    assert C.similarity("дебак", "debug") >= 0.6


def test_unresolved_reported_when_no_candidates():
    class Suspicious(FakeJev):
        def ask(self, state, questions):
            out = super().ask(state, questions)
            for k in out:
                if k.startswith("sus_"):
                    out[k]["noul"] = 0.9
            return out
    result = Interpreter(Suspicious()).interpret("публикация из гриха", ["npm"])
    assert [u.word for u in result.unresolved] == ["публикация", "гриха"]
    assert result.variants[0].text == "публикация из гриха"
    assert not result.needs_clarification


def test_end_to_end_offline():
    fake = FakeJev()
    result = Interpreter(fake).interpret(MESSAGE, GLOSSARY, context="обсуждаем агента и его скилы")
    top = result.variants[0].text
    assert "провести дебаг и" in top
    assert "скилы" in top
    assert "лисенер" in top
    assert "Ванневар" in top
    assert result.variants[0].probability > 0
    assert len(fake.calls) == 1  # everything goes to Jev in a single request


def test_clean_message_short_circuits():
    fake = FakeJev()
    result = Interpreter(fake).interpret("запусти тесты, потом коммит", GLOSSARY)
    assert not result.flagged
    assert result.variants[0].text == "запусти тесты, потом коммит"
    assert not result.needs_clarification
    assert len(fake.calls) == 1


def test_strip_hints_removes_fake_keys():
    q = {"a": {"type": "choice", "instructions": "x", "criteria": {"o": {"_fake_score": 1, "k": "v"}, "p": {"_fake_score": 2}}, "_fake_hint": 3}}
    s = strip_hints(q)
    assert "_fake_hint" not in s["a"]
    assert s["a"]["criteria"]["o"] == {"k": "v"}
    assert s["a"]["criteria"]["p"] is None


def test_case_preserved():
    toks = C.tokenize("Анвар сломался")
    from interpreter.pipeline import _render
    assert _render("Анвар сломался", toks, {0: ("ванневар", 1)}) == "Ванневар сломался"
