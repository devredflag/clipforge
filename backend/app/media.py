"""Utilitários de ffmpeg/ffprobe.

Resolve os binários nesta ordem, para o app funcionar embutido (executável) ou com ffmpeg do sistema:
  1. variáveis CLIPFORGE_FFMPEG / CLIPFORGE_FFPROBE;
  2. pasta `bin/` ao lado do executável (os scripts de build colocam ffmpeg+ffprobe ali);
  3. imageio-ffmpeg (traz um ffmpeg estático via pip) — só para o ffmpeg;
  4. PATH do sistema.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import wave
from functools import lru_cache
from pathlib import Path

import numpy as np


class MediaError(RuntimeError):
    pass


def _app_dir() -> Path:
    """Pasta do executável (PyInstaller) ou da própria aplicação (modo fonte)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]  # pasta clipforge/


def _bundled_candidates(tool: str) -> list[Path]:
    exe = f"{tool}.exe" if os.name == "nt" else tool
    roots = [_app_dir(), _app_dir() / "bin", _app_dir() / "ffmpeg"]
    if getattr(sys, "_MEIPASS", None):  # recursos extraídos do executável onefile
        meipass = Path(sys._MEIPASS)
        roots += [meipass, meipass / "bin", meipass / "ffmpeg"]
    return [r / exe for r in roots]


@lru_cache(maxsize=4)
def _resolve(tool: str) -> str | None:
    env = os.environ.get(f"CLIPFORGE_{tool.upper()}")
    if env and Path(env).exists():
        return env
    for cand in _bundled_candidates(tool):
        if cand.exists():
            return str(cand)
    if tool == "ffmpeg":
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
            if exe and Path(exe).exists():
                return exe
        except Exception:  # noqa: BLE001
            pass
    return shutil.which(tool)


def ffmpeg_bin() -> str:
    return _resolve("ffmpeg") or "ffmpeg"


def ffprobe_bin() -> str:
    return _resolve("ffprobe") or "ffprobe"


def tools_status() -> dict:
    return {"ffmpeg": _resolve("ffmpeg"), "ffprobe": _resolve("ffprobe")}


def ensure_tools() -> None:
    missing = [t for t in ("ffmpeg", "ffprobe") if _resolve(t) is None]
    if missing:
        raise MediaError(
            f"Ferramentas ausentes: {', '.join(missing)}. Instale o ffmpeg "
            "(https://ffmpeg.org/download.html) e reinicie o ClipForge, ou use a versão empacotada "
            "(que já traz o ffmpeg)."
        )


def run(cmd: list[str], cwd: str | Path | None = None, timeout: float | None = None) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired as exc:
        raise MediaError(f"Tempo esgotado: {' '.join(cmd[:3])}...") from exc
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-8:])
        raise MediaError(f"{cmd[0]} falhou (código {proc.returncode}):\n{tail}")
    return proc


def probe(path: str | Path) -> dict:
    ensure_tools()
    out = run([ffprobe_bin(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    data = json.loads(out.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    duration = float(data.get("format", {}).get("duration") or (video or {}).get("duration") or 0)
    return {
        "duration": duration,
        "width": int(video["width"]) if video else 0,
        "height": int(video["height"]) if video else 0,
        "has_audio": audio is not None,
    }


def extract_audio(src: str | Path, dst: str | Path, start: float | None = None, duration: float | None = None) -> Path:
    """Extrai áudio mono 16 kHz (formato que o Whisper usa) e também serve para medir energia."""
    cmd = [ffmpeg_bin(), "-y", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(src)]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(dst)]
    run(cmd)
    return Path(dst)


def wav_rms(path: str | Path, hop: float = 0.5) -> np.ndarray:
    """Energia RMS a cada `hop` segundos de um WAV 16-bit mono."""
    with wave.open(str(path), "rb") as w:
        rate = w.getframerate()
        frames = w.readframes(w.getnframes())
        channels = w.getnchannels()
    samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    step = max(1, int(rate * hop))
    n = len(samples) // step
    if n == 0:
        return np.zeros(0, dtype=np.float32)
    blocks = samples[: n * step].reshape(n, step)
    return np.sqrt((blocks ** 2).mean(axis=1)).astype(np.float32)
