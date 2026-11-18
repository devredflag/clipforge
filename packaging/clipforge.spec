# PyInstaller spec do ClipForge — gera um executável de desktop com o servidor embutido.
# Uso (na raiz do projeto, com a venv ativa):   pyinstaller packaging/clipforge.spec
# Os scripts build_*.{sh,bat,command} baixam o ffmpeg para packaging/bin antes de chamar isto.
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

ROOT = Path(os.path.abspath(os.getcwd()))
BACKEND = ROOT / "backend"
BIN = ROOT / "packaging" / "bin"   # ffmpeg/ffprobe (preenchido pelos scripts de build)

datas = [(str(BACKEND / "app" / "static"), "app/static")]
binaries = []

# ffmpeg/ffprobe embutidos, se os scripts de build os baixaram
if BIN.exists():
    for f in BIN.iterdir():
        if f.is_file():
            binaries.append((str(f), "bin"))

# dependências que o PyInstaller não descobre sozinho
hiddenimports = []
for pkg in ("faster_whisper", "ctranslate2", "onnxruntime", "av",
            "google_auth_oauthlib", "googleapiclient", "uvicorn", "anyio"):
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass
for pkg in ("faster_whisper", "ctranslate2", "onnxruntime", "av", "tokenizers"):
    try:
        datas += collect_data_files(pkg)
        binaries += collect_dynamic_libs(pkg)
    except Exception:
        pass

# uvicorn carrega estes por string
hiddenimports += [
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on", "uvicorn.lifespan.off",
    "app.main", "app.desktop", "multipart", "python_multipart",
]

block_cipher = None
ONEFILE = os.environ.get("CLIPFORGE_ONEFILE") == "1"   # CI usa 1 → sai um único ClipForge.exe

a = Analysis(
    [str(BACKEND / "app" / "desktop.py")],
    pathex=[str(BACKEND)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter.test", "test", "pytest", "matplotlib"],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

_icon = str(ROOT / "packaging" / "icon.ico") if (ROOT / "packaging" / "icon.ico").exists() else None

if ONEFILE:
    # UM único arquivo clicável (ClipForge.exe). Na abertura ele se extrai sozinho para uma pasta temporária.
    exe = EXE(
        pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
        name="ClipForge",
        debug=False, strip=False, upx=False, runtime_tmpdir=None,
        console=False, icon=_icon,
    )
else:
    # Pasta ClipForge/ com o ClipForge dentro (abre mais rápido; bom para distribuir compactado).
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name="ClipForge",
        debug=False, strip=False, upx=False,
        console=False, icon=_icon,
    )
    coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, strip=False, upx=False, name="ClipForge")
