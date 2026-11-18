"""Fila de publicação: distribui os cortes aprovados nos horários diários e publica quando chega a hora.

Regras:
  * Para cada plataforma conectada e habilitada, cada corte aprovado ganha o próximo horário livre
    (`post_times`, no fuso `timezone`), em ordem: fonte mais antiga primeiro, Parte 1, Parte 2...
  * Falhas temporárias tentam de novo (até 3x); estouro de cota empurra para o próximo dia.
  * Cortes atrasados (servidor desligado) saem aos poucos, com intervalo mínimo entre postagens.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from . import config, db
from .publishers import get as get_publisher
from .publishers.base import PublishError

log = logging.getLogger("clipforge.scheduler")

MIN_GAP_MINUTES = 5
MAX_ATTEMPTS = 3
_plan_lock = threading.Lock()


def _parse_hhmm(t: str) -> tuple[int, int]:
    h, m = t.split(":")
    return int(h), int(m)


def iter_slots(settings, after: datetime):
    """Gera horários (UTC) futuros, em ordem crescente, segundo as configurações."""
    tz = ZoneInfo(settings.timezone)
    day = after.astimezone(tz).date()
    times = [_parse_hhmm(t) for t in settings.post_times]
    for offset in range(0, 800):
        d = day + timedelta(days=offset)
        for h, m in times:
            local = datetime(d.year, d.month, d.day, h, m, tzinfo=tz)
            utc = local.astimezone(timezone.utc)
            if utc > after:
                yield utc


def next_free_slot(settings, taken: set[str], after: datetime) -> datetime:
    for slot in iter_slots(settings, after):
        if slot.isoformat(timespec="seconds") not in taken:
            return slot
    raise RuntimeError("Sem horários livres")


def connected_platforms(settings) -> list[str]:
    return [p for p in settings.platforms if db.get_account(p)]


def plan_all(now: datetime | None = None) -> int:
    """Cria posts para cortes aprovados que ainda não têm um por plataforma. Devolve quantos criou."""
    now = now or datetime.now(timezone.utc)
    settings = config.get_settings()
    created = 0
    with _plan_lock:
        for platform in connected_platforms(settings):
            clips = db.query(
                "SELECT c.* FROM clips c JOIN sources s ON s.id = c.source_id "
                "WHERE c.status = 'approved' AND c.file IS NOT NULL "
                "AND NOT EXISTS (SELECT 1 FROM posts p WHERE p.clip_id = c.id AND p.platform = ? "
                "                AND p.status != 'cancelled') "
                "ORDER BY s.created_at, c.source_id, c.idx", [platform])
            if not clips:
                continue
            taken = {r["scheduled_at"] for r in db.query(
                "SELECT scheduled_at FROM posts WHERE platform = ? AND status IN ('scheduled','publishing')",
                [platform])}
            # nunca agenda antes do último post já marcado: mantém a ordem Parte 1, 2, 3...
            last = db.one("SELECT MAX(scheduled_at) AS m FROM posts WHERE platform = ? "
                          "AND status IN ('scheduled','publishing')", [platform])
            floor = now + timedelta(minutes=2)
            if last and last["m"]:
                floor = max(floor, datetime.fromisoformat(last["m"]))
            for clip in clips:
                slot = next_free_slot(settings, taken, floor)
                iso = slot.isoformat(timespec="seconds")
                db.insert("posts", clip_id=clip["id"], platform=platform, scheduled_at=iso, status="scheduled",
                          created_at=db.now_iso())
                taken.add(iso)
                floor = slot
                created += 1
    if created:
        log.info("Agendados %d posts", created)
    return created


def cancel_posts_for_clip(clip_id: int) -> None:
    db.execute("UPDATE posts SET status = 'cancelled' WHERE clip_id = ? AND status = 'scheduled'", [clip_id])


def publish_post(post_id: int, publisher_for: Callable = get_publisher) -> None:
    """Publica um post agora (chamado pelo laço ou por 'publicar agora')."""
    if not db.claim_post(post_id):
        return
    post = db.one("SELECT * FROM posts WHERE id = ?", [post_id])
    clip = db.one("SELECT * FROM clips WHERE id = ?", [post["clip_id"]])
    settings = config.get_settings()
    try:
        if not clip or clip["status"] not in ("approved", "ready") or not clip.get("file"):
            raise PublishError("O corte não está disponível para publicação.", retryable=False)
        account = db.get_account(post["platform"])
        if not account:
            raise PublishError(f"Conta {post['platform']} não está conectada.", retryable=False)
        source = db.get_source(clip["source_id"])
        pub = publisher_for(post["platform"])
        ext_id, url = pub.publish(clip, source, account, settings)
        db.update("posts", post_id, status="published", external_id=ext_id, external_url=url,
                  published_at=db.now_iso(), error=None, attempts=post["attempts"] + 1)
        log.info("Publicado clip %s em %s: %s", clip["id"], post["platform"], url)
    except PublishError as exc:
        _handle_failure(post, exc, settings)
    except Exception as exc:  # noqa: BLE001
        log.exception("Erro inesperado ao publicar post %s", post_id)
        _handle_failure(post, PublishError(f"Erro inesperado: {exc}", retryable=True), settings)


def _handle_failure(post: dict, exc: PublishError, settings) -> None:
    attempts = post["attempts"] + (0 if exc.quota else 1)
    now = datetime.now(timezone.utc)
    if exc.quota:
        # empurra para o primeiro horário do dia seguinte (fuso do usuário)
        tz = ZoneInfo(settings.timezone)
        tomorrow = datetime.now(tz).date() + timedelta(days=1)
        h, m = _parse_hhmm(settings.post_times[0])
        when = datetime(tomorrow.year, tomorrow.month, tomorrow.day, h, m, tzinfo=tz).astimezone(timezone.utc)
        db.update("posts", post["id"], status="scheduled", scheduled_at=when.isoformat(timespec="seconds"),
                  error=str(exc))
    elif exc.retryable and attempts < MAX_ATTEMPTS:
        when = now + timedelta(minutes=10 * attempts)
        db.update("posts", post["id"], status="scheduled", scheduled_at=when.isoformat(timespec="seconds"),
                  attempts=attempts, error=str(exc))
    else:
        db.update("posts", post["id"], status="failed", attempts=attempts, error=str(exc))
    log.warning("Post %s: %s", post["id"], exc)


def tick(now: datetime | None = None, publisher_for: Callable = get_publisher) -> int:
    """Uma passada do laço: publica o que venceu respeitando o intervalo mínimo por plataforma."""
    now = now or datetime.now(timezone.utc)
    due = db.query("SELECT * FROM posts WHERE status = 'scheduled' AND scheduled_at <= ? "
                   "ORDER BY scheduled_at, id", [now.isoformat(timespec="seconds")])
    done = 0
    seen: set[str] = set()
    for post in due:
        platform = post["platform"]
        if platform in seen:
            continue  # um por plataforma por passada
        recent = db.one("SELECT published_at FROM posts WHERE platform = ? AND status = 'published' "
                        "ORDER BY published_at DESC LIMIT 1", [platform])
        if recent and recent["published_at"]:
            gap = now - datetime.fromisoformat(recent["published_at"])
            if gap < timedelta(minutes=MIN_GAP_MINUTES):
                continue
        seen.add(platform)
        publish_post(post["id"], publisher_for)
        done += 1
    return done


class PublisherLoop(threading.Thread):
    def __init__(self, interval: float = 15.0):
        super().__init__(daemon=True, name="publisher-loop")
        self.interval = interval
        self._stop_event = threading.Event()

    def run(self) -> None:
        # posts que ficaram "publishing" por queda do servidor: não sabemos se foram, então não repetimos sozinhos
        db.execute("UPDATE posts SET status = 'failed', error = 'Interrompido durante a publicação — "
                   "confira na plataforma antes de tentar de novo' WHERE status = 'publishing'")
        while not self._stop_event.is_set():
            try:
                plan_all()
                tick()
            except Exception:  # noqa: BLE001
                log.exception("Erro no laço de publicação")
            try:
                from . import metrics
                metrics.refresh_due()  # autolimitado: só consulta a plataforma quando o dado está velho
            except Exception:  # noqa: BLE001
                log.exception("Erro ao atualizar métricas")
            self._stop_event.wait(self.interval)

    def stop(self) -> None:
        self._stop_event.set()
