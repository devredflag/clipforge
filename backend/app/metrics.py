"""Coleta de métricas reais dos vídeos publicados e resumo do mês.

Nada aqui é inventado: os números vêm das APIs das plataformas (YouTube Data API; TikTok Display API quando
liberada). Se uma plataforma não fornece métricas para a conta, o vídeo entra como "sem métricas" e isso é dito
claramente — em vez de mostrar zero como se fosse engajamento real.
"""
from __future__ import annotations

import logging
import statistics
from datetime import datetime, timedelta, timezone
from typing import Callable

from . import db
from .publishers import get as get_publisher

log = logging.getLogger("clipforge.metrics")

REFRESH_EVERY = timedelta(hours=6)   # com que frequência reconsultar as views de um post
PLATFORMS = ("youtube", "tiktok")


def refresh_due(publisher_for: Callable = get_publisher, now: datetime | None = None, force: bool = False) -> int:
    """Atualiza as métricas dos posts publicados cujo último dado está velho. Devolve quantos atualizou."""
    now = now or datetime.now(timezone.utc)
    rows = db.query(
        "SELECT p.id, p.platform, p.external_id, m.updated_at AS m_updated "
        "FROM posts p LEFT JOIN metrics m ON m.post_id = p.id "
        "WHERE p.status = 'published' AND p.external_id IS NOT NULL")
    done = 0
    for r in rows:
        if not force and r["m_updated"]:
            try:
                if now - datetime.fromisoformat(r["m_updated"]) < REFRESH_EVERY:
                    continue
            except ValueError:
                pass
        account = db.get_account(r["platform"])
        if not account:
            db.upsert_metrics(r["id"], available=False, note="Conta desconectada.")
            continue
        try:
            stats = publisher_for(r["platform"]).fetch_stats(account, r["external_id"])
        except Exception as exc:  # noqa: BLE001
            log.warning("Métricas do post %s falharam: %s", r["id"], exc)
            stats = {"available": False, "note": str(exc)[:160]}
        db.upsert_metrics(
            r["id"], views=stats.get("views"), likes=stats.get("likes"), comments=stats.get("comments"),
            shares=stats.get("shares"), available=bool(stats.get("available")), note=stats.get("note"))
        done += 1
    if done:
        log.info("Métricas atualizadas: %d posts", done)
    return done


def summary(now: datetime | None = None, window_days: int = 30) -> dict:
    """Resumo do período: total de posts publicados, média de views, melhores/piores e lista por vídeo,
    com rótulo de desempenho relativo à média de cada plataforma."""
    now = now or datetime.now(timezone.utc)
    since = (now - timedelta(days=window_days)).isoformat(timespec="seconds")
    rows = db.query(
        "SELECT p.id, p.platform, p.published_at, p.external_url, c.title, c.idx, "
        "m.views, m.likes, m.comments, m.shares, m.available, m.note "
        "FROM posts p JOIN clips c ON c.id = p.clip_id LEFT JOIN metrics m ON m.post_id = p.id "
        "WHERE p.status = 'published' AND p.published_at >= ? ORDER BY p.published_at DESC", [since])

    per_platform_views: dict[str, list[int]] = {p: [] for p in PLATFORMS}
    for r in rows:
        if r["available"] and r["views"] is not None:
            per_platform_views.setdefault(r["platform"], []).append(r["views"])
    avg = {p: (round(statistics.mean(v)) if v else None) for p, v in per_platform_views.items()}
    median = {p: (statistics.median(v) if v else None) for p, v in per_platform_views.items()}

    def performance(r: dict) -> str:
        if not r["available"] or r["views"] is None:
            return "sem_dados"
        med = median.get(r["platform"])
        if not med:
            return "sem_dados"
        if r["views"] >= med * 1.3:
            return "acima"
        if r["views"] <= med * 0.6:
            return "abaixo"
        return "media"

    videos = []
    for r in rows:
        videos.append({
            "post_id": r["id"], "platform": r["platform"], "title": r["title"], "idx": r["idx"],
            "url": r["external_url"], "published_at": r["published_at"],
            "views": r["views"], "likes": r["likes"], "comments": r["comments"], "shares": r["shares"],
            "available": bool(r["available"]), "note": r["note"], "performance": performance(r),
        })

    measured = [v for v in videos if v["available"] and v["views"] is not None]
    total_views = sum(v["views"] for v in measured)
    best = max(measured, key=lambda v: v["views"], default=None)
    worst = min(measured, key=lambda v: v["views"], default=None)

    return {
        "window_days": window_days,
        "published_count": len(rows),
        "measured_count": len(measured),
        "total_views": total_views,
        "avg_views": round(total_views / len(measured)) if measured else None,
        "avg_views_by_platform": avg,
        "best": best, "worst": worst,
        "videos": videos,
        "platforms_measured": sorted({v["platform"] for v in measured}),
    }


def alerts(now: datetime | None = None) -> list[dict]:
    """Avisos acionáveis, derivados do estado real do sistema (nada decorativo)."""
    from . import config, media

    now = now or datetime.now(timezone.utc)
    settings = config.get_settings()
    out: list[dict] = []

    def add(level: str, title: str, detail: str = "", tab: str | None = None) -> None:
        out.append({"level": level, "title": title, "detail": detail, "tab": tab})

    # ffmpeg
    tools = media.tools_status()
    if not (tools["ffmpeg"] and tools["ffprobe"]):
        add("error", "ffmpeg não encontrado", "Sem ele não dá para gerar cortes. Instale o ffmpeg e reinicie.", "settings")

    # contas: plataforma ativa mas desconectada
    for p in settings.platforms:
        if not db.get_account(p):
            name = {"youtube": "YouTube", "tiktok": "TikTok"}.get(p, p)
            add("warning", f"{name} não está conectado",
                f"Há cortes sendo gerados, mas nada será publicado no {name} até conectar a conta.", "accounts")

    # publicações que falharam (últimos 7 dias)
    week = (now - timedelta(days=7)).isoformat(timespec="seconds")
    failed = db.query("SELECT platform, COUNT(*) n, MAX(error) err FROM posts "
                      "WHERE status='failed' AND created_at >= ? GROUP BY platform", [week])
    for f in failed:
        name = {"youtube": "YouTube", "tiktok": "TikTok"}.get(f["platform"], f["platform"])
        quota = f["err"] and ("cota" in f["err"].lower() or "quota" in f["err"].lower() or "limit" in f["err"].lower())
        add("warning" if quota else "error",
            f"{f['n']} publicação(ões) falharam no {name}",
            (f["err"] or "")[:200], "queue")

    # fontes que falharam
    srcfail = db.one("SELECT COUNT(*) n FROM sources WHERE status='failed'")
    if srcfail and srcfail["n"]:
        add("warning", f"{srcfail['n']} vídeo(s) não puderam ser processados",
            "Veja o motivo em Vídeos & lives e tente de novo.", "sources")

    # métricas do TikTok indisponíveis (informativo)
    tnote = db.one("SELECT note FROM metrics WHERE available=0 AND note LIKE '%Display API%' LIMIT 1")
    if tnote:
        add("info", "Métricas do TikTok indisponíveis",
            "O TikTok só libera views pela Display API após auditoria do app. As demais funções seguem normais.",
            "accounts")

    if not out:
        add("ok", "Tudo funcionando", "Nenhum problema detectado.")
    order = {"error": 0, "warning": 1, "info": 2, "ok": 3}
    out.sort(key=lambda a: order.get(a["level"], 9))
    return out
