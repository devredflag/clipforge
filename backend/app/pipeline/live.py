"""Cortes de lives em tempo (quase) real.

Como funciona:
  * O ffmpeg grava a live em segmentos de ~20 s (.ts) e anota cada segmento fechado numa lista CSV.
  * A cada `live_chunk_seconds` de gravação nova, o bloco é transcrito (com 8 s de sobreposição para não
    cortar frases no meio) e as palavras entram numa linha do tempo única.
  * O "decisor" só olha o trecho que terminou há pelo menos `live_delay_seconds` — esse atraso garante que o
    assunto já se fechou antes de a gente decidir onde cortar (contexto preservado).
  * Cada corte aprovado é renderizado na hora (9:16 + legendas) e entra na fila de publicação.
  * Ao fim da live (ou ao parar), o que sobrou é processado com atraso zero.
"""
from __future__ import annotations

import csv
import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from .. import config, db, media
from . import download as dl
from .highlights import pick_highlights
from .process import RMS_HOP, ollama_args, render_and_register
from .transcribe import Transcriber, Word, get_transcriber

log = logging.getLogger("clipforge.live")

SEGMENT_SECONDS = 20
OVERLAP_SECONDS = 8.0

_sessions: dict[int, "LiveSession"] = {}
_sessions_lock = threading.Lock()


def request_stop(source_id: int) -> bool:
    with _sessions_lock:
        s = _sessions.get(source_id)
    if s:
        s.stop()
        return True
    return False


@dataclass
class Segment:
    name: str
    start: float
    end: float


