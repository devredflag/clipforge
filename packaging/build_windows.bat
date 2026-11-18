@echo off
REM ============================================================
REM  Gera ClipForge.exe (Windows). Rode com DUPLO CLIQUE ou no cmd,
REM  a partir da pasta do projeto. Precisa de Python 3.10+ instalado.
REM ============================================================
setlocal
cd /d "%~dp0\.."

echo [1/5] Criando ambiente Python...
if not exist .venv ( python -m venv .venv )
call .venv\Scripts\activate.bat

echo [2/5] Instalando dependencias...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt pyinstaller pywebview imageio-ffmpeg || goto :erro

echo [3/5] Baixando ffmpeg...
python packaging\fetch_ffmpeg.py

echo [4/5] Empacotando (pode demorar alguns minutos)...
pyinstaller --noconfirm --clean packaging\clipforge.spec || goto :erro

echo [5/5] Pronto!
echo.
echo O aplicativo esta em:  dist\ClipForge\ClipForge.exe
echo Crie um atalho dele na area de trabalho e pronto.
echo.
pause
exit /b 0

:erro
echo.
echo Falhou. Veja as mensagens acima.
pause
exit /b 1
