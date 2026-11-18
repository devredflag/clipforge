"""Configuração: variáveis de ambiente (.env), token da API e configurações editáveis pelo painel."""
from __future__ import annotations

import json
import os
import secrets
import sys
import threading
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

# empacotado: pasta do .exe (no onefile, __file__ fica numa pasta temporária apagada ao fechar)
ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("CLIPFORGE_DATA", ROOT / "data"))


def load_env_file(path: Path | None = None) -> None:
    """Carrega um .env simples (CHAVE=valor) sem depender de bibliotecas externas."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file()


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def public_base_url() -> str:
    return env("PUBLIC_BASE_URL", "http://localhost:8765").rstrip("/")


def ensure_dirs() -> None:
    for sub in ("", "sources", "clips", "live", "tmp"):
        (DATA_DIR / sub).mkdir(parents=True, exist_ok=True)


def api_token() -> str:
    """Token que a extensão e o painel usam para falar com o backend (criado na primeira execução)."""
    ensure_dirs()
    path = DATA_DIR / "api_token.txt"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(24), encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return path.read_text(encoding="utf-8").strip()


@dataclass
class Settings:
    # --- publicação ---
    timezone: str = "America/Sao_Paulo"
    platforms: list[str] = field(default_factory=lambda: ["youtube", "tiktok"])
    post_times: list[str] = field(default_factory=lambda: ["09:00", "13:00", "19:00"])
    auto_approve: bool = True  # cortes prontos já entram na fila de publicação
    part_label: str = "Parte"
    hashtags: list[str] = field(default_factory=lambda: ["shorts", "cortes"])
    youtube_privacy: str = "public"  # projetos sem auditoria do Google ficam privados de qualquer jeito
    tiktok_mode: str = "direct"  # direct (video.publish) | inbox (rascunho, video.upload)
    tiktok_privacy: str = "SELF_ONLY"  # apps sem auditoria só podem SELF_ONLY

    # --- cortes ---
    clip_min_seconds: float = 25.0
    clip_max_seconds: float = 59.0
    max_clips_per_source: int = 12
    min_score: float = 0.55  # notas: trecho fraco ~0.4, forte ~0.8 (calibrado em dados sintéticos — ajuste com vídeos reais)
    layout: str = "blur"  # blur (vídeo inteiro sobre fundo desfocado) | fill (corta no centro)
    normalize_audio: bool = True

    # --- legendas ---
    caption_font: str = "Arial"
    caption_size: int = 84
    caption_uppercase: bool = True
    caption_color: str = "FFFFFF"  # RRGGBB
    caption_highlight: str = "FFE600"  # RRGGBB
    show_part_badge: bool = True

    # --- transcrição ---
    whisper_model: str = "small"
    whisper_device: str = "auto"
    whisper_compute: str = "int8"
    language: str = "auto"  # auto | pt | en | ...

    # --- IA local opcional (Ollama) ---
    ollama_enabled: bool = False
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    # --- download ---
    cookies_from_browser: str = ""  # ex.: "chrome" — ajuda quando o YouTube pede login
    max_height: int = 1080

    # --- live ---
    live_delay_seconds: int = 180  # só corta trechos que terminaram há pelo menos isso (contexto)
    live_chunk_seconds: int = 60  # a cada quanto tempo de live gravada transcreve um novo bloco
    live_min_score: float = 0.60


_lock = threading.Lock()
_cache: Settings | None = None


def _path() -> Path:
    return DATA_DIR / "settings.json"


def get_settings() -> Settings:
    global _cache
    with _lock:
        if _cache is None:
            s = Settings()
            p = _path()
            if p.exists():
                try:
                    raw = json.loads(p.read_text(encoding="utf-8"))
                    _apply(s, raw)
                except (json.JSONDecodeError, OSError):
                    pass
            _cache = s
        return Settings(**asdict(_cache))


def _apply(s: Settings, raw: dict[str, Any]) -> None:
    types = {f.name: f for f in fields(Settings)}
    for key, value in raw.items():
        if key not in types:
            continue
        current = getattr(s, key)
        try:
            if isinstance(current, bool):
                value = value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes", "sim")
            elif isinstance(current, int):
                value = int(value)
            elif isinstance(current, float):
                value = float(value)
            elif isinstance(current, list):
                if isinstance(value, str):
                    value = [v.strip() for v in value.split(",") if v.strip()]
                value = [str(v) for v in value]
            else:
                value = str(value)
        except (TypeError, ValueError):
            continue
        setattr(s, key, value)


def update_settings(raw: dict[str, Any]) -> Settings:
    global _cache
    current = get_settings()
    _apply(current, raw)
    _validate(current)
    with _lock:
        _cache = current
        ensure_dirs()
        _path().write_text(json.dumps(asdict(current), indent=2, ensure_ascii=False), encoding="utf-8")
    return get_settings()


def reset_cache() -> None:
    global _cache
    with _lock:
        _cache = None


def _validate(s: Settings) -> None:
    import re
    from zoneinfo import ZoneInfo

    ZoneInfo(s.timezone)  # levanta se inválido
    times = []
    for t in s.post_times:
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", t):
            raise ValueError(f"Horário inválido: {t!r} (use HH:MM)")
        times.append(t)
    s.post_times = sorted(set(times))
    if not s.post_times:
        raise ValueError("Defina ao menos um horário de postagem")
    s.platforms = [p for p in s.platforms if p in ("youtube", "tiktok")]
    if s.clip_min_seconds < 5 or s.clip_max_seconds < s.clip_min_seconds:
        raise ValueError("Duração dos cortes inválida")
    if s.clip_max_seconds > 180:
        raise ValueError("Duração máxima dos cortes: 180s (limite dos Shorts)")
    if s.layout not in ("blur", "fill"):
        raise ValueError("layout deve ser 'blur' ou 'fill'")
    if s.tiktok_mode not in ("direct", "inbox"):
        raise ValueError("tiktok_mode deve ser 'direct' ou 'inbox'")
    if s.tiktok_privacy not in ("SELF_ONLY", "FOLLOWER_OF_CREATOR", "MUTUAL_FOLLOW_FRIENDS", "PUBLIC_TO_EVERYONE"):
        raise ValueError("tiktok_privacy inválido")
    if s.youtube_privacy not in ("public", "unlisted", "private"):
        raise ValueError("youtube_privacy inválido")
    for hexcolor in (s.caption_color, s.caption_highlight):
        if not re.fullmatch(r"[0-9A-Fa-f]{6}", hexcolor):
            raise ValueError("Cores devem estar no formato RRGGBB")
    s.live_delay_seconds = max(0, s.live_delay_seconds)
    s.live_chunk_seconds = max(20, s.live_chunk_seconds)
