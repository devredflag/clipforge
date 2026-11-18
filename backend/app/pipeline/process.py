"""Orquestra o processamento de uma fonte: vídeo gravado (VOD) ou live."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable

from .. import config, db, media
from . import download as dl
from .highlights import pick_highlights
from .render import render_clip
from .transcribe import Transcriber, Word, get_transcriber

log = logging.getLogger("clipforge.process")

RMS_HOP = 0.5


def badge_for(settings, idx: int) -> str | None:
    return f"{settings.part_label.upper()} {idx}" if settings.show_part_badge else None


def render_and_register(source_id: int, cand, idx: int, words: list[Word], src_path: Path, settings,
                        src_offset: float = 0.0) -> int:
    """Cria a linha do corte, renderiza e marca como pronto/aprovado."""
    clip_id = db.create_clip(source_id, idx, cand.start, cand.end, cand.score, cand.title, cand.reason)
    out_dir = config.DATA_DIR / "clips" / str(source_id)
    try:
        out, thumb = render_clip(
            src_path, cand.start, cand.end, words, out_dir, name=f"clip_{idx:03d}", layout=settings.layout,
            normalize=settings.normalize_audio, font=settings.caption_font, size=settings.caption_size,
            uppercase=settings.caption_uppercase, color=settings.caption_color,
            highlight=settings.caption_highlight, badge_text=badge_for(settings, idx), src_offset=src_offset,
        )
    except Exception as exc:  # noqa: BLE001 — qualquer falha de render vira status do corte
        log.exception("Falha ao renderizar corte %s", clip_id)
        db.update("clips", clip_id, status="failed", error=str(exc)[-500:])
        return clip_id
    status = "approved" if settings.auto_approve else "ready"
    db.update("clips", clip_id, file=str(out), thumb=str(thumb), status=status)
    if status == "approved":
        try:
            from .. import scheduler
            scheduler.plan_all()
        except Exception:  # noqa: BLE001 — agendar não pode derrubar o processamento
            log.exception("Falha ao agendar publicação")
    return clip_id


def ollama_args(settings) -> tuple[str, str] | None:
    return (settings.ollama_url, settings.ollama_model) if settings.ollama_enabled else None


def process_vod(source_id: int, *, transcriber: Transcriber | None = None,
                downloader: Callable | None = None, stop: Callable[[], bool] = lambda: False) -> None:
    settings = config.get_settings()
    src = db.get_source(source_id)
    work = config.DATA_DIR / "sources" / str(source_id)
    work.mkdir(parents=True, exist_ok=True)

    # 1) baixar -------------------------------------------------------------------------------
    db.set_progress(source_id, "downloading", 0.0, "Baixando vídeo")
    video = (downloader or dl.download_video)(
        src["url"], work, settings, lambda p: db.set_progress(source_id, "downloading", p * 0.15)
    )
    info = media.probe(video)
    db.update("sources", source_id, duration=info["duration"])
    if not info["has_audio"]:
        raise RuntimeError("O vídeo não tem faixa de áudio — não há o que transcrever.")

    # 2) transcrever --------------------------------------------------------------------------
    db.set_progress(source_id, "transcribing", 0.15, "Extraindo áudio")
    wav = work / "audio.wav"
    media.extract_audio(video, wav)
    rms = media.wav_rms(wav, RMS_HOP)

    cache = work / "words.json"
    if cache.exists():
        words = [Word(**w) for w in json.loads(cache.read_text(encoding="utf-8"))]
    else:
        db.set_progress(source_id, "transcribing", 0.15, "Transcrevendo (Whisper)")
        tr = transcriber or get_transcriber(settings)
        lang = None if settings.language == "auto" else settings.language
        words = tr.transcribe(str(wav), lang, lambda p: db.set_progress(source_id, "transcribing", 0.15 + p * 0.45))
        cache.write_text(json.dumps([w.__dict__ for w in words], ensure_ascii=False), encoding="utf-8")
    if stop():
        db.set_progress(source_id, "stopped", detail="Interrompido")
        return
    if len(words) < 20:
        raise RuntimeError("Quase nenhuma fala detectada — sem fala não dá para legendar nem escolher cortes.")

    # 3) escolher trechos ---------------------------------------------------------------------
    db.set_progress(source_id, "analyzing", 0.62, "Escolhendo os melhores trechos")
    chosen = pick_highlights(
        words, rms, min_s=settings.clip_min_seconds, max_s=settings.clip_max_seconds,
        limit=settings.max_clips_per_source, min_score=settings.min_score,
        ollama=ollama_args(settings), rms_hop=RMS_HOP,
    )
    if not chosen:
        db.set_progress(source_id, "done", 1.0, "Nenhum trecho passou da nota mínima — reduza 'min_score' nas configurações")
        return

    # 4) renderizar ---------------------------------------------------------------------------
    for n, cand in enumerate(chosen, 1):
        if stop():
            db.set_progress(source_id, "stopped", detail="Interrompido")
            return
        db.set_progress(source_id, "rendering", 0.65 + 0.35 * (n - 1) / len(chosen), f"Renderizando corte {n}/{len(chosen)}")
        render_and_register(source_id, cand, db.next_clip_idx(source_id), words, video, settings)
    db.set_progress(source_id, "done", 1.0, f"{len(chosen)} cortes gerados")


def run_source(source_id: int, **kw) -> None:
    """Ponto de entrada do job: detecta se é live ou vídeo gravado e delega."""
    settings = config.get_settings()
    src = db.get_source(source_id)
    try:
        info = kw.pop("info", None) or (kw.pop("info_fn", None) or dl.probe_url)(src["url"], settings)
        kw.pop("info_fn", None)
        db.update("sources", source_id, title=info["title"], channel=info["channel"],
                  thumbnail=info["thumbnail"], video_id=info["id"], duration=info["duration"],
                  kind="live" if info["live_status"] in ("is_live", "is_upcoming") else "vod")
        if info["live_status"] in ("is_live", "is_upcoming"):
            from .live import run_live
            run_live(source_id, info, **kw)
        else:
            process_vod(source_id, **kw)
    except Exception as exc:  # noqa: BLE001
        log.exception("Fonte %s falhou", source_id)
        db.update("sources", source_id, status="failed", error=str(exc)[-800:])
