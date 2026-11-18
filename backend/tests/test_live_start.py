"""Começar a gravar a live num ponto anterior ao ao-vivo (desde o início / a partir de hh:mm:ss)."""
import time

from app.pipeline import live as live_mod

URL = "https://example/live.m3u8"


def _window(monkeypatch, seg=5.0, window=3600.0):
    monkeypatch.setattr(live_mod.dl, "hls_window", lambda url: (seg, window))


def test_ao_vivo_nao_volta(monkeypatch):
    _window(monkeypatch)
    assert live_mod._back_segments(None, {"started_at": time.time() - 600}, URL) == 0


def test_a_partir_de_ponto_dentro_da_janela(monkeypatch):
    _window(monkeypatch)
    info = {"started_at": time.time() - 1800}  # live no ar há 30 min
    assert live_mod._back_segments(600, info, URL) in (240, 241)  # começar aos 10 min → voltar 20 min = 240 segs


def test_desde_o_inicio_limitado_a_janela(monkeypatch):
    _window(monkeypatch)
    info = {"started_at": time.time() - 7 * 3600}  # live de 7 h, YouTube guarda 1 h
    assert live_mod._back_segments(0, info, URL) == 720


def test_sem_horario_de_inicio_usa_janela_toda(monkeypatch):
    _window(monkeypatch)
    assert live_mod._back_segments(0, {}, URL) == 720


def test_arquivo_local_ignora(monkeypatch):
    _window(monkeypatch)
    assert live_mod._back_segments(0, {}, "C:/video.mp4") == 0


def test_falha_ao_ler_janela_grava_do_ao_vivo(monkeypatch):
    def boom(url):
        raise OSError("rede")
    monkeypatch.setattr(live_mod.dl, "hls_window", boom)
    assert live_mod._back_segments(0, {}, URL) == 0
