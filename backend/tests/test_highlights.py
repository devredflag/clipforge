from app.pipeline import highlights as hl
from app.pipeline.transcribe import Word

from conftest import build_transcript, make_sentences


def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def test_sentences_split_on_punctuation_and_pause():
    words = make_sentences([(0, "Olá pessoal. Tudo bem?", 0.3), (10, "Outra frase sem ponto", 0.3)])
    sents = hl.words_to_sentences(words)
    assert [s.text for s in sents] == ["Olá pessoal.", "Tudo bem?", "Outra frase sem ponto"]


def test_long_sentence_is_broken_at_longest_pause():
    words = [Word(f"w{i}", i * 0.5, i * 0.5 + 0.4) for i in range(40)]  # 20 s sem pontuação
    words[19] = Word("w19", words[19].start, words[19].end)
    words[20] = Word("w20", words[20].start + 0.6, words[20].end + 0.6)  # pausa maior no meio
    sents = hl.words_to_sentences(words, max_len=14)
    assert all(s.end - s.start <= 15 for s in sents)


def test_picks_strong_regions_not_boring_ones():
    words = build_transcript()
    chosen = hl.pick_highlights(words, None, min_s=15, max_s=40, limit=4, min_score=0.6)
    assert len(chosen) >= 2, "há dois trechos fortes no roteiro"
    hot = [(25, 55), (80, 115)]
    for c in chosen:
        assert 15 <= c.duration <= 40
        assert any(overlap(c.start, c.end, h0, h1) >= 0.7 * c.duration for h0, h1 in hot), (c.start, c.end)
    # sem sobreposição e em ordem cronológica
    for a, b in zip(chosen, chosen[1:]):
        assert a.end <= b.start


def test_default_min_score_rejects_boring_regions():
    from app import config
    words = build_transcript()
    s = config.Settings()
    chosen = hl.pick_highlights(words, None, min_s=15, max_s=40, limit=0, min_score=s.min_score)
    assert chosen
    for c in chosen:
        assert not (c.end <= 25 or (c.start >= 55 and c.end <= 80)), (c.start, c.end)


def test_clip_starts_and_ends_on_sentence_boundaries():
    words = build_transcript()
    for c in hl.pick_highlights(words, None, min_s=15, max_s=40, limit=4, min_score=0.6):
        assert c.words[-1].text.endswith(hl.TERMINAL)
        assert c.start in {w.start for w in words}


def test_region_limits_candidates():
    words = build_transcript()
    chosen = hl.pick_highlights(words, None, min_s=15, max_s=40, limit=0, min_score=0.3, region=(0, 60))
    assert chosen and all(c.end <= 60 for c in chosen)


def test_min_score_filters_everything_when_high():
    words = build_transcript()
    assert hl.pick_highlights(words, None, min_s=15, max_s=40, limit=4, min_score=0.99) == []


def test_ollama_rerank_changes_choice_and_sets_title():
    words = build_transcript()
    calls = []

    def judge(text, url, model):
        calls.append(text)
        good = "ganhar 10 mil" in text
        return {"score": 1.0 if good else 0.1, "title": "Título da IA" if good else "", "reason": "teste"}

    chosen = hl.pick_highlights(words, None, min_s=15, max_s=40, limit=2, min_score=0.2,
                                ollama=("http://x", "m"), judge=judge)
    assert calls, "o juiz deveria ter sido consultado"
    assert chosen[0].title == "Título da IA" or any(c.title == "Título da IA" for c in chosen)


def test_ollama_down_falls_back_to_rules():
    words = build_transcript()

    def judge(*_a):
        raise hl.OllamaUnavailable("fora do ar")

    chosen = hl.pick_highlights(words, None, min_s=15, max_s=40, limit=3, min_score=0.3,
                                ollama=("http://x", "m"), judge=judge)
    baseline = hl.pick_highlights(words, None, min_s=15, max_s=40, limit=3, min_score=0.3)
    assert [(c.start, c.end) for c in chosen] == [(c.start, c.end) for c in baseline]
    assert all(c.title for c in chosen)  # título de reserva


def test_fallback_title_is_trimmed():
    c = hl.Candidate(0, 30, [Word("a", 0, 1)], "Você sabia que ninguém conta esse segredo para ninguém hoje em dia?")
    t = hl.fallback_title(c, 1)
    assert len(t) <= 62 and t[0].isupper()
