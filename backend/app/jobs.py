"""Fila de processamento.

Toda fonte passa primeiro por uma checagem leve (é live ou vídeo gravado?) em thread própria, para que uma
live nunca fique esperando atrás de um vídeo na fila. Vídeos gravados rodam um por vez (são pesados);
cada live ganha sua própria thread.
"""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from . import config, db
from .pipeline import download as dl
from .pipeline import live as live_mod
from .pipeline.process import run_source

log = logging.getLogger("clipforge.jobs")

_vod_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vod")
_stop_flags: dict[int, threading.Event] = {}
_lock = threading.Lock()
_run_kwargs: dict = {}  # injeção de dependências nos testes (transcriber, downloader, info_fn...)


def configure(**kwargs) -> None:
    _run_kwargs.clear()
    _run_kwargs.update(kwargs)


def _flag(source_id: int) -> threading.Event:
    with _lock:
        return _stop_flags.setdefault(source_id, threading.Event())


def _execute(source_id: int, info: dict) -> None:
    kw = {k: v for k, v in _run_kwargs.items() if k != "info_fn"}
    kw["stop"] = _flag(source_id).is_set
    try:
        run_source(source_id, info=info, **kw)
    finally:
        with _lock:
            _stop_flags.pop(source_id, None)


def _dispatch(source_id: int) -> None:
    src = db.get_source(source_id)
    if not src:
        return
    info_fn = _run_kwargs.get("info_fn") or dl.probe_url
    try:
        info = info_fn(src["url"], config.get_settings())
    except Exception as exc:  # noqa: BLE001
        log.warning("Falha ao consultar %s: %s", src["url"], exc)
        db.update("sources", source_id, status="failed", error=str(exc)[-800:])
        return
    is_live = info["live_status"] in ("is_live", "is_upcoming")
    db.update("sources", source_id, title=info["title"], channel=info["channel"], thumbnail=info["thumbnail"],
              video_id=info["id"], duration=info["duration"], kind="live" if is_live else "vod")
    if is_live:
        _execute(source_id, info)  # nesta própria thread: dura o tempo da live
    else:
        _vod_pool.submit(_execute, source_id, info)


def submit(source_id: int) -> None:
    threading.Thread(target=_dispatch, args=(source_id,), daemon=True, name=f"dispatch-{source_id}").start()


def stop(source_id: int) -> None:
    with _lock:
        flag = _stop_flags.get(source_id)
    if flag:
        flag.set()
    live_mod.request_stop(source_id)


def recover_on_startup() -> None:
    """Fontes interrompidas por queda do servidor: VOD volta para a fila; live é marcada como encerrada."""
    active = "('queued','downloading','transcribing','analyzing','rendering','recording')"
    for src in db.query(f"SELECT * FROM sources WHERE status IN {active}"):
        if src["kind"] == "live":
            db.update("sources", src["id"], status="stopped", stage_detail="O servidor reiniciou durante a live")
        else:
            db.update("sources", src["id"], status="queued", progress=0)
            submit(src["id"])
