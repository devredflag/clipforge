#!/bin/bash
# ============================================================
#  Gera o app ClipForge (macOS). DUPLO CLIQUE neste arquivo.
#  Precisa de Python 3.10+ (python.org ou "brew install python").
# ============================================================
set -e
cd "$(dirname "$0")/.."

echo "[1/5] Criando ambiente Python..."
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate

echo "[2/5] Instalando dependencias..."
python -m pip install --upgrade pip >/dev/null
pip install -r requirements.txt pyinstaller pywebview imageio-ffmpeg

echo "[3/5] Baixando ffmpeg..."
python packaging/fetch_ffmpeg.py || true

echo "[4/5] Empacotando (pode demorar alguns minutos)..."
pyinstaller --noconfirm --clean packaging/clipforge.spec

echo "[5/5] Pronto!"
echo
echo "O aplicativo esta em:  dist/ClipForge/ClipForge"
echo "Para um app .app arrastavel para Aplicativos, rode:  ./packaging/make_mac_app.sh"
echo
read -p "Pressione Enter para fechar."
