import json
import os
from pathlib import Path

import pytest

from app import config, db
from app.pipeline import captions
from app.pipeline.transcribe import Word
from app.publishers import tiktok, youtube
from app.publishers.base import PublishError, compose_caption, compose_description, compose_title


# ---- legendas ---------------------------------------------------------------------------------

def test_color_conversion_is_bgr():
    assert captions._ass_color("FFE600") == "&H0000E6FF"
    assert captions._tag_color("FFE600") == "&H00E6FF&"


def test_timestamp_format():
    assert captions._ts(0) == "0:00:00.00"
    assert captions._ts(61.257) == "0:01:01.26"
    assert captions._ts(3725.5) == "1:02:05.50"


def test_ass_times_are_relative_to_clip_and_badge_present():
    words = [Word("um", 10.0, 10.3), Word("dois", 10.4, 10.7), Word("três.", 10.8, 11.2), Word("fora", 50, 50.3)]
    ass = captions.build_ass(words, 10.0, 20.0, badge_text="PARTE 3")
    assert "PARTE 3" in ass
    dialogues = [l for l in ass.splitlines() if l.startswith("Dialogue: 1,")]
    assert dialogues and dialogues[0].split(",")[1] == "0:00:00.00"
    assert "FORA" not in ass  # palavra fora do corte
    assert "UM" in ass and "TRÊS." in ass


def test_ass_escapes_override_braces():
    ass = captions.build_ass([Word("{\\b1}oi", 0, 0.5)], 0, 5)
    assert "{\\b1}" not in ass.split("[Events]")[1].replace("{\\c", "").replace("{\\t", "")


def test_groups_respect_max_words():
    words = [Word(f"p{i}", i * 0.3, i * 0.3 + 0.25) for i in range(10)]
    assert all(len(g) <= 3 for g in captions.group_words(words))


# ---- títulos e descrições ---------------------------------------------------------------------

def test_title_suffix_never_truncated():
    s = config.Settings()
    clip = {"title": "x" * 300, "idx": 12}
    t = compose_title(clip, s, limit=100)
    assert len(t) <= 100 and t.endswith("| Parte 12")


def test_caption_fits_tiktok_limit_and_has_hashtags():
    s = config.Settings()
    cap = compose_caption({"title": "Título", "idx": 2}, s)
    assert cap == "Título | Parte 2 #shorts #cortes"


def test_description_credits_source():
    d = compose_description({"title": "t", "idx": 1, "description": ""}, {"url": "https://youtu.be/abc", "channel": "Canal"},
                            config.Settings())
    assert "https://youtu.be/abc" in d and "Canal" in d and "#shorts" in d


# ---- TikTok -----------------------------------------------------------------------------------

def test_chunk_plan_follows_tiktok_rules():
    MB = 1024 * 1024
    assert tiktok.chunk_plan(10 * MB) == (10 * MB, 1)
    assert tiktok.chunk_plan(64 * MB) == (64 * MB, 1)
    for size in (65 * MB, 100 * MB + 123, 400 * MB + 7):
        chunk, total = tiktok.chunk_plan(size)
        assert 5 * MB <= chunk <= 64 * MB
        assert total == size // chunk
        last = size - chunk * (total - 1)
        assert chunk <= last <= 128 * MB
        assert 1 <= total <= 1000


class FakeResp:
    def __init__(self, status=200, body=None, text=""):
        self.status_code, self._body, self.text = status, body if body is not None else {}, text

    def json(self):
        return self._body


def _tiktok_env(monkeypatch, tmp_path, privacy_options=("SELF_ONLY",), mode="direct"):
    video = tmp_path / "v.mp4"
    video.write_bytes(os.urandom(1024 * 300))
    calls = {"post": [], "put": []}

    def fake_post(url, headers=None, json=None, timeout=None, **_):
        calls["post"].append((url, json))
        if url.endswith("creator_info/query/"):
            return FakeResp(200, {"data": {"privacy_level_options": list(privacy_options), "max_video_post_duration_sec": 600},
                                  "error": {"code": "ok"}})
        if url.endswith("video/init/") or url.endswith("inbox/video/init/"):
            return FakeResp(200, {"data": {"publish_id": "v_pub_file~1", "upload_url": "https://open-upload.tiktokapis.com/video/?x=1"},
                                  "error": {"code": "ok"}})
        if url.endswith("status/fetch/"):
            status = "SEND_TO_USER_INBOX" if mode == "inbox" else "PUBLISH_COMPLETE"
            return FakeResp(200, {"data": {"status": status, "publicaly_available_post_id": ["777"]}, "error": {"code": "ok"}})
        raise AssertionError(url)

    def fake_put(url, data=None, headers=None, timeout=None, **_):
        calls["put"].append((url, headers, len(data)))
        return FakeResp(201)

    monkeypatch.setattr(tiktok.requests, "post", fake_post)
    monkeypatch.setattr(tiktok.requests, "put", fake_put)
    clip = {"file": str(video), "title": "Meu corte", "idx": 3, "start": 0, "end": 40}
    account = {"data": {"access_token": "tok", "refresh_token": "r", "expires_at": 9e12, "refresh_expires_at": 9e12}}
    return clip, account, calls, video


