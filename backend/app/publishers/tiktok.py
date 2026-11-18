"""TikTok via Content Posting API.

Dois modos (Configurações → tiktok_mode):
  * direct: publica direto no perfil (escopo video.publish). Enquanto o app do TikTok não for auditado,
    só é permitido privacy_level=SELF_ONLY (o vídeo fica visível apenas para você).
  * inbox:  envia como rascunho para o app do TikTok (escopo video.upload); você toca em "Publicar" no celular.

O redirect_uri do login precisa ser HTTPS e cadastrado no portal do TikTok (use um túnel como cloudflared/ngrok
e coloque a URL em PUBLIC_BASE_URL / TIKTOK_REDIRECT_URI).
"""
from __future__ import annotations

import os
import threading
import time
from urllib.parse import urlencode

import requests

from .. import config, db
from .base import PublishError, compose_caption

AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
API = "https://open.tiktokapis.com"
MB = 1024 * 1024
_states: dict[str, float] = {}
_states_lock = threading.Lock()


def redirect_uri() -> str:
    return config.env("TIKTOK_REDIRECT_URI") or f"{config.public_base_url()}/auth/tiktok/callback"


def is_configured() -> bool:
    return bool(config.env("TIKTOK_CLIENT_KEY") and config.env("TIKTOK_CLIENT_SECRET"))


def _scope(settings) -> str:
    return "user.info.basic,video.publish" if settings.tiktok_mode == "direct" else "user.info.basic,video.upload"


def start_auth(state: str) -> str:
    if not is_configured():
        raise PublishError("Defina TIKTOK_CLIENT_KEY e TIKTOK_CLIENT_SECRET no arquivo .env", retryable=False)
    with _states_lock:
        _states[state] = time.time()
    params = {"client_key": config.env("TIKTOK_CLIENT_KEY"), "scope": _scope(config.get_settings()),
              "response_type": "code", "redirect_uri": redirect_uri(), "state": state}
    return f"{AUTH_URL}?{urlencode(params)}"


def _token_request(form: dict) -> dict:
    r = requests.post(f"{API}/v2/oauth/token/", data={
        "client_key": config.env("TIKTOK_CLIENT_KEY"), "client_secret": config.env("TIKTOK_CLIENT_SECRET"), **form,
    }, headers={"Content-Type": "application/x-www-form-urlencoded"}, timeout=30)
    data = r.json()
    if r.status_code != 200 or "access_token" not in data:
        raise PublishError(f"TikTok recusou o login: {data.get('error_description') or data}", retryable=False)
    now = time.time()
    data["expires_at"] = now + int(data.get("expires_in", 86400))
    data["refresh_expires_at"] = now + int(data.get("refresh_expires_in", 31536000))
    return data


