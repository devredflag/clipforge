"""Escolha dos melhores trechos.

1. A transcrição vira frases; janelas de frases viram candidatos de `min` a `max` segundos.
2. Cada candidato recebe nota por regras (gancho, ritmo de fala, silêncio, ênfase, energia de áudio, fechamento).
3. Opcional: um LLM local (Ollama) reavalia os melhores candidatos e sugere título.
4. Seleção gulosa sem sobreposição.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import numpy as np
import requests

from .transcribe import Word

TERMINAL = (".", "?", "!", "…")

HOOK_PATTERNS = [
    r"\bsegredo\b", r"\bning[uú]em\b", r"\bnunca\b", r"\bjamais\b", r"\berro\b", r"\bverdade\b", r"\bmentira\b",
    r"\bcuidado\b", r"\baten[cç][aã]o\b", r"\babsurdo\b", r"\bchocante\b", r"\bincr[ií]vel\b", r"\bdescobri\b",
    r"\bimagina\b", r"\bpare\b", r"\bpor que\b", r"\bcomo\b", r"\bdica\b", r"\btruque\b", r"\bmelhor\b",
    r"\bpior\b", r"\bmilh[oõ]es?\b", r"\bdinheiro\b", r"\bsurpreend", r"\bacredit",
    r"\bsecret\b", r"\bnobody\b", r"\bnever\b", r"\bmistake\b", r"\btruth\b", r"\bwarning\b", r"\binsane\b",
    r"\bshocking\b", r"\bdiscovered\b", r"\bimagine\b", r"\bstop\b", r"\bwhy\b", r"\bhow\b", r"\btip\b",
    r"\btrick\b", r"\bbest\b", r"\bworst\b", r"\bmillion\b", r"\bbelieve\b",
]
_HOOK_RE = re.compile("|".join(HOOK_PATTERNS), re.IGNORECASE)


@dataclass
class Sentence:
    words: list[Word]

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass
class Candidate:
    start: float
    end: float
    words: list[Word]
    first_sentence: str
    rule_score: float = 0.0
    score: float = 0.0
    title: str = ""
    reason: str = ""
    features: dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


def words_to_sentences(words: list[Word], pause: float = 0.8, max_len: float = 14.0) -> list[Sentence]:
    """Agrupa palavras em frases por pontuação ou pausa longa; quebra frases muito longas na maior pausa."""
    sentences: list[Sentence] = []
    cur: list[Word] = []

    def flush() -> None:
        nonlocal cur
        if cur:
            sentences.append(Sentence(cur))
            cur = []

    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        gap = (nxt.start - w.end) if nxt else 99.0
        if w.text.endswith(TERMINAL) or gap > pause:
            flush()
        elif cur[-1].end - cur[0].start > max_len:
            # quebra na maior pausa interna
            gaps = [(cur[j + 1].start - cur[j].end, j) for j in range(len(cur) - 1)]
            if gaps:
                _, j = max(gaps)
                head, tail = cur[: j + 1], cur[j + 1:]
                sentences.append(Sentence(head))
                cur = tail
    flush()
    return sentences


def build_candidates(sentences: list[Sentence], min_s: float, max_s: float) -> list[Candidate]:
    out: list[Candidate] = []
    n = len(sentences)
    for i in range(n):
        words: list[Word] = []
        for j in range(i, n):
            words = words + sentences[j].words
            dur = words[-1].end - sentences[i].start
            if dur > max_s:
                break
            if dur >= min_s:
                out.append(Candidate(sentences[i].start, words[-1].end, list(words), sentences[i].text))
    return out


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def score_candidates(cands: list[Candidate], rms: np.ndarray | None, min_s: float, max_s: float,
                     rms_hop: float = 0.5, next_word_start: dict[int, float] | None = None) -> None:
    """Preenche rule_score/score (0..1). `rms` = energia por `rms_hop` s do áudio inteiro."""
    target = (min_s + max_s) / 2
    median = float(np.median(rms)) if rms is not None and len(rms) else 0.0
    for c in cands:
        dur = max(c.duration, 0.1)
        n = len(c.words)
        wps = n / dur
        pace = _clamp(1 - abs(wps - 2.8) / 2.2)

        silence = 0.0
        for a, b in zip(c.words, c.words[1:]):
            gap = b.start - a.end
            if gap > 0.8:
                silence += gap
        silence_score = 1 - _clamp(silence / dur * 3)

        first = c.first_sentence
        hook = 0.0
        if "?" in first:
            hook += 0.5
        if _HOOK_RE.search(first):
            hook += 0.4
        if re.search(r"\d", first):
            hook += 0.2
        hook = _clamp(hook)

        text = c.text
        hits = len(_HOOK_RE.findall(text)) + text.count("!") + text.count("?")
        emph = _clamp(hits / (dur / 15) / 3)

        if rms is not None and len(rms) and median > 0:
            a, b = int(c.start / rms_hop), max(int(c.end / rms_hop), int(c.start / rms_hop) + 1)
            seg = rms[a:b]
            ratio = float(seg.mean()) / median if len(seg) else 1.0
            energy = _clamp((ratio - 0.8) / 1.2)
        else:
            energy = 0.5

        closure = 1.0 if c.words[-1].text.endswith(TERMINAL) else 0.4
        length = _clamp(1 - abs(dur - target) / max(target, 1))

        score = (0.22 * hook + 0.12 * pace + 0.12 * silence_score + 0.14 * emph
                 + 0.16 * energy + 0.14 * closure + 0.10 * length)
        if n < 20:
            score *= 0.5  # trecho com pouca fala não vira corte
        c.rule_score = c.score = round(score, 4)
        c.features = {"hook": round(hook, 2), "pace": round(pace, 2), "silence": round(silence_score, 2),
                      "emphasis": round(emph, 2), "energy": round(energy, 2), "closure": closure,
                      "length": round(length, 2)}


def select_non_overlapping(cands: list[Candidate], limit: int, min_score: float, min_gap: float = 0.0) -> list[Candidate]:
    chosen: list[Candidate] = []
    for c in sorted(cands, key=lambda x: x.score, reverse=True):
        if c.score < min_score:
            break
        if any(c.start < o.end + min_gap and c.end > o.start - min_gap for o in chosen):
            continue
        chosen.append(c)
        if limit and len(chosen) >= limit:
            break
    return sorted(chosen, key=lambda x: x.start)


# ---- Ollama (opcional) ------------------------------------------------------------------------

OLLAMA_PROMPT = """Você avalia trechos de vídeo para virarem cortes curtos (Shorts/TikTok).
Responda SOMENTE com JSON no formato {{"score": <0-10>, "title": "<título curto e chamativo, até 60 caracteres, no idioma do trecho>", "reason": "<uma frase>"}}.
Dê nota alta para trechos com gancho forte no início, ideia completa, emoção, curiosidade ou valor prático.
Dê nota baixa para trechos que dependem de contexto anterior, são vagos ou terminam no meio de uma ideia.

