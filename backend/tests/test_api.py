from app import config, db, jobs


def test_health_is_public(client):
    r = client.get("/api/health", headers={"X-API-Key": "errado"})
    assert r.status_code == 200 and r.json()["ok"]


def test_auth_required(client):
    assert client.get("/api/sources", headers={"X-API-Key": "errado"}).status_code == 401
    assert client.get("/api/settings", headers={"X-API-Key": ""}).status_code == 401


def test_rejects_non_youtube_url(client):
    r = client.post("/api/sources", json={"url": "https://vimeo.com/123"})
    assert r.status_code == 422


def test_add_source_enqueues(client, monkeypatch):
    seen = []
    monkeypatch.setattr(jobs, "submit", lambda sid: seen.append(sid))
    r = client.post("/api/sources", json={"url": "https://youtu.be/abc123"})
    assert r.status_code == 200
    assert seen == [r.json()["id"]]


def test_duplicate_source_not_requeued(client, monkeypatch):
    monkeypatch.setattr(jobs, "submit", lambda sid: None)
    a = client.post("/api/sources", json={"url": "https://www.youtube.com/watch?v=abc123"}).json()
    b = client.post("/api/sources", json={"url": "https://www.youtube.com/watch?v=abc123"}).json()
    assert a["id"] == b["id"] and b["duplicate"]


def test_settings_roundtrip_and_validation(client):
    r = client.put("/api/settings", json={"post_times": ["08:00", "20:00"], "min_score": 0.5})
    assert r.status_code == 200 and r.json()["post_times"] == ["08:00", "20:00"]
    assert client.put("/api/settings", json={"post_times": ["25:00"]}).status_code == 422
    assert client.put("/api/settings", json={"timezone": "Marte/Olympus"}).status_code == 422


def test_clip_lifecycle(client):
    sid = db.create_source("https://youtu.be/x")
    cid = db.create_clip(sid, 1, 0, 30, 0.7, "Título original")
    db.update("clips", cid, status="ready", file=__file__)  # arquivo real só para passar no "existe?"

    assert client.patch(f"/api/clips/{cid}", json={"title": "Novo título"}).json()["title"] == "Novo título"
    assert client.patch(f"/api/clips/{cid}", json={"title": "  "}).status_code == 422

    db.save_account("youtube", "Canal", {"token": "x"})
    config.update_settings({"platforms": ["youtube"]})
    assert client.post(f"/api/clips/{cid}/approve").json()["status"] == "approved"
    assert db.query("SELECT * FROM posts WHERE clip_id=?", [cid]), "aprovar deveria agendar"

    assert client.post(f"/api/clips/{cid}/reject").json()["status"] == "rejected"
    assert db.one("SELECT status FROM posts WHERE clip_id=?", [cid])["status"] == "cancelled"


def test_accounts_listing(client):
    accs = {a["platform"]: a for a in client.get("/api/accounts").json()}
    assert set(accs) == {"youtube", "tiktok"}
    assert accs["youtube"]["connected"] is False


def test_source_delete_removes_clips(client, monkeypatch):
    monkeypatch.setattr(jobs, "submit", lambda sid: None)
    sid = db.create_source("https://youtu.be/x")
    db.create_clip(sid, 1, 0, 30, 0.7, "c")
    assert client.delete(f"/api/sources/{sid}").status_code == 200
    assert db.get_source(sid) is None
    assert db.query("SELECT * FROM clips WHERE source_id=?", [sid]) == []


def test_retry_only_failed(client):
    sid = db.create_source("https://youtu.be/x")
    db.update("sources", sid, status="done")
    assert client.post(f"/api/sources/{sid}/retry").status_code == 409
