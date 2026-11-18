from datetime import datetime, timedelta, timezone

from app import config, db, scheduler
from app.publishers.base import PublishError

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)  # 09:00 em São Paulo (UTC-3, sem horário de verão)


def make_clips(n, source_url="https://youtu.be/aaa", status="approved"):
    sid = db.create_source(source_url)
    ids = []
    for i in range(1, n + 1):
        cid = db.create_clip(sid, i, i * 10, i * 10 + 30, 0.7, f"Corte {i}")
        db.update("clips", cid, status=status, file=f"/tmp/fake_{sid}_{i}.mp4")
        ids.append(cid)
    return sid, ids


def connect(*platforms):
    for p in platforms:
        db.save_account(p, p.title(), {"token": "x"})


class FakePublisher:
    def __init__(self, fail=None):
        self.fail, self.published = fail, []

    def publish(self, clip, source, account, settings):
        if self.fail:
            raise self.fail
        self.published.append(clip["id"])
        return f"ext{clip['id']}", f"https://example.com/{clip['id']}"


def test_slots_follow_timezone_and_are_future_only():
    s = config.get_settings()
    slots = list(zip(range(4), scheduler.iter_slots(s, NOW)))
    got = [sl.isoformat(timespec="minutes") for _, sl in slots]
    assert got == ["2026-11-18T16:00+00:00", "2026-11-18T22:00+00:00", "2026-11-19T12:00+00:00", "2026-11-19T16:00+00:00"]


def test_plan_orders_parts_sequentially_across_days():
    _, ids = make_clips(5)
    connect("youtube")
    assert scheduler.plan_all(NOW) == 5
    posts = db.query("SELECT p.*, c.idx FROM posts p JOIN clips c ON c.id=p.clip_id ORDER BY p.scheduled_at")
    assert [p["idx"] for p in posts] == [1, 2, 3, 4, 5]
    assert [p["scheduled_at"][:16] for p in posts][:4] == [
        "2026-11-18T16:00", "2026-11-18T22:00", "2026-11-19T12:00", "2026-11-19T16:00"]
    assert len({p["scheduled_at"] for p in posts}) == 5


def test_plan_is_idempotent_and_per_platform():
    make_clips(2)
    connect("youtube", "tiktok")
    assert scheduler.plan_all(NOW) == 4
    assert scheduler.plan_all(NOW) == 0
    assert {p["platform"] for p in db.query("SELECT platform FROM posts")} == {"youtube", "tiktok"}


def test_unconnected_platform_is_skipped_then_planned_after_connecting():
    make_clips(1)
    connect("youtube")
    assert scheduler.plan_all(NOW) == 1
    connect("tiktok")
    assert scheduler.plan_all(NOW) == 1


def test_new_clips_continue_after_existing_queue():
    make_clips(2, "https://youtu.be/a")
    connect("youtube")
    scheduler.plan_all(NOW)
    make_clips(1, "https://youtu.be/b")
    scheduler.plan_all(NOW)
    rows = db.query("SELECT scheduled_at FROM posts ORDER BY scheduled_at")
    assert len(rows) == 3 and rows[2]["scheduled_at"][:16] == "2026-11-19T12:00"


def test_only_approved_clips_are_planned():
    make_clips(2, status="ready")
    connect("youtube")
    assert scheduler.plan_all(NOW) == 0


def test_tick_publishes_due_posts_one_per_platform_per_pass():
    make_clips(2)
    connect("youtube")
    scheduler.plan_all(NOW)
    pub = FakePublisher()
    past = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(timespec="seconds")
    db.execute("UPDATE posts SET scheduled_at = ?", [past])  # ambos vencidos (servidor ficou desligado)
    assert scheduler.tick(None, lambda p: pub) == 1  # um por plataforma por passada
    assert scheduler.tick(None, lambda p: pub) == 0  # intervalo mínimo desde a última publicação
    row = db.one("SELECT * FROM posts WHERE status='published'")
    assert row["external_url"].startswith("https://example.com/")
    assert db.one("SELECT COUNT(*) n FROM posts WHERE status='scheduled'")["n"] == 1
    # passado o intervalo mínimo, o segundo sai
    later = datetime.now(timezone.utc) + timedelta(minutes=scheduler.MIN_GAP_MINUTES + 1)
    assert scheduler.tick(later, lambda p: pub) == 1
    assert pub.published == sorted(pub.published) and len(pub.published) == 2  # na ordem das partes


def test_tick_does_not_publish_future_posts():
    make_clips(1)
    connect("youtube")
    scheduler.plan_all(NOW)
    pub = FakePublisher()
    assert scheduler.tick(NOW, lambda p: pub) == 0 and not pub.published


def test_claim_prevents_double_publish():
    _, ids = make_clips(1)
    connect("youtube")
    scheduler.plan_all(NOW)
    pid = db.one("SELECT id FROM posts")["id"]
    assert db.claim_post(pid) is True
    assert db.claim_post(pid) is False


def test_retryable_failure_is_rescheduled_then_fails_after_max_attempts():
    make_clips(1)
    connect("youtube")
    scheduler.plan_all(NOW)
    pid = db.one("SELECT id FROM posts")["id"]
    pub = FakePublisher(PublishError("rede caiu", retryable=True))
    for expected_attempts in (1, 2):
        scheduler.publish_post(pid, lambda p: pub)
        row = db.one("SELECT * FROM posts WHERE id=?", [pid])
        assert row["status"] == "scheduled" and row["attempts"] == expected_attempts
    scheduler.publish_post(pid, lambda p: pub)
    row = db.one("SELECT * FROM posts WHERE id=?", [pid])
    assert row["status"] == "failed" and "rede caiu" in row["error"]


def test_non_retryable_failure_fails_immediately():
    make_clips(1)
    connect("youtube")
    scheduler.plan_all(NOW)
    pid = db.one("SELECT id FROM posts")["id"]
    scheduler.publish_post(pid, lambda p: FakePublisher(PublishError("token inválido", retryable=False)))
    assert db.one("SELECT status FROM posts WHERE id=?", [pid])["status"] == "failed"


def test_quota_pushes_to_next_day_without_counting_attempt():
    make_clips(1)
    connect("youtube")
    scheduler.plan_all(NOW)
    pid = db.one("SELECT id FROM posts")["id"]
    scheduler.publish_post(pid, lambda p: FakePublisher(PublishError("cota", retryable=True, quota=True)))
    row = db.one("SELECT * FROM posts WHERE id=?", [pid])
    assert row["status"] == "scheduled" and row["attempts"] == 0
    assert datetime.fromisoformat(row["scheduled_at"]) > datetime.now(timezone.utc)


def test_rejected_clip_cancels_its_posts():
    _, ids = make_clips(1)
    connect("youtube")
    scheduler.plan_all(NOW)
    scheduler.cancel_posts_for_clip(ids[0])
    assert db.one("SELECT status FROM posts")["status"] == "cancelled"
