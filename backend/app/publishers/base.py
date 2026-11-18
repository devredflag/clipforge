"""Tipos e utilitários comuns aos publicadores."""
from __future__ import annotations

import re


class PublishError(Exception):
    """Falha ao publicar. `retryable`: vale tentar de novo. `quota`: limite diário da plataforma estourou."""

    def __init__(self, message: str, *, retryable: bool = True, quota: bool = False):
        super().__init__(message)
        self.retryable = retryable
        self.quota = quota


def hashtag_string(tags: list[str]) -> str:
    out = []
    for t in tags:
        t = re.sub(r"[^\w]", "", t, flags=re.UNICODE)
        if t:
            out.append(f"#{t}")
    return " ".join(out)


def compose_title(clip: dict, settings, limit: int = 100) -> str:
    """'<título> | Parte N' — o sufixo nunca é cortado, só o título."""
    suffix = f" | {settings.part_label} {clip['idx']}"
    base = (clip.get("title") or "Corte").strip()
    room = limit - len(suffix)
    if len(base) > room:
        base = base[: max(1, room - 1)].rstrip() + "…"
    return base + suffix


def compose_description(clip: dict, source: dict | None, settings, limit: int = 4800) -> str:
    parts = []
    if clip.get("description"):
        parts.append(clip["description"].strip())
    parts.append(f"{settings.part_label} {clip['idx']}")
    if source and source.get("url"):
        credit = f"Vídeo completo: {source['url']}"
        if source.get("channel"):
            credit += f" ({source['channel']})"
        parts.append(credit)
    tags = hashtag_string(settings.hashtags)
    if tags:
        parts.append(tags)
    return "\n\n".join(parts)[:limit]


def compose_caption(clip: dict, settings, limit: int = 2200) -> str:
    """Legenda do TikTok: título + parte + hashtags, dentro do limite de 2200 caracteres."""
    tags = hashtag_string(settings.hashtags)
    head = compose_title(clip, settings, limit=max(20, limit - len(tags) - 2))
    return f"{head} {tags}".strip()[:limit]
