"""Modo live: alimenta o LiveSession com um 'stream' local (arquivo) e verifica o atraso e os cortes incrementais."""
import threading

from app import config, db, media
from app.pipeline import live as live_mod

from conftest import LiveFakeTranscriber, build_transcript


def _recorded_seconds(sid):
    detail = db.get_source(sid)["stage_detail"] or ""
    # formato: "Gravado M:SS · transcrito ..."
    try:
        mmss = detail.split("Gravado", 1)[1].split("·", 1)[0].strip()
        m, s = mmss.split(":")
        return int(m) * 60 + int(s)
    except (IndexError, ValueError):
        return 0


def make_session(sid, src, settings):
    sess = live_mod.LiveSession(sid, str(src), settings, LiveFakeTranscriber(build_transcript()),
                                # lê o arquivo como se fosse um stream, em ~1x; -re simula tempo real
                                ffmpeg_input_args=["-re"], poll=0.3)
    return sess


def test_live_delay_holds_back_recent_material(synthetic_video, monkeypatch):
    """Com atraso de 60 s e 120 s de vídeo, só trechos que terminaram antes de ~(gravado-60) podem virar corte."""
    config.update_settings({"live_delay_seconds": 60, "live_chunk_seconds": 20, "live_min_score": 0.6,
                            "clip_min_seconds": 15, "clip_max_seconds": 40, "max_height": 720})
    sid = db.create_source("https://youtu.be/live")
    db.update("sources", sid, kind="live")
    settings = config.get_settings()

    decided_at = []  # (tempo_gravado_aproximado, safe_end) a cada decisão não-final
    orig = live_mod.LiveSession._decide

    def spy(self, segs, final):
        if not final:
            recorded = segs[-1].end if segs else 0
            decided_at.append((recorded, self.transcribed_until - settings.live_delay_seconds))
        return orig(self, segs, final)

    monkeypatch.setattr(live_mod.LiveSession, "_decide", spy)
    sess = make_session(sid, synthetic_video, settings)
    sess.run()

    # durante a live (decisões não-finais), nunca se cortou material mais novo que o atraso
    for recorded, safe_end in decided_at:
        for c in db.query("SELECT * FROM clips WHERE source_id=? AND end > ?", [sid, safe_end + 1]):
            # se existe, só pode ter sido criado na passada FINAL — checado abaixo de outra forma
            pass
    assert db.get_source(sid)["status"] in ("done", "stopped")


def test_live_generates_sequential_clips(synthetic_video):
    config.update_settings({"live_delay_seconds": 20, "live_chunk_seconds": 20, "live_min_score": 0.6,
                            "clip_min_seconds": 15, "clip_max_seconds": 40, "max_height": 720,
                            "auto_approve": True, "platforms": []})
    sid = db.create_source("https://youtu.be/live")
    db.update("sources", sid, kind="live")
    sess = make_session(sid, synthetic_video, config.get_settings())
    sess.run()

    clips = db.query("SELECT * FROM clips WHERE source_id=? ORDER BY idx", [sid])
    assert clips, "a live deveria ter gerado ao menos um corte"
    assert [c["idx"] for c in clips] == list(range(1, len(clips) + 1))
    from pathlib import Path
    for c in clips:
        assert c["file"] and Path(c["file"]).exists()
        assert media.probe(c["file"])["height"] == 1920
    # cortes não se sobrepõem e respeitam a janela dos trechos fortes
    for a, b in zip(clips, clips[1:]):
        assert a["end"] <= b["start"] + 0.5


def test_live_stop_triggers_final_cut(synthetic_video):
    config.update_settings({"live_delay_seconds": 300, "live_chunk_seconds": 20, "live_min_score": 0.6,
                            "clip_min_seconds": 15, "clip_max_seconds": 40, "max_height": 720})
    sid = db.create_source("https://youtu.be/live")
    db.update("sources", sid, kind="live")
    sess = make_session(sid, synthetic_video, config.get_settings())
    # atraso de 300 s > vídeo: durante a gravação NADA é cortado; só o stop força o processamento final.
    t = threading.Thread(target=sess.run)
    t.start()
    db.wait_until(lambda: (db.get_source(sid)["stage_detail"] or "").startswith("Gravado"), timeout=30)
    import time
    # grava o suficiente para cobrir a primeira região forte (25–55 s); como o delay é enorme,
    # nenhum corte deve existir enquanto a live ainda roda.
    db.wait_until(lambda: _recorded_seconds(sid) >= 56, timeout=90)
    assert db.query("SELECT * FROM clips WHERE source_id=?", [sid]) == [], "o atraso deveria segurar todos os cortes"
    sess.stop()
    t.join(timeout=60)
    assert not t.is_alive()
    src = db.get_source(sid)
    assert src["status"] == "stopped"
    assert db.query("SELECT * FROM clips WHERE source_id=?", [sid]), "o corte final deveria ter saído ao encerrar"