def finish_auth(state: str, code: str) -> str:
    with _states_lock:
        if _states.pop(state, None) is None:
            raise PublishError("Sessão de login expirada. Clique em 'Conectar' de novo.", retryable=False)
    data = _token_request({"code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri()})
    name = "Conta do TikTok"
    try:
        r = requests.get(f"{API}/v2/user/info/", params={"fields": "open_id,display_name"},
                         headers={"Authorization": f"Bearer {data['access_token']}"}, timeout=30)
        name = r.json().get("data", {}).get("user", {}).get("display_name") or name
    except (requests.RequestException, ValueError):
        pass
    db.save_account("tiktok", name, data)
    return name


def _access_token(account: dict) -> str:
    data = account["data"]
    if time.time() > data.get("expires_at", 0) - 300:
        if time.time() > data.get("refresh_expires_at", 0):
            raise PublishError("O login do TikTok expirou — reconecte a conta.", retryable=False)
        fresh = _token_request({"grant_type": "refresh_token", "refresh_token": data["refresh_token"]})
        data = {**data, **fresh}
        db.update_account_data("tiktok", data)
    return data["access_token"]


def _check(resp: requests.Response, what: str) -> dict:
    try:
        body = resp.json()
    except ValueError:
        raise PublishError(f"TikTok ({what}): resposta inválida (HTTP {resp.status_code})", retryable=resp.status_code >= 500)
    err = body.get("error") or {}
    code = err.get("code", "ok")
    if resp.status_code >= 400 or code != "ok":
        msg = err.get("message") or str(body)
        if code in ("spam_risk_too_many_posts", "spam_risk_user_banned_from_posting", "rate_limit_exceeded"):
            raise PublishError(f"TikTok limitou as postagens ({code}): {msg}", retryable=True, quota=True)
        if code in ("access_token_invalid", "scope_not_authorized", "scope_permission_missed"):
            raise PublishError(f"Permissão do TikTok ({code}): reconecte a conta. {msg}", retryable=False)
        if code == "unaudited_client_can_only_post_to_private_accounts":
            raise PublishError("App do TikTok sem auditoria: só publica com privacidade SELF_ONLY. "
                               "Ajuste 'tiktok_privacy' ou peça a auditoria no portal.", retryable=False)
        raise PublishError(f"TikTok ({what}) {code}: {msg}", retryable=resp.status_code >= 500)
    return body.get("data", {})


def chunk_plan(size: int) -> tuple[int, int]:
    """(chunk_size, total_chunk_count) respeitando as regras do TikTok: chunks de 5–64 MB, o último pode ser
    maior (até 128 MB), total_chunk_count = floor(size / chunk_size)."""
    if size <= 64 * MB:
        return size, 1
    chunk = 32 * MB
    return chunk, size // chunk


def publish(clip: dict, source: dict | None, account: dict, settings) -> tuple[str, str]:
    path = clip["file"]
    size = os.path.getsize(path)
    token = _access_token(account)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8"}
    chunk_size, total = chunk_plan(size)
    source_info = {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": chunk_size, "total_chunk_count": total}

    if settings.tiktok_mode == "direct":
        info = _check(requests.post(f"{API}/v2/post/publish/creator_info/query/", headers=headers, timeout=30),
                      "creator_info")
        options = info.get("privacy_level_options") or []
        privacy = settings.tiktok_privacy
        if options and privacy not in options:
            raise PublishError(f"Privacidade '{privacy}' não permitida para esta conta. Opções: {options}",
                               retryable=False)
        max_dur = info.get("max_video_post_duration_sec")
        if max_dur and clip["end"] - clip["start"] > max_dur:
            raise PublishError(f"Vídeo mais longo que o limite do TikTok para esta conta ({max_dur}s).", retryable=False)
        body = {"post_info": {"title": compose_caption(clip, settings), "privacy_level": privacy,
                              "disable_duet": False, "disable_comment": False, "disable_stitch": False,
                              "video_cover_timestamp_ms": 1000},
                "source_info": source_info}
        init_url = f"{API}/v2/post/publish/video/init/"
    else:
        body = {"source_info": source_info}
        init_url = f"{API}/v2/post/publish/inbox/video/init/"

    data = _check(requests.post(init_url, headers=headers, json=body, timeout=30), "init")
    publish_id, upload_url = data["publish_id"], data["upload_url"]

    with open(path, "rb") as f:
        offset = 0
        for i in range(total):
            this = size - offset if i == total - 1 else chunk_size
            blob = f.read(this)
            r = requests.put(upload_url, data=blob, timeout=300, headers={
                "Content-Type": "video/mp4", "Content-Length": str(len(blob)),
                "Content-Range": f"bytes {offset}-{offset + len(blob) - 1}/{size}",
            })
            if r.status_code not in (200, 201, 206):
                raise PublishError(f"Falha no upload para o TikTok (HTTP {r.status_code}): {r.text[:200]}",
                                   retryable=r.status_code >= 500)
            offset += len(blob)

    return _wait_status(publish_id, headers, settings, account)


def fetch_stats(account: dict, video_id: str) -> dict:
    """Métricas do TikTok via Display API (/v2/video/query/). Exige o escopo 'video.list', que normalmente
    só é liberado após auditoria do app. Sem esse escopo, retorna available=False com aviso claro — sem fingir.
    """
    if not str(video_id).isdigit():
        return {"available": False, "note": "Sem ID público do vídeo (post ainda não concluído ou enviado como rascunho)."}
    try:
        token = _access_token(account)
    except PublishError as exc:
        return {"available": False, "note": str(exc)}
    try:
        r = requests.post(
            f"{API}/v2/video/query/?fields=id,view_count,like_count,comment_count,share_count",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"filters": {"video_ids": [str(video_id)]}}, timeout=30)
        body = r.json()
    except (requests.RequestException, ValueError) as exc:
        return {"available": False, "note": f"TikTok: {exc}"}
    err = (body.get("error") or {}).get("code", "ok")
    if err in ("scope_not_authorized", "scope_permission_missed", "access_token_invalid"):
        return {"available": False, "note": "Métricas do TikTok precisam da Display API (escopo video.list), "
                                            "liberada após auditoria do app."}
    if err != "ok":
        return {"available": False, "note": f"TikTok: {(body.get('error') or {}).get('message', err)}"}
    videos = (body.get("data") or {}).get("videos") or []
    if not videos:
        return {"available": False, "note": "Vídeo não encontrado na conta."}
    v = videos[0]
    return {"available": True, "views": v.get("view_count"), "likes": v.get("like_count"),
            "comments": v.get("comment_count"), "shares": v.get("share_count")}


def _wait_status(publish_id: str, headers: dict, settings, account: dict) -> tuple[str, str]:
    deadline = time.time() + 240
    status = ""
    while time.time() < deadline:
        data = _check(requests.post(f"{API}/v2/post/publish/status/fetch/", headers=headers,
                                    json={"publish_id": publish_id}, timeout=30), "status")
        status = data.get("status", "")
        if status == "PUBLISH_COMPLETE":
            ids = data.get("publicaly_available_post_id") or data.get("publicly_available_post_id") or []
            post_id = str(ids[0]) if ids else publish_id
            return post_id, (f"https://www.tiktok.com/@/video/{post_id}" if ids else "https://www.tiktok.com/")
        if status == "SEND_TO_USER_INBOX":
            return publish_id, "https://www.tiktok.com/"  # rascunho no app — o usuário finaliza
        if status == "FAILED":
            raise PublishError(f"O TikTok recusou o vídeo: {data.get('fail_reason', 'motivo não informado')}",
                               retryable=False)
        time.sleep(5)
    raise PublishError(f"O TikTok não terminou de processar a tempo (último status: {status}).", retryable=True)
