from datetime import datetime, timedelta, timezone

from app import config, db, metrics

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)


def _published(platform, clip_id, days_ago, ext="x"):
    when = (NOW - timedelta(days=days_ago)).isoformat(timespec="seconds")
    return db.insert("posts", clip_id=clip_id, platform=platform, scheduled_at=when, status="published",
                     external_id=ext, external_url=f"https://e/{ext}", published_at=when, created_at=when)


def _clip():
    sid = db.create_source("https://youtu.be/x")
    return db.create_clip(sid, 1, 0, 30, 0.7, "t")


class FakeStatsPublisher:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = 0

    def fetch_stats(self, account, video_id):
        self.calls += 1
        return self.mapping.get(video_id, {"available": False, "note": "n/d"})


def test_refresh_populates_metrics_and_throttles():
    db.save_account("youtube", "C", {"t": 1})
    c = _clip()
    _published("youtube", c, 2, ext="v1")
    pub = FakeStatsPublisher({"v1": {"available": True, "views": 100, "likes": 5, "comments": 2}})
    assert metrics.refresh_due(lambda p: pub, now=NOW) == 1
    row = db.one("SELECT * FROM metrics")
    assert row["views"] == 100 and row["available"] == 1
    # dentro da janela de 6h não reconsulta
    assert metrics.refresh_due(lambda p: pub, now=NOW + timedelta(hours=1)) == 0
    assert pub.calls == 1
    # force ignora o intervalo
    metrics.refresh_due(lambda p: pub, now=NOW + timedelta(hours=1), force=True)
    assert pub.calls == 2


def test_unavailable_platform_marked_not_faked():
    db.save_account("tiktok", "C", {"t": 1})
    c = _clip()
    _published("tiktok", c, 1, ext="v1")
    pub = FakeStatsPublisher({"v1": {"available": False, "note": "Display API"}})
    metrics.refresh_due(lambda p: pub, now=NOW)
    row = db.one("SELECT * FROM metrics")
    assert row["available"] == 0 and row["views"] is None and "Display API" in row["note"]


def test_summary_computes_average_and_performance():
    db.save_account("youtube", "C", {"t": 1})
    # três vídeos com views bem diferentes → mediana define acima/abaixo
    views = {"a": 1000, "b": 100, "c": 500}
    for ext, v in views.items():
        pid = _published("youtube", _clip(), 3, ext=ext)
        db.upsert_metrics(pid, views=v, available=True)
    s = metrics.summary(now=NOW)
    assert s["measured_count"] == 3
    assert s["avg_views"] == round((1000 + 100 + 500) / 3)
    assert s["best"]["views"] == 1000 and s["worst"]["views"] == 100
    perf = {v["views"]: v["performance"] for v in s["videos"]}
    assert perf[1000] == "acima" and perf[100] == "abaixo"  # mediana=500


def test_summary_ignores_old_and_unavailable():
    db.save_account("youtube", "C", {"t": 1})
    old = _published("youtube", _clip(), 60, ext="old")
    db.upsert_metrics(old, views=9999, available=True)
    na = _published("youtube", _clip(), 1, ext="na")
    db.upsert_metrics(na, available=False, note="x")
    s = metrics.summary(now=NOW, window_days=30)
    assert s["published_count"] == 1      # o antigo ficou fora da janela
    assert s["measured_count"] == 0       # o único no período não tem métrica
    assert s["avg_views"] is None


def test_alerts_flag_disconnected_platform_and_failed_posts():
    config.update_settings({"platforms": ["youtube", "tiktok"]})
    db.save_account("youtube", "C", {"t": 1})   # tiktok fica desconectado
    c = _clip()
    when = (NOW - timedelta(days=1)).isoformat(timespec="seconds")
    db.insert("posts", clip_id=c, platform="youtube", scheduled_at=when, status="failed",
              error="cota diária atingida", created_at=when)
    titles = " | ".join(a["title"] for a in metrics.alerts(now=NOW))
    assert "TikTok não está conectado" in titles
    assert "falharam" in titles


def test_alerts_all_good_when_nothing_wrong():
    config.update_settings({"platforms": []})  # nada ativo, nada falho, ffmpeg presente no ambiente de teste
    out = metrics.alerts(now=NOW)
    assert any(a["level"] == "ok" for a in out)
