"""Publicadores por plataforma."""
from __future__ import annotations

from . import tiktok, youtube

REGISTRY = {"youtube": youtube, "tiktok": tiktok}


def get(platform: str):
    try:
        return REGISTRY[platform]
    except KeyError as exc:
        raise ValueError(f"Plataforma desconhecida: {platform}") from exc
