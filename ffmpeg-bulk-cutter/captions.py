"""Word-level caption generation: builds styled .ass subtitle files for
"word" (one word at a time, TikTok/CapCut style) and "highlight" (full line
with the currently-spoken word highlighted, Opus Clip style) caption modes.
"""
from dataclasses import dataclass
from pathlib import Path

NAMED_COLORS = {
    "white": (255, 255, 255),
    "yellow": (255, 255, 0),
    "black": (0, 0, 0),
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "cyan": (0, 255, 255),
    "blue": (0, 120, 255),
    "orange": (255, 165, 0),
}


@dataclass
class Word:
    start: float
    end: float
    text: str


def parse_color(value: str) -> tuple[int, int, int]:
    value = value.strip()
    if value.lower() in NAMED_COLORS:
        return NAMED_COLORS[value.lower()]
    hex_value = value.lstrip("#")
    if len(hex_value) == 6:
        try:
            return tuple(int(hex_value[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            pass
    raise ValueError(f"Unrecognized color: {value!r} (use a name like 'yellow' or a hex code like '#FFCC00')")


def _ass_style_color(rgb: tuple[int, int, int]) -> str:
    """&HAABBGGRR - used in the [V4+ Styles] section (alpha=00, opaque)."""
    r, g, b = rgb
    return f"&H00{b:02X}{g:02X}{r:02X}"


def _ass_override_color(rgb: tuple[int, int, int]) -> str:
    """&HBBGGRR& - used inline in dialogue text via a \\c override tag."""
    r, g, b = rgb
    return f"&H{b:02X}{g:02X}{r:02X}&"


def _escape_ass_text(text: str) -> str:
    # '{' and '}' delimit override tags in ASS; keep word text from
    # accidentally breaking the parser.
    return text.replace("{", "(").replace("}", ")").replace("\n", "\\N")


def format_ass_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    centis = round(seconds * 100)
    hours, centis = divmod(centis, 360000)
    minutes, centis = divmod(centis, 6000)
    secs, centis = divmod(centis, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def chunk_words(words: list[Word], max_words: int) -> list[list[Word]]:
    return [words[i:i + max_words] for i in range(0, len(words), max_words)]


def _ass_header(video_width: int, video_height: int, font: str, font_size: int,
                 primary_rgb: tuple[int, int, int], margin_v: int) -> str:
    primary = _ass_style_color(primary_rgb)
    outline = _ass_style_color((0, 0, 0))
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {video_width}\n"
        f"PlayResY: {video_height}\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font},{font_size},{primary},{primary},{outline},&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,3,1,2,40,40,{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


def write_ass_word_mode(words: list[Word], ass_path: Path, video_res: tuple[int, int],
                         font: str, font_size: int, text_rgb: tuple[int, int, int], margin_v: int) -> int:
    width, height = video_res
    lines = [_ass_header(width, height, font, font_size, text_rgb, margin_v)]
    count = 0
    for word in words:
        text = word.text.strip()
        if not text or word.end <= word.start:
            continue
        count += 1
        start = format_ass_timestamp(word.start)
        end = format_ass_timestamp(word.end)
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{_escape_ass_text(text)}\n")
    ass_path.write_text("".join(lines), encoding="utf-8")
    return count


def write_ass_highlight_mode(words: list[Word], ass_path: Path, video_res: tuple[int, int],
                              font: str, font_size: int, text_rgb: tuple[int, int, int],
                              highlight_rgb: tuple[int, int, int], margin_v: int, max_words: int) -> int:
    width, height = video_res
    lines = [_ass_header(width, height, font, font_size, text_rgb, margin_v)]
    primary_tag = _ass_override_color(text_rgb)
    highlight_tag = _ass_override_color(highlight_rgb)

    count = 0
    for group in chunk_words(words, max_words):
        group = [w for w in group if w.text.strip()]
        if not group:
            continue
        n = len(group)
        for i, word in enumerate(group):
            if word.end <= word.start and i + 1 >= n:
                continue
            start = word.start
            end = group[i + 1].start if i + 1 < n else word.end
            if end <= start:
                continue
            parts = []
            for j, w2 in enumerate(group):
                token = _escape_ass_text(w2.text.strip())
                if j == i:
                    parts.append(f"{{\\c{highlight_tag}}}{token}{{\\c{primary_tag}}}")
                else:
                    parts.append(token)
            text = " ".join(parts)
            count += 1
            lines.append(f"Dialogue: 0,{format_ass_timestamp(start)},{format_ass_timestamp(end)},Default,,0,0,0,,{text}\n")
    ass_path.write_text("".join(lines), encoding="utf-8")
    return count
