"""Legendas estilo "karaokê" (palavra atual destacada) em formato ASS, queimadas no vídeo pelo ffmpeg."""
from __future__ import annotations

from .transcribe import Word

PLAY_W, PLAY_H = 1080, 1920


def _ass_color(rrggbb: str) -> str:
    r, g, b = rrggbb[0:2], rrggbb[2:4], rrggbb[4:6]
    return f"&H00{b}{g}{r}".upper()  # ASS usa BGR


def _tag_color(rrggbb: str) -> str:
    """Cor para tags de sobreposição (\\c): &HBBGGRR&."""
    r, g, b = rrggbb[0:2], rrggbb[2:4], rrggbb[4:6]
    return f"&H{b}{g}{r}&".upper()


def _ts(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, rem = divmod(cs, 360000)
    m, rem = divmod(rem, 6000)
    s, c = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{c:02d}"


def _escape(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def group_words(words: list[Word], max_words: int = 3, max_chars: int = 18, max_gap: float = 0.6) -> list[list[Word]]:
    groups: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if cur:
            chars = sum(len(x.text) + 1 for x in cur) + len(w.text)
            if (len(cur) >= max_words or chars > max_chars or w.start - cur[-1].end > max_gap
                    or cur[-1].text.endswith((".", "?", "!", "…"))):
                groups.append(cur)
                cur = []
        cur.append(w)
    if cur:
        groups.append(cur)
    return groups


def build_ass(words: list[Word], clip_start: float, clip_end: float, *, font: str = "Arial", size: int = 84,
              uppercase: bool = True, color: str = "FFFFFF", highlight: str = "FFE600",
              badge_text: str | None = None) -> str:
    """`words` em tempo absoluto da fonte; os eventos saem relativos ao início do corte."""
    dur = clip_end - clip_start
    inside = [Word(w.text, w.start - clip_start, w.end - clip_start) for w in words
              if w.end > clip_start and w.start < clip_end]
    for w in inside:
        w.start = max(0.0, w.start)
        w.end = min(dur, w.end)

    c_main = _ass_color(color)
    t_main, t_hi = _tag_color(color), _tag_color(highlight)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {PLAY_W}
PlayResY: {PLAY_H}
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{font},{size},{c_main},{c_main},&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,2,2,60,60,520,1
Style: Badge,{font},{int(size * 0.62)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,3,10,0,8,0,0,150,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines: list[str] = []
    if badge_text:
        # BorderStyle 3 = caixa opaca atrás do texto; cor da caixa vem de OutlineColour (preto translúcido ok)
        lines.append(f"Dialogue: 0,{_ts(0)},{_ts(dur)},Badge,,0,0,0,,{_escape(badge_text)}")

    groups = group_words(inside)
    for gi, group in enumerate(groups):
        shown = [_escape(w.text.upper() if uppercase else w.text) for w in group]
        group_end = group[-1].end
        if gi + 1 < len(groups):
            nxt = groups[gi + 1][0].start
            if nxt - group_end < 0.35:
                group_end = nxt  # sem piscar entre grupos próximos
        for wi, w in enumerate(group):
            start = w.start
            end = group[wi + 1].start if wi + 1 < len(group) else group_end
            end = max(end, start + 0.05)
            parts = []
            for k, text in enumerate(shown):
                if k == wi:
                    parts.append(f"{{\\c{t_hi}\\t(0,90,\\fscx112\\fscy112)\\t(90,180,\\fscx100\\fscy100)}}{text}{{\\c{t_main}\\fscx100\\fscy100}}")
                else:
                    parts.append(text)
            lines.append(f"Dialogue: 1,{_ts(start)},{_ts(end)},Cap,,0,0,0,,{' '.join(parts)}")
    return header + "\n".join(lines) + "\n"
