"""API HTTP do ClipForge (painel e extensão falam com ela)."""
from __future__ import annotations

import logging
import os
import re
import secrets
import sys
import shutil
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, db, jobs, media, metrics, scheduler
from . import publishers
from .publishers.base import PublishError
from .pipeline.download import UPLOAD_PREFIX

log = logging.getLogger("clipforge")


def _static_dir() -> Path:
    """Pasta do painel web, tanto em modo fonte quanto empacotado (PyInstaller onefile/onedir)."""
    here = Path(__file__).parent / "static"
    if here.exists():
        return here
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass and (Path(meipass) / "app" / "static").exists():
        return Path(meipass) / "app" / "static"
    return here


STATIC = _static_dir()
YOUTUBE_RE = re.compile(r"^https?://((www|m|music)\.)?(youtube\.com|youtu\.be)/", re.IGNORECASE)

_loop: scheduler.PublisherLoop | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _loop
    config.ensure_dirs()
    db.init_db()
    token = config.api_token()
    try:
        media.ensure_tools()
    except media.MediaError as exc:
        log.error("%s", exc)
    if not os.environ.get("CLIPFORGE_NO_BACKGROUND"):
        jobs.recover_on_startup()
        _loop = scheduler.PublisherLoop()
        _loop.start()
    log.info("ClipForge no ar. Token da API: %s (também em %s)", token, config.DATA_DIR / "api_token.txt")
    yield
    if _loop:
        _loop.stop()