def test_tiktok_direct_publish_flow(monkeypatch, tmp_path):
    clip, account, calls, video = _tiktok_env(monkeypatch, tmp_path)
    s = config.Settings(tiktok_privacy="SELF_ONLY")
    post_id, url = tiktok.publish(clip, None, account, s)
    assert post_id == "777"
    init = next(j for u, j in calls["post"] if u.endswith("/video/init/"))
    size = video.stat().st_size
    assert init["source_info"] == {"source": "FILE_UPLOAD", "video_size": size, "chunk_size": size, "total_chunk_count": 1}
    assert init["post_info"]["privacy_level"] == "SELF_ONLY"
    assert "Parte 3" in init["post_info"]["title"]
    (_, hdrs, n), = calls["put"]
    assert hdrs["Content-Range"] == f"bytes 0-{size - 1}/{size}" and n == size


def test_tiktok_rejects_privacy_not_allowed(monkeypatch, tmp_path):
    clip, account, _, _ = _tiktok_env(monkeypatch, tmp_path, privacy_options=("SELF_ONLY",))
    with pytest.raises(PublishError) as e:
        tiktok.publish(clip, None, account, config.Settings(tiktok_privacy="PUBLIC_TO_EVERYONE"))
    assert not e.value.retryable


def test_tiktok_inbox_mode_uses_inbox_endpoint(monkeypatch, tmp_path):
    clip, account, calls, _ = _tiktok_env(monkeypatch, tmp_path, mode="inbox")
    tiktok.publish(clip, None, account, config.Settings(tiktok_mode="inbox"))
    assert any(u.endswith("/inbox/video/init/") for u, _ in calls["post"])
    assert not any(u.endswith("creator_info/query/") for u, _ in calls["post"])


def test_tiktok_error_mapping():
    r = FakeResp(403, {"error": {"code": "unaudited_client_can_only_post_to_private_accounts", "message": "x"}})
    with pytest.raises(PublishError) as e:
        tiktok._check(r, "init")
    assert not e.value.retryable and "SELF_ONLY" in str(e.value)
    r = FakeResp(429, {"error": {"code": "rate_limit_exceeded", "message": "x"}})
    with pytest.raises(PublishError) as e:
        tiktok._check(r, "init")
    assert e.value.quota


# ---- YouTube ----------------------------------------------------------------------------------

class _Req:
    def __init__(self, fail=None):
        self.fail, self.n = fail, 0

    def next_chunk(self):
        if self.fail:
            raise self.fail
        self.n += 1
        return (None, None) if self.n < 2 else (None, {"id": "abc123"})


class _Videos:
    def __init__(self, fail=None):
        self.fail, self.body = fail, None

    def insert(self, part, body, media_body):
        self.body = body
        return _Req(self.fail)


class _YT:
    def __init__(self, fail=None):
        self.v = _Videos(fail)

    def videos(self):
        return self.v


def test_youtube_publish_builds_short_metadata(monkeypatch, tmp_path):
    yt = _YT()
    monkeypatch.setattr(youtube, "_credentials", lambda a: object())
    monkeypatch.setattr(youtube, "_service", lambda c: yt)
    f = tmp_path / "v.mp4"
    f.write_bytes(b"0" * 2048)
    clip = {"file": str(f), "title": "Meu corte", "idx": 5, "description": "", "start": 0, "end": 30}
    vid, url = youtube.publish(clip, {"url": "https://youtu.be/x", "channel": "C"}, {"data": {}}, config.Settings())
    assert vid == "abc123" and url.endswith("/shorts/abc123")
    assert yt.v.body["snippet"]["title"] == "Meu corte | Parte 5"
    assert "#shorts" in yt.v.body["snippet"]["description"]
    assert yt.v.body["status"]["selfDeclaredMadeForKids"] is False


def test_youtube_quota_error_is_flagged(monkeypatch, tmp_path):
    from googleapiclient.errors import HttpError

    class Resp:
        status = 403
        reason = "Forbidden"

    err = HttpError(Resp(), json.dumps({"error": {"errors": [{"reason": "quotaExceeded"}]}}).encode())
    monkeypatch.setattr(youtube, "_credentials", lambda a: object())
    monkeypatch.setattr(youtube, "_service", lambda c: _YT(err))
    f = tmp_path / "v.mp4"
    f.write_bytes(b"0" * 2048)
    with pytest.raises(PublishError) as e:
        youtube.publish({"file": str(f), "title": "t", "idx": 1, "description": "", "start": 0, "end": 9}, None,
                        {"data": {}}, config.Settings())
    assert e.value.quota
