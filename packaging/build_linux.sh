#!/bin/bash
# ============================================================
#  Gera o executável ClipForge (Linux).
#  Precisa de Python 3.10+ e, para janela nativa, do WebKitGTK
#  (ex.: sudo apt install gir1.2-webkit2-4.1 python3-gi).
# ============================================================
set -e
cd "$(dirname "$0")/.."

echo "[1/5] Criando ambiente Python..."
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate

echo "[2/5] Instalando dependencias..."
python -m pip install --upgrade pip >/dev/null
pip install -r requirements.txt pyinstaller imageio-ffmpeg
pip install pywebview || echo "(pywebview opcional nao instalado; o app abrira no navegador)"

echo "[3/5] Baixando ffmpeg..."
python packaging/fetch_ffmpeg.py || true

echo "[4/5] Empacotando (pode demorar alguns minutos)..."
pyinstaller --noconfirm --clean packaging/clipforge.spec

echo "[5/5] Pronto!  Execute:  ./dist/ClipForge/ClipForge"