class LiveSession:
    def __init__(self, source_id: int, stream_url: str, settings, transcriber: Transcriber, *,
                 ffmpeg_input_args: list[str] | None = None, poll: float = 2.0):
        self.source_id = source_id
        self.stream_url = stream_url
        self.settings = settings
        self.transcriber = transcriber
        self.input_args = ffmpeg_input_args or []
        self.poll = poll
        self.dir = config.DATA_DIR / "live" / str(source_id)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.list_path = self.dir / "segments.csv"
        self.proc: subprocess.Popen | None = None
        self._stop = threading.Event()
        # estado da linha do tempo
        self.words: list[Word] = []
        self.rms: np.ndarray = np.zeros(0, dtype=np.float32)
        self.transcribed_until = 0.0
        self.cursor = 0.0
        self.clips_made = 0

    # ---- gravação ------------------------------------------------------------------------
    def _start_recorder(self) -> None:
        cmd = [media.ffmpeg_bin(), "-y", "-v", "error"]
        if self.stream_url.startswith("http"):
            cmd += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
        cmd += [*self.input_args, "-i", self.stream_url, "-map", "0:v:0?", "-map", "0:a:0?", "-c", "copy",
                "-f", "segment", "-segment_time", str(SEGMENT_SECONDS), "-segment_format", "mpegts",
                "-reset_timestamps", "1", "-segment_list", self.list_path.name, "-segment_list_type", "csv",
                "seg_%05d.ts"]
        self.err_log = open(self.dir / "ffmpeg.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(cmd, cwd=self.dir, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                                     stderr=self.err_log)

    def stop(self) -> None:
        """Pede para encerrar: o ffmpeg fecha o último segmento e o laço faz o processamento final."""
        self._stop.set()
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write(b"q")  # type: ignore[union-attr]
                self.proc.stdin.flush()  # type: ignore[union-attr]
            except (BrokenPipeError, OSError, ValueError):
                self.proc.terminate()

    def _read_segments(self) -> list[Segment]:
        if not self.list_path.exists():
            return []
        segs: list[Segment] = []
        with open(self.list_path, newline="", encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) >= 3:
                    try:
                        segs.append(Segment(row[0], float(row[1]), float(row[2])))
                    except ValueError:
                        continue
        return segs

    def _range_file(self, segs: list[Segment], t0: float, t1: float, tag: str) -> tuple[Path, float]:
        """Junta (sem recodificar) os segmentos que cobrem [t0, t1]. Devolve (arquivo, início absoluto)."""
        sel = [s for s in segs if s.end > t0 and s.start < t1 and (self.dir / s.name).exists()]
        if not sel:
            raise media.MediaError("Segmentos da live indisponíveis para o intervalo pedido")
        listing = self.dir / f"concat_{tag}.txt"
        listing.write_text("".join(f"file '{(self.dir / s.name).as_posix()}'\n" for s in sel), encoding="utf-8")
        out = self.dir / f"range_{tag}.ts"
        media.run([media.ffmpeg_bin(), "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy",
                   str(out)])
        return out, sel[0].start

    # ---- transcrição ---------------------------------------------------------------------
    def _transcribe_block(self, segs: list[Segment], t1: float) -> None:
        t0 = max(0.0, self.transcribed_until - OVERLAP_SECONDS)
        rng, base = self._range_file(segs, t0, t1, "asr")
        wav = self.dir / "asr.wav"
        media.extract_audio(rng, wav, start=max(0.0, t0 - base), duration=t1 - t0)
        lang = None if self.settings.language == "auto" else self.settings.language
        new_words = [Word(w.text, w.start + t0, w.end + t0) for w in self.transcriber.transcribe(str(wav), lang)]
        committed_end = self.words[-1].end if self.words else -1.0
        self.words.extend(w for w in new_words if w.start >= committed_end - 0.05)
        keep = int(round(t0 / RMS_HOP))
        self.rms = np.concatenate([self.rms[:keep], media.wav_rms(wav, RMS_HOP)])
        self.transcribed_until = t1

    # ---- decisão de cortes ---------------------------------------------------------------
    def _decide(self, segs: list[Segment], final: bool) -> None:
        s = self.settings
        delay = 0.0 if final else float(s.live_delay_seconds)
        safe_end = self.transcribed_until - delay
        if safe_end - self.cursor < s.clip_min_seconds:
            return
        chosen = pick_highlights(
            self.words, self.rms, min_s=s.clip_min_seconds, max_s=s.clip_max_seconds, limit=0,
            min_score=s.live_min_score, ollama=ollama_args(s), region=(self.cursor, safe_end), rms_hop=RMS_HOP,
        )
        for cand in chosen:
            try:
                rng, base = self._range_file(segs, cand.start - 1.0, cand.end + 1.0, f"clip{self.clips_made}")
                render_and_register(self.source_id, cand, db.next_clip_idx(self.source_id), self.words, rng, s,
                                    src_offset=base)
                self.clips_made += 1
            except Exception:  # noqa: BLE001
                log.exception("Falha ao cortar trecho da live %s", self.source_id)
        last_end = max((c.end for c in chosen), default=self.cursor)
        self.cursor = max(self.cursor, last_end, safe_end - s.clip_max_seconds)

    def _prune(self, segs: list[Segment]) -> None:
        """Apaga segmentos que não serão mais usados (a live pode ter horas)."""
        horizon = min(self.cursor, self.transcribed_until - OVERLAP_SECONDS) - 5.0
        for sg in segs:
            if sg.end < horizon:
                (self.dir / sg.name).unlink(missing_ok=True)

    def _status(self, segs: list[Segment]) -> None:
        rec = segs[-1].end if segs else 0.0
        fmt = lambda t: f"{int(t // 60)}:{int(t % 60):02d}"  # noqa: E731
        db.set_progress(self.source_id, "recording", None,
                        f"Gravado {fmt(rec)} · transcrito {fmt(self.transcribed_until)} · cortes {self.clips_made}")

    # ---- laço principal ------------------------------------------------------------------
    def run(self) -> None:
        with _sessions_lock:
            _sessions[self.source_id] = self
        try:
            self._start_recorder()
            chunk = float(self.settings.live_chunk_seconds)
            while True:
                finished = self.proc.poll() is not None  # type: ignore[union-attr]
                segs = self._read_segments()
                closed_end = segs[-1].end if segs else 0.0
                try:
                    while closed_end - self.transcribed_until >= chunk or (
                            finished and closed_end - self.transcribed_until > 1.0):
                        target = closed_end if finished else min(closed_end, self.transcribed_until + chunk)
                        self._transcribe_block(segs, target)
                        self._decide(segs, final=False)
                        self._status(segs)
                except media.MediaError:
                    log.exception("Erro ao processar bloco da live %s", self.source_id)
                if finished:
                    break
                self._prune(segs)
                self._status(segs)
                time.sleep(self.poll)
            segs = self._read_segments()
            if not segs:
                err = ""
                try:
                    err = (self.dir / "ffmpeg.log").read_text(encoding="utf-8")[-400:]
                except OSError:
                    pass
                raise RuntimeError(f"Nenhum trecho da live foi gravado. {err}".strip())
            self._decide(segs, final=True)
            db.set_progress(self.source_id, "stopped" if self._stop.is_set() else "done", 1.0,
                            f"Live encerrada · {self.clips_made} cortes")
        finally:
            if self.proc and self.proc.poll() is None:
                self.proc.kill()
            try:
                self.err_log.close()
            except Exception:  # noqa: BLE001
                pass
            with _sessions_lock:
                _sessions.pop(self.source_id, None)


def run_live(source_id: int, info: dict, *, transcriber: Transcriber | None = None,
             stream_url_fn: Callable | None = None, stop: Callable[[], bool] = lambda: False, **_: object) -> None:
    settings = config.get_settings()
    if info.get("live_status") == "is_upcoming":
        # espera a live começar (até 12 h), checando a cada 30 s
        deadline = time.time() + 12 * 3600
        while time.time() < deadline and not stop():
            db.set_progress(source_id, "queued", 0.0, "Aguardando a live começar")
            try:
                fresh = dl.probe_url(db.get_source(source_id)["url"], settings)
            except dl.DownloadError:
                fresh = info
            if fresh["live_status"] == "is_live":
                break
            time.sleep(30)
        if stop():
            db.set_progress(source_id, "stopped", detail="Cancelado antes de começar")
            return
    url = (stream_url_fn or dl.live_stream_url)(db.get_source(source_id)["url"], settings)
    session = LiveSession(source_id, url, settings, transcriber or get_transcriber(settings))
    session.run()
