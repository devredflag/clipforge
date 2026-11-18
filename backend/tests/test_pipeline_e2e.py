"""Ponta a ponta sem internet: usa o vídeo sintético como 'download' e um transcritor falso."""
import shutil
from pathlib import Path

from app import config, db
from app.pipeline import process
from app.pipeline.transcribe import Word

from conftest import FakeTranscriber, build_transcript


def fake_downloader_factory(src):
    def _dl(url, dest_dir, settings, progress=None):
        dest = Path(dest_dir) / "video.mp4"
        shutil.copy(src, dest)
        if progress:
            progress(1.0)
        return dest
    return _dl


def run_vod(src, settings_patch=None):
    if settings_patch:
        config.update_settings(settings_patch)
    sid = db.create_source("https://youtu.be/test")
    db.update("sources", sid, kind="vod")
    process.process_vod(sid, transcriber=FakeTranscriber(build_transcript()), downloader=fake_downloader_factory(src))
    return sid


def test_vod_produces_rendered_clips(synthetic_video):
    sid = run_vod(synthetic_video, {"max_clips_per_source": 3, "auto_approve": False, "min_score": 0.6})
    src = db.get_source(sid)
    assert src["status"] == "done"
    clips = db.query("SELECT * FROM clips WHERE source_id=? ORDER BY idx", [sid])
    assert 1 <= len(clips) <= 3
    for i, c in enumerate(clips, 1):
        assert c["idx"] == i                       # numeração sequencial = Parte 1, 2, 3...
        assert c["status"] == "ready"              # auto_approve desligado
        assert c["file"] and Path(c["file"]).exists()
        from app import media
        info = media.probe(c["file"])
        assert (info["width"], info["height"]) == (1080, 1920)   # vertical 9:16
        assert abs(info["duration"] - (c["end"] - c["start"])) < 1.5
        assert c["title"]


def test_auto_approve_schedules_posts_when_account_connected(synthetic_video):
    db.save_account("youtube", "Canal", {"token": "x"})
    sid = run_vod(synthetic_video, {"max_clips_per_source": 2, "auto_approve": True, "min_score": 0.6,
                                    "platforms": ["youtube"]})
    clips = db.query("SELECT * FROM clips WHERE source_id=?", [sid])
    assert all(c["status"] == "approved" for c in clips)
    posts = db.query("SELECT * FROM posts")
    assert len(posts) == len(clips) and {p["platform"] for p in posts} == {"youtube"}
    # cada parte agendada uma vez, em horários distintos
    assert len({p["scheduled_at"] for p in posts}) == len(posts)


def test_transcript_is_cached(synthetic_video):
    tr = FakeTranscriber(build_transcript())
    sid = db.create_source("https://youtu.be/test")
    db.update("sources", sid, kind="vod")
    dl = fake_downloader_factory(synthetic_video)
    process.process_vod(sid, transcriber=tr, downloader=dl)
    assert (config.DATA_DIR / "sources" / str(sid) / "words.json").exists()
    assert tr.calls == 1
    # reprocessar reutiliza o cache (não chama o transcritor de novo)
    for c in db.query("SELECT id FROM clips WHERE source_id=?", [sid]):
        db.execute("DELETE FROM clips WHERE id=?", [c["id"]])
    process.process_vod(sid, transcriber=tr, downloader=dl)
    assert tr.calls == 1


def test_no_highlights_marks_done_not_failed(synthetic_video):
    # min_score impossível: nada é escolhido, mas não é erro
    sid = db.create_source("https://youtu.be/test")
    db.update("sources", sid, kind="vod")
    process.process_vod(sid, transcriber=FakeTranscriber(build_transcript()),
                        downloader=fake_downloader_factory(synthetic_video))
    # (usa min_score padrão) — agora força o caso extremo
    config.update_settings({"min_score": 0.999})
    sid2 = db.create_source("https://youtu.be/test2")
    db.update("sources", sid2, kind="vod")
    process.process_vod(sid2, transcriber=FakeTranscriber(build_transcript()),
                        downloader=fake_downloader_factory(synthetic_video))
    assert db.get_source(sid2)["status"] == "done"
    assert db.query("SELECT * FROM clips WHERE source_id=?", [sid2]) == []