TRECHO:
\"\"\"{text}\"\"\"
"""


class OllamaUnavailable(RuntimeError):
    pass


def ollama_judge(text: str, url: str, model: str, timeout: float = 90.0) -> dict:
    try:
        r = requests.post(
            f"{url.rstrip('/')}/api/generate",
            json={"model": model, "prompt": OLLAMA_PROMPT.format(text=text[:3500]), "stream": False,
                  "format": "json", "options": {"temperature": 0.2}},
            timeout=timeout,
        )
        r.raise_for_status()
        data = json.loads(r.json().get("response", "{}"))
    except (requests.RequestException, json.JSONDecodeError, ValueError) as exc:
        raise OllamaUnavailable(str(exc)) from exc
    score = float(data.get("score", 0))
    return {"score": _clamp(score / 10), "title": str(data.get("title", ""))[:80].strip(),
            "reason": str(data.get("reason", ""))[:200].strip()}


def rerank_with_ollama(cands: list[Candidate], url: str, model: str, judge=ollama_judge) -> bool:
    """Mistura a nota das regras (40%) com a do LLM (60%). Devolve False se o Ollama não respondeu."""
    ok = False
    for c in cands:
        try:
            verdict = judge(c.text, url, model)
        except OllamaUnavailable:
            if not ok:
                return False  # nunca respondeu: desiste sem demorar
            continue
        ok = True
        c.score = round(0.4 * c.rule_score + 0.6 * verdict["score"], 4)
        c.title = verdict["title"] or c.title
        c.reason = verdict["reason"] or c.reason
    return ok


def fallback_title(c: Candidate, idx: int) -> str:
    text = re.sub(r"\s+", " ", c.first_sentence).strip(" .,;:-")
    if len(text) < 12:
        return f"Corte {idx}"
    if len(text) > 60:
        text = text[:60].rsplit(" ", 1)[0] + "…"
    return text[0].upper() + text[1:]


def pick_highlights(words: list[Word], rms: np.ndarray | None, *, min_s: float, max_s: float, limit: int,
                    min_score: float, ollama: tuple[str, str] | None = None, judge=ollama_judge,
                    region: tuple[float, float] | None = None, rms_hop: float = 0.5) -> list[Candidate]:
    """Função única usada por vídeos gravados e lives. `region` restringe a janela (start, end) permitida."""
    if region:
        words = [w for w in words if w.start >= region[0] and w.end <= region[1]]
    sentences = words_to_sentences(words)
    cands = build_candidates(sentences, min_s, max_s)
    if region:
        cands = [c for c in cands if c.start >= region[0] and c.end <= region[1]]
    if not cands:
        return []
    score_candidates(cands, rms, min_s, max_s, rms_hop)
    if ollama:
        pool = select_non_overlapping(cands, limit=max(limit * 3, 9) if limit else 30, min_score=0.0)
        # com poucos candidatos independentes, usa também os melhores sobrepostos
        if len(pool) < 3:
            pool = sorted(cands, key=lambda c: c.score, reverse=True)[:6]
        if rerank_with_ollama(pool, ollama[0], ollama[1], judge=judge):
            cands = pool
    chosen = select_non_overlapping(cands, limit=limit, min_score=min_score)
    for i, c in enumerate(chosen, 1):
        if not c.title:
            c.title = fallback_title(c, i)
    return chosen
