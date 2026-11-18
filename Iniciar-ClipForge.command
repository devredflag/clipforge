#!/bin/bash
# ClipForge (macOS/Linux) — DUPLO CLIQUE para abrir o app.
# Na primeira vez, prepara tudo (precisa de internet); depois abre direto.
cd "$(dirname "$0")"

PY="$(command -v python3 || command -v python)"
if [ -z "$PY" ]; then
  echo "Python 3 nao encontrado. Instale em https://www.python.org/downloads/ e tente de novo."
  read -p "Enter para fechar."; exit 1
fi

if [ ! -d .venv ]; then
  echo "Preparando o ClipForge pela primeira vez (pode levar alguns minutos)..."
  "$PY" -m venv .venv
  source .venv/bin/activate
  python -m pip install --upgrade pip >/dev/null
  pip install -r requirements.txt imageio-ffmpeg
  pip install pywebview || true   # janela nativa; se falhar, abre no navegador
else
  source .venv/bin/activate
fi

cd backend
echo "Abrindo o ClipForge..."
exec python -m app.desktop
