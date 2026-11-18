import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_DATA = tempfile.mkdtemp(prefix="clipforge-test-")
os.environ["CLIPFORGE_DATA"] = _DATA
os.environ["CLIPFORGE_NO_BACKGROUND"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import config, db, jobs  # noqa: E402
from app.pipeline.transcribe import Word  # noqa: E402


def make_sentences(spec):
    """spec: lista de (inicio_s, texto, ritmo_s_por_palavra). Devolve Words com tempos absolutos."""
    words, t = [], 0.0
    for start, text, step in spec:
        t = start
        for w in text.split():
            words.append(Word(w, round(t, 3), round(t + step * 0.9, 3)))
            t += step
    return words


BORING = "Então eu estava pensando sobre isso ontem mais ou menos."
HOT = ["Você sabia que ninguém conta esse segredo?", "Eu descobri isso e foi absurdo!",
       "O maior erro é nunca testar o que você acredita.", "Por que isso importa tanto para o seu dinheiro?",
       "Agora imagina ganhar 10 mil por mês com essa dica.", "Essa é a verdade que ninguém quer admitir."]


def build_transcript(total=120.0):
    """Trechos fracos (lentos, com pausas) e fortes (densos, com ganchos): 0-25 fraco, 25-55 forte,
    55-80 fraco, 80-115 forte."""
    spec = []
    t = 0.0
    while t < 25:
        spec.append((t, BORING, 0.55)); t += 7.0
    t = 25.0
    i = 0
    while t < 55:
        spec.append((t, HOT[i % len(HOT)], 0.33)); t += 3.4; i += 1
    t = 55.0
    while t < 80:
        spec.append((t, BORING, 0.55)); t += 7.0
    t = 80.0
    while t < 115:
        spec.append((t, HOT[i % len(HOT)], 0.33)); t += 3.4; i += 1
    return make_sentences(spec)


class FakeTranscriber:
    """Para VOD: devolve o roteiro inteiro, ignorando o áudio."""

    def __init__(self, words):
        self.words = words
        self.calls = 0

    def transcribe(self, wav_path, language=None, progress=None):
        self.calls += 1
        if progress:
            progress(1.0)
        return list(self.words)


class LiveFakeTranscriber:
    """Para live: reproduz a mesma contabilidade de deslocamento do LiveSession (início = fim anterior - overlap)."""

    def __init__(self, words, overlap=8.0):
        self.words, self.overlap, self.end = words, overlap, 0.0
        self.windows = []

    def transcribe(self, wav_path, language=None, progress=None):
        from app import media
        dur = media.probe(wav_path)["duration"]
        offset = max(0.0, self.end - self.overlap)
        self.end = offset + dur
        self.windows.append((offset, self.end))
        return [Word(w.text, w.start - offset, w.end - offset) for w in self.words
                if w.start >= offset and w.end <= offset + dur]


@pytest.fixture(scope="session")
def synthetic_video(tmp_path_factory):
    path = tmp_path_factory.mktemp("media") / "src.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30",
         "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100", "-t", "120", "-g", "30",
         "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)],
        check=True)
    return path


@pytest.fixture(autouse=True)
def clean_state():
    config.ensure_dirs()
    db.init_db()
    with db.connect() as c:
        for table in ("posts", "clips", "sources", "accounts"):
            c.execute(f"DELETE FROM {table}")
    (config.DATA_DIR / "settings.json").unlink(missing_ok=True)
    config.reset_cache()
    jobs.configure()
    for sub in ("sources", "clips", "live"):
        shutil.rmtree(config.DATA_DIR / sub, ignore_errors=True)
    config.ensure_dirs()
    yield


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        c.headers.update({"X-API-Key": config.api_token()})
        yield c
