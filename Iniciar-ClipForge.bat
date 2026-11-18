@echo off
REM ClipForge (Windows) - DUPLO CLIQUE para abrir o app.
REM Na primeira vez, prepara tudo (precisa de internet); depois abre direto.
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python nao encontrado. Instale em https://www.python.org/downloads/
  echo IMPORTANTE: marque "Add Python to PATH" na instalacao.
  pause
  exit /b 1
)

if not exist .venv (
  echo Preparando o ClipForge pela primeira vez (pode levar alguns minutos)...
  python -m venv .venv
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip >nul
  pip install -r requirements.txt imageio-ffmpeg
  pip install pywebview
) else (
  call .venv\Scripts\activate.bat
)

cd backend
echo Abrindo o ClipForge...
python -m app.desktop
