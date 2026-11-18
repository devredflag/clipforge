"""Corte + enquadramento vertical 9:16 + legendas queimadas, tudo com ffmpeg."""
from __future__ import annotations

from pathlib import Path

from .. import media
from .captions import build_ass
from .transcribe import Word

W, H = 1080, 1920


def _filter_graph(layout: str) -> str:
    """Devolve o filter_complex que produz [v] já com legendas (arquivo captions.ass no cwd)."""
    if layout == "fill":
        return (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"setsar=1,ass=captions.ass[v]")
    # blur: vídeo inteiro no centro sobre o mesmo vídeo ampliado e desfocado (não perde nada do enquadramento)
    return (f"[0:v]split[a][b];"
            f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=40:6,eq=brightness=-0.12[bg];"
            f"[b]scale={W}:-2[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,ass=captions.ass[v]")


def render_clip(src: str | Path, start: float, end: float, words: list[Word], out_dir: str | Path, *,
                name: str, layout: str = "blur", normalize: bool = True, font: str = "Arial", size: int = 84,
                uppercase: bool = True, color: str = "FFFFFF", highlight: str = "FFE600",
                badge_text: str | None = None, src_offset: float = 0.0) -> tuple[Path, Path]:
    """Gera <name>.mp4 e <name>.jpg em out_dir.

    `start`/`end`: tempos na linha do tempo das `words`. `src_offset`: quanto subtrair para achar o ponto no
    arquivo `src` (usado na live, onde o arquivo de origem é só um pedaço da gravação).
    """
    media.ensure_tools()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{name}.mp4"
    thumb = out_dir / f"{name}.jpg"
    ass_path = out_dir / "captions.ass"  # cwd do ffmpeg = out_dir, evita problemas de caminho/':' no Windows
    ass_path.write_text(
        build_ass(words, start, end, font=font, size=size, uppercase=uppercase, color=color,
                  highlight=highlight, badge_text=badge_text),
        encoding="utf-8",
    )
    duration = end - start
    seek = max(0.0, start - src_offset)
    cmd = [
        media.ffmpeg_bin(), "-y", "-v", "error",
        "-ss", f"{seek:.3f}", "-i", str(Path(src).resolve()), "-t", f"{duration:.3f}",
        "-filter_complex", _filter_graph(layout), "-map", "[v]", "-map", "0:a:0?",
    ]
    if normalize:
        cmd += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"]
    cmd += [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-movflags", "+faststart", str(out.name),
    ]
    media.run(cmd, cwd=out_dir)
    media.run([media.ffmpeg_bin(), "-y", "-v", "error", "-ss", f"{min(1.0, duration / 2):.2f}", "-i", str(out.name),
               "-frames:v", "1", "-vf", "scale=360:-2", str(thumb.name)], cwd=out_dir)
    return out, thumb
