"""Baixa binários estáticos de ffmpeg + ffprobe para packaging/bin/ no SO atual.

Usado pelos scripts de build. Requer internet (a máquina do usuário tem; o sandbox de testes não).
Fontes: gyan.dev (Windows), evermeet.cx (macOS), johnvansickle.com (Linux).
"""
from __future__ import annotations

import io
import os
import platform
import shutil
import stat
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

BIN = Path(__file__).resolve().parent / "bin"


def _download(url: str, attempts: int = 3) -> bytes:
    for n in range(1, attempts + 1):
        print(f"  baixando {url} (tentativa {n})")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "ClipForge-build"})
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read()
        except Exception as exc:  # noqa: BLE001 — sites de build às vezes dão 503 passageiro
            if n == attempts:
                raise
            print(f"  falhou ({exc}); tentando de novo em {10 * n}s")
            time.sleep(10 * n)
    raise RuntimeError("inalcançável")


def _make_exec(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


WINDOWS_SOURCES = (
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
    # alternativa se o gyan.dev estiver fora do ar
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
)


def fetch_windows() -> None:
    for i, url in enumerate(WINDOWS_SOURCES):
        try:
            data = _download(url)
            break
        except Exception as exc:  # noqa: BLE001
            if i == len(WINDOWS_SOURCES) - 1:
                raise
            print(f"  fonte indisponível ({exc}); usando a próxima")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            base = os.path.basename(name)
            if base in ("ffmpeg.exe", "ffprobe.exe"):
                (BIN / base).write_bytes(z.read(name))
                print(f"  ✓ {base}")


def fetch_macos() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        data = _download(f"https://evermeet.cx/ffmpeg/get/{tool}/zip")
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            member = next(n for n in z.namelist() if os.path.basename(n) == tool)
            out = BIN / tool
            out.write_bytes(z.read(member))
            _make_exec(out)
            print(f"  ✓ {tool}")


def fetch_linux() -> None:
    arch = "amd64" if platform.machine() in ("x86_64", "amd64") else "arm64"
    data = _download(f"https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-{arch}-static.tar.xz")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as t:
        for m in t.getmembers():
            base = os.path.basename(m.name)
            if base in ("ffmpeg", "ffprobe") and m.isfile():
                src = t.extractfile(m)
                out = BIN / base
                out.write_bytes(src.read())
                _make_exec(out)
                print(f"  ✓ {base}")


def main() -> int:
    BIN.mkdir(parents=True, exist_ok=True)
    if (BIN / "ffmpeg").exists() or (BIN / "ffmpeg.exe").exists():
        print("ffmpeg já está em packaging/bin — pulando download.")
        return 0
    system = platform.system().lower()
    print(f"Baixando ffmpeg para {system}…")
    try:
        if system == "windows":
            fetch_windows()
        elif system == "darwin":
            fetch_macos()
        else:
            fetch_linux()
    except Exception as exc:  # noqa: BLE001
        print(f"\n[aviso] não consegui baixar o ffmpeg automaticamente: {exc}\n"
              "Baixe manualmente ffmpeg e ffprobe e coloque em packaging/bin/, ou garanta o ffmpeg no PATH.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
