"""YouTube Shorts via YouTube Data API v3 (OAuth 2.0).

Observações importantes (documentadas no README):
  * Projetos do Google Cloud criados depois de 28/07/2020 e sem a auditoria do YouTube publicam SEMPRE como
    privado, mesmo com privacyStatus=public. Funciona para testar; para público é preciso passar na auditoria.
  * Um vídeo vertical de até 3 minutos enviado pela API é tratado como Short.
"""
from __future__ import annotations

import os
import threading
from datetime import datetime, timezone

from .. import config, db
from .base import PublishError, compose_description, compose_title

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
_flows: dict[str, object] = {}
_flows_lock = threading.Lock()


def redirect_uri() -> str:
    return config.env("YOUTUBE_REDIRECT_URI") or f"{config.public_base_url()}/auth/youtube/callback"


def is_configured() -> bool:
    return bool(config.env("YOUTUBE_CLIENT_ID") and config.env("YOUTUBE_CLIENT_SECRET"))


def _client_config() -> dict:
    return {"web": {
        "client_id": config.env("YOUTUBE_CLIENT_ID"),
        "client_secret": config.env("YOUTUBE_CLIENT_SECRET"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [redirect_uri()],
    }}


def _flow():
    from google_auth_oauthlib.flow import Flow

    if redirect_uri().startswith(("http://localhost", "http://127.0.0.1")):
        os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")  # só para callback em localhost
    os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
    return Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=redirect_uri())


def start_auth(state: str) -> str:
    if not is_configured():
        raise PublishError("Defina YOUTUBE_CLIENT_ID e YOUTUBE_CLIENT_SECRET no arquivo .env", retryable=False)
    flow = _flow()
    url, _ = flow.authorization_url(access_type="offline", prompt="consent", state=state)
    with _flows_lock:
        _flows[state] = flow
    return url


def finish_auth(state: str, code: str) -> str:
    with _flows_lock:
        flow = _flows.pop(state, None)
    if flow is None:
        raise PublishError("Sessão de login expirada. Clique em 'Conectar' de novo.", retryable=False)
    flow.fetch_token(code=code)
    creds = flow.credentials
    data = {
        "token": creds.token, "refresh_token": creds.refresh_token, "token_uri": creds.token_uri,
        "client_id": creds.client_id, "client_secret": creds.client_secret, "scopes": list(creds.scopes or SCOPES),
    }
    name = "Canal do YouTube"
    try:
        yt = _service(creds)
        items = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
        if items:
            name = items[0]["snippet"]["title"]
    except Exception:  # noqa: BLE001 — nome é só cosmético
        pass
    db.save_account("youtube", name, data)
    return name


def _service(creds):
    from googleapiclient.discovery import build

    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _credentials(account: dict):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    data = account["data"]
    creds = Credentials.from_authorized_user_info(data, SCOPES)
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        data["token"] = creds.token
        db.update_account_data("youtube", data)
    return creds


def publish(clip: dict, source: dict | None, account: dict, settings) -> tuple[str, str]:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    try:
        creds = _credentials(account)
    except Exception as exc:  # noqa: BLE001
        raise PublishError(f"Não foi possível renovar o login do YouTube — reconecte a conta. ({exc})",
                           retryable=False) from exc
    yt = _service(creds)
    body = {
        "snippet": {
            "title": compose_title(clip, settings, limit=100),
            "description": compose_description(clip, source, settings),
            "tags": [t for t in settings.hashtags if t][:15],
            "categoryId": "22",
        },
        "status": {"privacyStatus": settings.youtube_privacy, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(clip["file"], mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    try:
        request = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            _, response = request.next_chunk()
    except HttpError as exc:
        status = getattr(exc.resp, "status", 0)
        body = exc.content.decode("utf-8", "ignore") if isinstance(exc.content, bytes) else str(exc.content or "")
        text = f"{exc} {body}"  # o motivo (quotaExceeded etc.) vem no corpo JSON da resposta
        if status == 403 and ("quotaExceeded" in text or "uploadLimitExceeded" in text):
            raise PublishError("Limite diário de envios do YouTube atingido — tentaremos amanhã.",
                               retryable=True, quota=True) from exc
        if status in (401, 403):
            raise PublishError(f"O YouTube recusou o envio (reconecte a conta?): {text[:300]}",
                               retryable=False) from exc
        raise PublishError(f"Erro do YouTube ({status}): {text[:300]}", retryable=status >= 500) from exc
    video_id = response["id"]
    return video_id, f"https://www.youtube.com/shorts/{video_id}"


def fetch_stats(account: dict, video_id: str) -> dict:
    """Estatísticas reais do vídeo (views, curtidas, comentários) via YouTube Data API.

    Retorna {'available': True, 'views': int, ...} ou {'available': False, 'note': '...'} em caso de erro.
    """
    from googleapiclient.errors import HttpError

    try:
        creds = _credentials(account)
        yt = _service(creds)
        items = yt.videos().list(part="statistics", id=video_id).execute().get("items", [])
    except HttpError as exc:  # noqa: BLE001
        return {"available": False, "note": f"YouTube: {str(exc)[:160]}"}
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "note": f"YouTube: {exc}"}
    if not items:
        return {"available": False, "note": "Vídeo não encontrado (pode ter sido removido)."}
    s = items[0].get("statistics", {})
    def _int(v):  # noqa: E306
        try:
            return int(v)
        except (TypeError, ValueError):
            return None
    return {"available": True, "views": _int(s.get("viewCount")), "likes": _int(s.get("likeCount")),
            "comments": _int(s.get("commentCount"))}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
