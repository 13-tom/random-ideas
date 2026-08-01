"""Word-level caption generation: builds styled .ass subtitle files for
"word" (one word at a time, TikTok/CapCut style) and "highlight" (full line
with the currently-spoken word highlighted, Opus Clip style) caption modes.
"""
from dataclasses import dataclass, field
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

POSITION_ALIGNMENT = {"bottom": 2, "middle": 5, "top": 8}


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class CaptionStyle:
    font: str = "Arial"
    font_size: int = 64
    text_rgb: tuple = (255, 255, 255)
    highlight_rgb: tuple = (255, 255, 0)
    outline_rgb: tuple = (0, 0, 0)
    outline_width: int = 3
    bold: bool = True
    italic: bool = False
    all_caps: bool = False
    box: bool = False
    position: str = "bottom"
    margin_v: int = 80


def parse_color(value: str) -> tuple:
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


def _ass_style_color(rgb: tuple) -> str:
    """&HAABBGGRR - used in the [V4+ Styles] section (alpha=00, opaque)."""
    r, g, b = rgb
    return f"&H00{b:02X}{g:02X}{r:02X}"


def _ass_override_color(rgb: tuple) -> str:
    """&HBBGGRR& - used inline in dialogue text via a \\c override tag."""
    r, g, b = rgb
    return f"&H{b:02X}{g:02X}{r:02X}&"


def _readable_text_on(bg_rgb: tuple) -> tuple:
    """Black or white text, whichever contrasts better against bg_rgb -
    used for text sitting on a --box highlight fill."""
    r, g, b = bg_rgb
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return (0, 0, 0) if luminance > 140 else (255, 255, 255)


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


def chunk_words(words: list, max_words: int) -> list:
    return [words[i:i + max_words] for i in range(0, len(words), max_words)]


def _style_line(name: str, style: CaptionStyle, primary_rgb: tuple, outline_rgb: tuple, border_style: int) -> str:
    # Confirmed empirically (rendered and visually compared several
    # variants): with BorderStyle=3, libass fills the box from
    # OutlineColour, not BackColour - BackColour turned out to have no
    # visible effect on the box at all. So outline_rgb here means "glyph
    # outline stroke color" for BorderStyle=1, but "box fill color" for
    # BorderStyle=3 - same ASS field, different visual meaning depending
    # on border_style.
    primary = _ass_style_color(primary_rgb)
    outline = _ass_style_color(outline_rgb)
    back = _ass_style_color((0, 0, 0))
    alignment = POSITION_ALIGNMENT[style.position]
    return (
        f"Style: {name},{style.font},{style.font_size},{primary},{primary},{outline},{back},"
        f"{-1 if style.bold else 0},{-1 if style.italic else 0},0,0,100,100,0,0,"
        f"{border_style},{style.outline_width},1,{alignment},40,40,{style.margin_v},1\n"
    )


def _ass_header(video_width: int, video_height: int, style: CaptionStyle) -> str:
    lines = [
        "[Script Info]\n",
        "ScriptType: v4.00+\n",
        f"PlayResX: {video_width}\n",
        f"PlayResY: {video_height}\n",
        "ScaledBorderAndShadow: yes\n",
        "\n",
        "[V4+ Styles]\n",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n",
        _style_line("Default", style, style.text_rgb, style.outline_rgb, border_style=1),
    ]
    if style.box:
        # BorderStyle=3 renders an opaque box instead of a text outline -
        # this is what gives the "colored pill behind the word" look. Text
        # on top of the box uses whichever of black/white contrasts better
        # against the highlight color.
        box_text_rgb = _readable_text_on(style.highlight_rgb)
        lines.append(_style_line("Highlight", style, box_text_rgb, style.highlight_rgb, border_style=3))
    lines += ["\n", "[Events]\n", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"]
    return "".join(lines)


def _word_text(style: CaptionStyle, text: str) -> str:
    text = text.strip()
    return text.upper() if style.all_caps else text


def write_ass_word_mode(words: list, ass_path: Path, video_res: tuple, style: CaptionStyle) -> int:
    width, height = video_res
    lines = [_ass_header(width, height, style)]
    style_name = "Highlight" if style.box else "Default"
    count = 0
    for word in words:
        text = _word_text(style, word.text)
        if not text or word.end <= word.start:
            continue
        count += 1
        start = format_ass_timestamp(word.start)
        end = format_ass_timestamp(word.end)
        lines.append(f"Dialogue: 0,{start},{end},{style_name},,0,0,0,,{_escape_ass_text(text)}\n")
    ass_path.write_text("".join(lines), encoding="utf-8")
    return count


def write_ass_highlight_mode(words: list, ass_path: Path, video_res: tuple, style: CaptionStyle, max_words: int) -> int:
    width, height = video_res
    lines = [_ass_header(width, height, style)]
    primary_tag = _ass_override_color(style.text_rgb)
    highlight_tag = _ass_override_color(style.highlight_rgb)

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
                token = _escape_ass_text(_word_text(style, w2.text))
                if j == i:
                    if style.box:
                        # \r switches to the "Highlight" style (opaque box)
                        # for just this word, then \r resets back to
                        # Default for the rest of the line.
                        parts.append(f"{{\\rHighlight}}{token}{{\\r}}")
                    else:
                        parts.append(f"{{\\c{highlight_tag}}}{token}{{\\c{primary_tag}}}")
                else:
                    parts.append(token)
            text = " ".join(parts)
            count += 1
            lines.append(f"Dialogue: 0,{format_ass_timestamp(start)},{format_ass_timestamp(end)},Default,,0,0,0,,{text}\n")
    ass_path.write_text("".join(lines), encoding="utf-8")
    return count