app = FastAPI(title="ClipForge", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^(chrome-extension://[a-z]+|https?://(localhost|127\.0\.0\.1)(:\d+)?)$",
    allow_methods=["*"], allow_headers=["*"],
)


def require_key(x_api_key: str | None = Header(default=None), token: str | None = Query(default=None)) -> None:
    supplied = x_api_key or token or ""
    if not secrets.compare_digest(supplied.encode(), config.api_token().encode()):
        raise HTTPException(401, "Token da API inválido")


auth = [Depends(require_key)]


# ---- modelos ------------------------------------------------------------------------------------

class NewSource(BaseModel):
    url: str
    start_at: float | None = Field(default=None, ge=0)  # segundos; None = ao vivo / início do vídeo


class ClipPatch(BaseModel):
    title: str | None = None
    description: str | None = None


# ---- serialização -------------------------------------------------------------------------------

def _clip_out(c: dict) -> dict:
    posts = db.query("SELECT id, platform, status, scheduled_at, external_url, error FROM posts "
                     "WHERE clip_id = ? AND status != 'cancelled' ORDER BY platform", [c["id"]])
    s = config.get_settings()
    return {
        "id": c["id"], "source_id": c["source_id"], "idx": c["idx"], "start": c["start"], "end": c["end"],
        "duration": round(c["end"] - c["start"], 1), "score": c["score"], "title": c["title"],
        "full_title": f"{c['title']} | {s.part_label} {c['idx']}", "description": c["description"],
        "reason": c["reason"], "status": c["status"], "error": c["error"], "created_at": c["created_at"],
        "has_video": bool(c["file"] and Path(c["file"]).exists()),
        "posts": posts,
    }


def _dir_bytes(path: Path) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def _source_out(s: dict, with_clips: bool = False) -> dict:
    out = dict(s)
    clips = db.query("SELECT * FROM clips WHERE source_id = ? ORDER BY idx", [s["id"]])
    out["clip_count"] = len(clips)
    sid = str(s["id"])
    # vídeo original/gravação (o que "Liberar espaço" apaga) e cortes renderizados
    out["original_bytes"] = _dir_bytes(config.DATA_DIR / "sources" / sid) + _dir_bytes(config.DATA_DIR / "live" / sid)
    out["clips_bytes"] = _dir_bytes(config.DATA_DIR / "clips" / sid)
    if with_clips:
        out["clips"] = [_clip_out(c) for c in clips]
    return out


def _get_clip(clip_id: int) -> dict:
    c = db.one("SELECT * FROM clips WHERE id = ?", [clip_id])
    if not c:
        raise HTTPException(404, "Corte não encontrado")
    return c


# ---- rotas --------------------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    status = media.tools_status()
    return {"ok": True, "version": app.version, "ffmpeg": bool(status["ffmpeg"] and status["ffprobe"]),
            "tools": status}


@app.get("/api/settings", dependencies=auth)
def get_settings() -> dict:
    from dataclasses import asdict
    return asdict(config.get_settings())


@app.put("/api/settings", dependencies=auth)
def put_settings(payload: dict) -> dict:
    from dataclasses import asdict
    try:
        s = config.update_settings(payload)
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    scheduler.plan_all()
    return asdict(s)


@app.post("/api/sources", dependencies=auth)
def add_source(body: NewSource) -> dict:
    url = body.url.strip()
    if not YOUTUBE_RE.match(url):
        raise HTTPException(422, "Envie um link do YouTube (youtube.com ou youtu.be)")
    active = db.one("SELECT * FROM sources WHERE url = ? AND status NOT IN ('failed','stopped','done') "
                    "ORDER BY id DESC", [url])
    if active:
        return {**_source_out(active), "duplicate": True}
    sid = db.create_source(url, start_at=body.start_at)
    jobs.submit(sid)
    return _source_out(db.get_source(sid))


UPLOAD_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
UPLOAD_MAX = 10 * 1024**3  # 10 GB


@app.post("/api/sources/upload", dependencies=auth)
async def upload_source(file: UploadFile = File(...)) -> dict:
    name = Path(file.filename or "video.mp4").name
    ext = Path(name).suffix.lower()
    if ext not in UPLOAD_EXTS:
        raise HTTPException(422, "Envie um vídeo MP4, MOV, MKV, WEBM ou AVI")
    sid = db.create_source(f"{UPLOAD_PREFIX}{name}")
    db.update("sources", sid, title=Path(name).stem, channel="Arquivo enviado")
    work = config.DATA_DIR / "sources" / str(sid)
    work.mkdir(parents=True, exist_ok=True)
    dest, size = work / f"video{ext}", 0
    try:
        with open(dest, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > UPLOAD_MAX:
                    raise HTTPException(413, "Arquivo maior que 10 GB")
                out.write(chunk)
    except BaseException:
        db.execute("DELETE FROM sources WHERE id = ?", [sid])
        shutil.rmtree(work, ignore_errors=True)
        raise
    jobs.submit(sid)
    return _source_out(db.get_source(sid))


@app.get("/api/sources", dependencies=auth)
def list_sources() -> list[dict]:
    return [_source_out(s) for s in db.query("SELECT * FROM sources ORDER BY id DESC")]


@app.get("/api/sources/{source_id}", dependencies=auth)
def get_source(source_id: int) -> dict:
    s = db.get_source(source_id)
    if not s:
        raise HTTPException(404, "Fonte não encontrada")
    return _source_out(s, with_clips=True)


@app.post("/api/sources/{source_id}/stop", dependencies=auth)
def stop_source(source_id: int) -> dict:
    if not db.get_source(source_id):
        raise HTTPException(404, "Fonte não encontrada")
    jobs.stop(source_id)
    return {"ok": True}


@app.post("/api/sources/{source_id}/retry", dependencies=auth)
def retry_source(source_id: int) -> dict:
    s = db.get_source(source_id)
    if not s:
        raise HTTPException(404, "Fonte não encontrada")
    if s["status"] not in ("failed", "stopped"):
        raise HTTPException(409, "Só dá para tentar de novo fontes que falharam ou foram interrompidas")
    db.update("sources", source_id, status="queued", error=None, progress=0)
    jobs.submit(source_id)
    return _source_out(db.get_source(source_id))


@app.post("/api/sources/{source_id}/free-space", dependencies=auth)
def free_space(source_id: int) -> dict:
    """Apaga o vídeo original / gravação da live (e o áudio extraído), mantendo os cortes e a transcrição."""
    s = db.get_source(source_id)
    if not s:
        raise HTTPException(404, "Fonte não encontrada")
    if s["status"] in ("queued", "downloading", "transcribing", "analyzing", "rendering", "recording"):
        raise HTTPException(409, "Espere terminar (ou clique em Parar) antes de liberar espaço")
    freed = 0
    work = config.DATA_DIR / "sources" / str(source_id)
    if work.exists():
        for f in work.iterdir():
            if f.name == "words.json":  # transcrição: pequena e evita transcrever de novo num "Tentar de novo"
                continue
            freed += _dir_bytes(f) if f.is_dir() else f.stat().st_size
            shutil.rmtree(f, ignore_errors=True) if f.is_dir() else f.unlink(missing_ok=True)
    live = config.DATA_DIR / "live" / str(source_id)
    freed += _dir_bytes(live)
    shutil.rmtree(live, ignore_errors=True)
    return {"ok": True, "freed_bytes": freed}


@app.delete("/api/sources/{source_id}", dependencies=auth)
def delete_source(source_id: int) -> dict:
    s = db.get_source(source_id)
    if not s:
        raise HTTPException(404, "Fonte não encontrada")
    if s["status"] in ("recording",):
        jobs.stop(source_id)
    db.execute("DELETE FROM sources WHERE id = ?", [source_id])
    for sub in ("sources", "clips", "live"):
        shutil.rmtree(config.DATA_DIR / sub / str(source_id), ignore_errors=True)
    return {"ok": True}


@app.get("/api/clips", dependencies=auth)
def list_clips(status: str | None = None, limit: int = 200) -> list[dict]:
    if status:
        rows = db.query("SELECT * FROM clips WHERE status = ? ORDER BY id DESC LIMIT ?", [status, limit])
    else:
        rows = db.query("SELECT * FROM clips ORDER BY id DESC LIMIT ?", [limit])
    return [_clip_out(c) for c in rows]


@app.patch("/api/clips/{clip_id}", dependencies=auth)
def patch_clip(clip_id: int, body: ClipPatch) -> dict:
    _get_clip(clip_id)
    vals = {k: v.strip() for k, v in body.model_dump(exclude_none=True).items()}
    if "title" in vals and not vals["title"]:
        raise HTTPException(422, "O título não pode ficar vazio")
    db.update("clips", clip_id, **vals)
    return _clip_out(_get_clip(clip_id))


@app.post("/api/clips/{clip_id}/approve", dependencies=auth)
def approve_clip(clip_id: int) -> dict:
    c = _get_clip(clip_id)
    if not c["file"] or not Path(c["file"]).exists():
        raise HTTPException(409, "O vídeo deste corte ainda não está pronto")
    db.update("clips", clip_id, status="approved")
    scheduler.plan_all()
    return _clip_out(_get_clip(clip_id))


@app.post("/api/clips/{clip_id}/reject", dependencies=auth)
def reject_clip(clip_id: int) -> dict:
    _get_clip(clip_id)
    db.update("clips", clip_id, status="rejected")
    scheduler.cancel_posts_for_clip(clip_id)
    return _clip_out(_get_clip(clip_id))


@app.delete("/api/clips/{clip_id}", dependencies=auth)
def delete_clip(clip_id: int) -> dict:
    c = _get_clip(clip_id)
    for key in ("file", "thumb"):
        if c.get(key):
            Path(c[key]).unlink(missing_ok=True)
    db.execute("DELETE FROM clips WHERE id = ?", [clip_id])
    return {"ok": True}


@app.get("/api/clips/{clip_id}/video", dependencies=auth)
def clip_video(clip_id: int) -> FileResponse:
    c = _get_clip(clip_id)
    if not c["file"] or not Path(c["file"]).exists():
        raise HTTPException(404, "Vídeo indisponível")
    return FileResponse(c["file"], media_type="video/mp4", filename=f"{c['title'][:40] or 'corte'}.mp4")


@app.get("/api/clips/{clip_id}/thumb", dependencies=auth)
def clip_thumb(clip_id: int) -> FileResponse:
    c = _get_clip(clip_id)
    if not c["thumb"] or not Path(c["thumb"]).exists():
        raise HTTPException(404, "Miniatura indisponível")
    return FileResponse(c["thumb"], media_type="image/jpeg")


@app.get("/api/posts", dependencies=auth)
def list_posts(status: str | None = None) -> list[dict]:
    sql = ("SELECT p.*, c.title AS clip_title, c.idx AS clip_idx, c.source_id AS source_id FROM posts p "
           "JOIN clips c ON c.id = p.clip_id WHERE p.status != 'cancelled' ")
    args: list = []
    if status:
        sql += "AND p.status = ? "
        args.append(status)
    sql += "ORDER BY p.scheduled_at DESC LIMIT 300"
    return db.query(sql, args)


def _get_post(post_id: int) -> dict:
    p = db.one("SELECT * FROM posts WHERE id = ?", [post_id])
    if not p:
        raise HTTPException(404, "Post não encontrado")
    return p


@app.post("/api/posts/{post_id}/cancel", dependencies=auth)
def cancel_post(post_id: int) -> dict:
    p = _get_post(post_id)
    if p["status"] != "scheduled":
        raise HTTPException(409, "Só posts agendados podem ser cancelados")
    db.update("posts", post_id, status="cancelled")
    return {"ok": True}


@app.post("/api/posts/{post_id}/retry", dependencies=auth)
def retry_post(post_id: int) -> dict:
    p = _get_post(post_id)
    if p["status"] not in ("failed", "cancelled"):
        raise HTTPException(409, "Só posts com falha ou cancelados podem ser reagendados")
    when = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(timespec="seconds")
    db.update("posts", post_id, status="scheduled", scheduled_at=when, attempts=0, error=None)
    return {"ok": True}


@app.post("/api/posts/{post_id}/publish-now", dependencies=auth)
def publish_now(post_id: int) -> dict:
    p = _get_post(post_id)
    if p["status"] not in ("scheduled", "failed"):
        raise HTTPException(409, "Este post não pode ser publicado agora")
    if p["status"] == "failed":
        db.update("posts", post_id, status="scheduled", attempts=0, error=None)
    threading.Thread(target=scheduler.publish_post, args=(post_id,), daemon=True).start()
    return {"ok": True}


@app.get("/api/metrics", dependencies=auth)
def get_metrics(window_days: int = 30) -> dict:
    return metrics.summary(window_days=max(1, min(window_days, 365)))


@app.post("/api/metrics/refresh", dependencies=auth)
def refresh_metrics() -> dict:
    n = metrics.refresh_due(force=True)
    return {"ok": True, "refreshed": n}


@app.get("/api/alerts", dependencies=auth)
def get_alerts() -> list[dict]:
    return metrics.alerts()


@app.get("/api/accounts", dependencies=auth)
def list_accounts() -> list[dict]:
    out = []
    for name, mod in publishers.REGISTRY.items():
        acc = db.get_account(name)
        out.append({"platform": name, "configured": mod.is_configured(), "connected": bool(acc),
                    "display_name": acc["display_name"] if acc else None,
                    "connected_at": acc["connected_at"] if acc else None,
                    "redirect_uri": mod.redirect_uri()})
    return out


# chaves que a tela Contas pode gravar no .env, por plataforma: (id, segredo, redirect opcional)
CREDENTIAL_KEYS = {
    "youtube": ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REDIRECT_URI"),
    "tiktok": ("TIKTOK_CLIENT_KEY", "TIKTOK_CLIENT_SECRET", "TIKTOK_REDIRECT_URI"),
}


class Credentials(BaseModel):
    client_id: str = Field(min_length=4, max_length=300)
    client_secret: str = Field(min_length=4, max_length=300)
    redirect_uri: str | None = Field(default=None, max_length=500)


@app.post("/api/accounts/{platform}/credentials", dependencies=auth)
def save_credentials(platform: str, body: Credentials) -> dict:
    if platform not in CREDENTIAL_KEYS:
        raise HTTPException(404, "Plataforma desconhecida")
    values = [body.client_id.strip(), body.client_secret.strip(), (body.redirect_uri or "").strip()]
    if any(ch in v for v in values for ch in "\r\n\"'"):  # o .env é linha a linha
        raise HTTPException(422, "Valor inválido")
    if values[2] and not values[2].startswith(("https://", "http://localhost", "http://127.0.0.1")):
        raise HTTPException(422, "O endereço de retorno precisa começar com https://")
    config.save_env(dict(zip(CREDENTIAL_KEYS[platform], values)))
    return {"ok": True, "redirect_uri": publishers.get(platform).redirect_uri()}


@app.post("/api/auth/{platform}/start", dependencies=auth)
def auth_start(platform: str, open_browser: bool = False) -> dict:
    if platform not in publishers.REGISTRY:
        raise HTTPException(404, "Plataforma desconhecida")
    try:
        url = publishers.get(platform).start_auth(secrets.token_urlsafe(16))
    except PublishError as exc:
        raise HTTPException(422, str(exc)) from exc
    if open_browser:  # a janela do app não abre abas: o login vai para o navegador padrão
        import webbrowser
        webbrowser.open(url)
    return {"url": url}


@app.delete("/api/accounts/{platform}", dependencies=auth)
def disconnect(platform: str) -> dict:
    db.delete_account(platform)
    return {"ok": True}


def _page(title: str, body: str, ok: bool) -> HTMLResponse:
    color = "#16a34a" if ok else "#dc2626"
    html = (f"<!doctype html><meta charset=utf-8><title>{title}</title>"
            f"<body style='font-family:system-ui;background:#0f1115;color:#e6e6e6;display:grid;place-items:center;"
            f"height:100vh;margin:0'><div style='max-width:520px;text-align:center'>"
            f"<h1 style='color:{color}'>{title}</h1><p>{body}</p><p><a style='color:#8ab4ff' href='/'>Voltar ao painel</a></p>"
            f"</div></body>")
    return HTMLResponse(html, status_code=200 if ok else 400)


@app.get("/auth/{platform}/callback", include_in_schema=False)
def auth_callback(platform: str, code: str | None = None, state: str | None = None, error: str | None = None):
    import html as _html
    if platform not in publishers.REGISTRY:
        raise HTTPException(404)
    if error or not code or not state:
        return _page("Não foi possível conectar", _html.escape(error or "Resposta incompleta da plataforma."), False)
    try:
        name = publishers.get(platform).finish_auth(state, code)
    except PublishError as exc:
        return _page("Não foi possível conectar", _html.escape(str(exc)), False)
    except Exception as exc:  # noqa: BLE001
        log.exception("Falha no callback de %s", platform)
        return _page("Não foi possível conectar", _html.escape(str(exc)[:300]), False)
    scheduler.plan_all()
    return _page("Conta conectada", f"{_html.escape(name)} ({platform}) pronta para receber publicações.", True)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
