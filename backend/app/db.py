"""Camada fina sobre SQLite (stdlib). Uma conexão por chamada; WAL permite leitura concorrente."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    video_id TEXT,
    title TEXT,
    channel TEXT,
    thumbnail TEXT,
    kind TEXT NOT NULL DEFAULT 'vod',          -- vod | live
    status TEXT NOT NULL DEFAULT 'queued',     -- queued|downloading|transcribing|analyzing|rendering|recording|done|failed|stopped
    stage_detail TEXT,
    progress REAL NOT NULL DEFAULT 0,
    duration REAL,
    start_at REAL,                              -- segundos; NULL = ao vivo (live) / início (vídeo)
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,                      -- número da parte (1, 2, 3...)
    start REAL NOT NULL,
    end REAL NOT NULL,
    score REAL NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    file TEXT,
    thumb TEXT,
    status TEXT NOT NULL DEFAULT 'rendering',  -- rendering|ready|approved|rejected|failed
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id INTEGER NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,                -- ISO UTC
    status TEXT NOT NULL DEFAULT 'scheduled',  -- scheduled|publishing|published|failed|cancelled
    external_id TEXT,
    external_url TEXT,
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    published_at TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS accounts (
    platform TEXT PRIMARY KEY,
    display_name TEXT,
    data_json TEXT NOT NULL,
    connected_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS metrics (
    post_id INTEGER PRIMARY KEY REFERENCES posts(id) ON DELETE CASCADE,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    shares INTEGER,
    available INTEGER NOT NULL DEFAULT 1,   -- 0 = a plataforma não fornece métricas nesta conta
    note TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clips_source ON clips(source_id, idx);
CREATE INDEX IF NOT EXISTS idx_posts_due ON posts(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_posts_published ON posts(status, published_at);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _db_path():
    config.ensure_dirs()
    return config.DATA_DIR / "clipforge.db"


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(_db_path(), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as c:
        c.executescript(SCHEMA)
        if "start_at" not in {r[1] for r in c.execute("PRAGMA table_info(sources)")}:  # bancos antigos
            c.execute("ALTER TABLE sources ADD COLUMN start_at REAL")


def query(sql: str, args: tuple | list = ()) -> list[dict[str, Any]]:
    with connect() as c:
        return [dict(r) for r in c.execute(sql, args).fetchall()]


def one(sql: str, args: tuple | list = ()) -> dict[str, Any] | None:
    rows = query(sql, args)
    return rows[0] if rows else None


def execute(sql: str, args: tuple | list = ()) -> int:
    with connect() as c:
        cur = c.execute(sql, args)
        return cur.lastrowid or 0


def insert(table: str, **values: Any) -> int:
    cols = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    return execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(values.values()))


_ALLOWED = {
    "sources": {"url", "video_id", "title", "channel", "thumbnail", "kind", "status", "stage_detail",
                "progress", "duration", "error", "updated_at"},
    "clips": {"idx", "start", "end", "score", "title", "description", "reason", "file", "thumb", "status", "error"},
    "posts": {"scheduled_at", "status", "external_id", "external_url", "error", "attempts", "published_at"},
}


def update(table: str, row_id: int, **values: Any) -> None:
    if not values:
        return
    bad = set(values) - _ALLOWED[table]
    if bad:
        raise ValueError(f"Colunas não permitidas em {table}: {bad}")
    if table == "sources":
        values["updated_at"] = now_iso()
    sets = ", ".join(f"{k} = ?" for k in values)
    execute(f"UPDATE {table} SET {sets} WHERE id = ?", [*values.values(), row_id])


# ---- atalhos de domínio -------------------------------------------------------------------

def create_source(url: str, kind: str = "vod", start_at: float | None = None) -> int:
    ts = now_iso()
    return insert("sources", url=url, kind=kind, start_at=start_at, status="queued", created_at=ts, updated_at=ts)


def get_source(source_id: int) -> dict[str, Any] | None:
    return one("SELECT * FROM sources WHERE id = ?", [source_id])


def set_progress(source_id: int, status: str, progress: float | None = None, detail: str | None = None) -> None:
    vals: dict[str, Any] = {"status": status}
    if progress is not None:
        vals["progress"] = round(max(0.0, min(1.0, progress)), 4)
    if detail is not None:
        vals["stage_detail"] = detail
    update("sources", source_id, **vals)


def next_clip_idx(source_id: int) -> int:
    row = one("SELECT COALESCE(MAX(idx), 0) + 1 AS n FROM clips WHERE source_id = ?", [source_id])
    return int(row["n"]) if row else 1


def create_clip(source_id: int, idx: int, start: float, end: float, score: float, title: str,
                reason: str = "", description: str = "") -> int:
    return insert("clips", source_id=source_id, idx=idx, start=start, end=end, score=score, title=title,
                  reason=reason, description=description, status="rendering", created_at=now_iso())


def get_account(platform: str) -> dict[str, Any] | None:
    row = one("SELECT * FROM accounts WHERE platform = ?", [platform])
    if row:
        row["data"] = json.loads(row.pop("data_json"))
    return row


def save_account(platform: str, display_name: str, data: dict[str, Any]) -> None:
    execute(
        "INSERT INTO accounts (platform, display_name, data_json, connected_at) VALUES (?,?,?,?) "
        "ON CONFLICT(platform) DO UPDATE SET display_name=excluded.display_name, "
        "data_json=excluded.data_json, connected_at=excluded.connected_at",
        [platform, display_name, json.dumps(data), now_iso()],
    )


def update_account_data(platform: str, data: dict[str, Any]) -> None:
    execute("UPDATE accounts SET data_json = ? WHERE platform = ?", [json.dumps(data), platform])


def delete_account(platform: str) -> None:
    execute("DELETE FROM accounts WHERE platform = ?", [platform])


def upsert_metrics(post_id: int, *, views=None, likes=None, comments=None, shares=None,
                   available: bool = True, note: str | None = None) -> None:
    execute(
        "INSERT INTO metrics (post_id, views, likes, comments, shares, available, note, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(post_id) DO UPDATE SET "
        "views=excluded.views, likes=excluded.likes, comments=excluded.comments, shares=excluded.shares, "
        "available=excluded.available, note=excluded.note, updated_at=excluded.updated_at",
        [post_id, views, likes, comments, shares, 1 if available else 0, note, now_iso()],
    )


def claim_post(post_id: int) -> bool:
    """Marca o post como 'publishing' só se ainda estiver 'scheduled' (evita publicar duas vezes)."""
    with connect() as c:
        cur = c.execute("UPDATE posts SET status = 'publishing' WHERE id = ? AND status = 'scheduled'", [post_id])
        return cur.rowcount == 1


def wait_until(fn, timeout: float = 5.0, step: float = 0.05):
    """Utilitário de teste: espera `fn()` ficar verdadeiro."""
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(step)
    return fn()
