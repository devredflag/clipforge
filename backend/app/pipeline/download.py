"""Download e inspeção de URLs do YouTube com yt-dlp."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import yt_dlp


class DownloadError(RuntimeError):
    pass


def _base_opts(settings) -> dict:
    opts: dict = {"quiet": True, "no_warnings": True, "noplaylist": True}
    if settings.cookies_from_browser:
        opts["cookiesfrombrowser"] = (settings.cookies_from_browser,)
    return opts


def _friendly(exc: Exception) -> DownloadError:
    msg = str(exc)
    low = msg.lower()
    if "sign in to confirm" in low or "not a bot" in low:
        msg += ("\n\nO YouTube pediu login. Em Configurações, preencha 'cookies_from_browser' "
                "(ex.: chrome) com o navegador onde você está logado.")
    elif "private video" in low or "members-only" in low:
        msg += "\n\nO vídeo é privado ou exclusivo para membros."
    return DownloadError(msg)


def probe_url(url: str, settings) -> dict:
    """Metadados sem baixar. Retorna dict normalizado, incluindo `live_status`."""
    try:
        with yt_dlp.YoutubeDL({**_base_opts(settings), "skip_download": True}) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise _friendly(exc) from exc
    return {
        "id": info.get("id"),
        "title": info.get("title") or "Sem título",
        "channel": info.get("channel") or info.get("uploader") or "",
        "thumbnail": info.get("thumbnail") or "",
        "duration": info.get("duration"),
        "live_status": info.get("live_status") or ("is_live" if info.get("is_live") else "not_live"),
    }


def download_video(url: str, dest_dir: str | Path, settings,
                   progress: Callable[[float], None] | None = None) -> Path:
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    h = int(settings.max_height)

    def hook(d: dict) -> None:
        if progress and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if total:
                progress(min(1.0, d.get("downloaded_bytes", 0) / total))

    opts = {
        **_base_opts(settings),
        "format": f"bv*[height<={h}]+ba/b[height<={h}]/best",
        "merge_output_format": "mp4",
        "outtmpl": str(dest_dir / "video.%(ext)s"),
        "progress_hooks": [hook],
        "overwrites": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as exc:
        raise _friendly(exc) from exc
    files = sorted(dest_dir.glob("video.*"))
    files = [f for f in files if f.suffix not in (".part", ".ytdl")]
    if not files:
        raise DownloadError("Download terminou, mas o arquivo não foi encontrado.")
    return files[0]


def live_stream_url(url: str, settings) -> tuple[str, str | None]:
    """URLs diretas (HLS) da live em andamento para o ffmpeg gravar: (vídeo, áudio separado ou None)."""
    h = int(settings.max_height)
    # o YouTube costuma servir lives com vídeo e áudio separados (sem formato combinado)
    opts = {**_base_opts(settings), "skip_download": True,
            "format": f"b[height<={h}]/bv*[height<={h}]+ba/bv*+ba/b", "live_from_start": False}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        raise _friendly(exc) from exc
    pair = info.get("requested_formats") or []
    if len(pair) == 2 and all(f.get("url") for f in pair):
        video, audio = (pair if pair[0].get("vcodec") != "none" else pair[::-1])
        return video["url"], audio["url"]
    stream = info.get("url")
    if not stream:
        fmts = [f for f in info.get("formats", []) if f.get("url") and f.get("vcodec") != "none"]
        if not fmts:
            raise DownloadError("Não consegui obter a URL da transmissão ao vivo.")
        stream = fmts[-1]["url"]
    return stream, None
