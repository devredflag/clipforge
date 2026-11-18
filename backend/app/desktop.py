"""Lançador do ClipForge como aplicativo de desktop.

Sobe o servidor local numa porta livre, numa thread, e abre a interface numa JANELA NATIVA do app
(via pywebview, quando disponível). Se não houver suporte a janela nativa no sistema, abre no navegador
padrão — em ambos os casos o usuário vê o mesmo painel, sem precisar de terminal.

É este o ponto de entrada do executável empacotado (PyInstaller) e do `python -m app.desktop`.
"""
from __future__ import annotations

import logging
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("clipforge.desktop")

APP_NAME = "ClipForge"


def _free_port(preferred: int = 8765) -> int:
    for port in (preferred, 0):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
        except OSError:
            continue
    return preferred


def _wait_health(base: str, token: str, timeout: float = 40.0) -> bool:
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/api/health", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.3)
    return False


def _run_server(host: str, port: int) -> None:
    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port, log_level="warning")


def _panel_url(base: str, token: str) -> str:
    # passa o token na URL só na primeira carga; o painel o guarda no navegador/janela e some com ele
    return f"{base}/?token={token}"


def _show_blocking_message(title: str, message: str) -> None:
    """Mostra um aviso sem depender de terminal (usado quando o ffmpeg falta, por exemplo)."""
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
        return
    except Exception:  # noqa: BLE001
        pass
    log.error("%s\n%s", title, message)


def main() -> int:
    # garante que o pacote 'app' seja importável quando empacotado
    here = Path(__file__).resolve()
    sys.path.insert(0, str(here.parents[1]))

    from app import config, media

    config.load_env_file()
    config.ensure_dirs()
    token = config.api_token()

    # checagem amigável de ffmpeg antes de abrir a janela
    status = media.tools_status()
    if not (status["ffmpeg"] and status["ffprobe"]):
        _show_blocking_message(
            f"{APP_NAME} — ffmpeg não encontrado",
            "O ClipForge precisa do ffmpeg (e ffprobe) para cortar vídeos.\n\n"
            "• Se você baixou a versão empacotada, ela deveria trazer o ffmpeg na pasta 'bin'.\n"
            "• Caso contrário, instale em https://ffmpeg.org/download.html e abra o ClipForge de novo.\n\n"
            "O app vai abrir mesmo assim, mas a geração de cortes não vai funcionar sem o ffmpeg.",
        )

    host, port = "127.0.0.1", _free_port()
    base = f"http://{host}:{port}"

    server = threading.Thread(target=_run_server, args=(host, port), daemon=True)
    server.start()

    if not _wait_health(base, token):
        _show_blocking_message(
            f"{APP_NAME} — falha ao iniciar",
            "O servidor interno não respondeu a tempo. Tente abrir o ClipForge novamente.\n"
            "Se persistir, rode pelo terminal para ver o erro: python -m app.desktop",
        )
        return 1

    url = _panel_url(base, token)
    log.info("%s pronto em %s", APP_NAME, base)

    # 1) janela nativa (experiência de 'app de verdade')
    try:
        import webview  # pywebview

        window = webview.create_window(APP_NAME, url, width=1180, height=820, min_size=(900, 640),
                                       text_select=True)
        webview.start()  # bloqueia até a janela fechar
        return 0
    except Exception as exc:  # noqa: BLE001 — sem backend de janela nativa (ex.: faltou WebKit)
        log.info("Janela nativa indisponível (%s); abrindo no navegador padrão.", exc)

    # 2) navegador padrão como alternativa
    webbrowser.open(url)
    print(f"\n{APP_NAME} rodando em {base}\nDeixe esta janela aberta. Feche-a para encerrar o app.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
