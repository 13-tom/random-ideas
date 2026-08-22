#!/usr/bin/env python3
"""Build an Instagram "prompt reveal" image carousel from a folder of numbered
photos - no video/ffmpeg involved, this one is pure image compositing (PIL).

Folder layout expected:
    1.jpg              <- the BASE/TEMPLATE photo (defines the scene AND the
                          exact output canvas size - every slide comes out
                          at this photo's width x height, nothing is resized
                          away from it)
    2.jpg   2a.jpg      <- pair #2: 2.jpg = ORIGINAL reference face photo,
                          2a.jpg = the AI "after" result (same scene as the
                          base photo, new face)
    3.jpg   3a.jpg      <- pair #3, same idea
    4.jpg   4a.jpg      <- pair #4, and so on - as many pairs as you have

("a"/"A" suffix both work, so do .jpg/.jpeg/.png in any mix.)

Output is one carousel of slides, in order:
    01_cover.jpg   - base photo + big "PROMPT" text top + "SWIPE" bottom
    02_slide.jpg   - pair #2's "a" result, full-bleed, + a small rounded
                     inset of pair #2's original face bottom-right, + a
                     page-number badge top-right (e.g. "2/5")
    03_slide.jpg   - pair #3, same treatment
    ...            - one slide per pair, in ascending number order
    NN_cta.jpg     - base photo again, darkened, + "COMMENT FOR" / "PROMPT"
                     centered + your logo underneath (final slide, always
                     last, always present even if you only have 1 pair)

If a pair is incomplete (only the plain photo or only the "a" one, not
both), it's skipped - the carousel just ends up with fewer slides. Nothing
is auto-generated to fill a gap.

Usage:
    python template_carousel.py my_carousel_folder/ -o carousel_out
    python template_carousel.py my_carousel_folder/ -o out --logo prompts_drive
    python template_carousel.py my_carousel_folder/ -o out --prompt-text "RECIPE"
"""
import argparse
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# Logo assets live alongside this script (in logos/), same convention as
# add_logo.py. Register your carousel CTA logo here once you have it, then
# pick it with --logo <name> - or just pass a raw file path to --logo.
LOGOS_DIR = Path(__file__).resolve().parent / "logos"
LOGO_PRESETS = {
    # "prompts_drive": str(LOGOS_DIR / "prompts_drive.png"),
}

# ============================================================================
# DEFAULTS - edit these directly to nudge the look without touching the
# rest of the file, or override per-run with the matching --flag (see
# --help). All pixel values are relative to the base photo's own size
# (scaled from a 1206x1512-ish reference), computed proportionally below so
# they hold up across different base photo resolutions.
# ============================================================================

DEFAULT_PROMPT_TEXT = "PROMPT"
DEFAULT_SWIPE_TEXT = "SWIPE"
DEFAULT_CTA_LINE1 = "COMMENT FOR"
DEFAULT_CTA_LINE2 = "PROMPT"

PROMPT_TOP_MARGIN_PCT = 0.045          # cover slide: "PROMPT" text top edge, as % of canvas height
PROMPT_SIDE_MARGIN_PCT = 0.035         # cover slide: max text width = canvas width minus 2x this
SWIPE_BOTTOM_MARGIN_PCT = 0.055        # cover slide: "SWIPE" text baseline distance from bottom

INSET_WIDTH_PCT = 0.30                 # reveal slide: inset (original face) width, as % of canvas width
INSET_MARGIN_PCT = 0.045               # reveal slide: inset distance from right/bottom edges
INSET_BORDER_PX_PCT = 0.006            # reveal slide: white border thickness around inset, as % of canvas width
INSET_CORNER_RADIUS_PCT = 0.03         # reveal slide: inset rounded-corner radius, as % of canvas width

PAGE_BADGE_MARGIN_PCT = 0.04           # reveal slide: page-number badge distance from top/right edges
PAGE_BADGE_FONT_PCT = 0.032            # reveal slide: page-number badge font size, as % of canvas height

CTA_DIM_OPACITY = 0.62                 # cta slide: black overlay opacity over the base photo (0=none, 1=fully black)
CTA_LINE1_Y_PCT = 0.50                 # cta slide: "COMMENT FOR" vertical center, as % of canvas height
CTA_LINE2_GAP_PCT = 0.018              # cta slide: gap between "COMMENT FOR" and "PROMPT"
CTA_LOGO_WIDTH_PCT = 0.30              # cta slide: logo width, as % of canvas width
CTA_LOGO_BOTTOM_MARGIN_PCT = 0.06      # cta slide: logo distance from bottom edge

# ============================================================================

# Bold sans-serif candidates, checked in order, across OSes - override with
# --font if none of these exist on your machine.
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/Arialbd.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def find_font(explicit: str = None) -> str:
    if explicit:
        if not Path(explicit).exists():
            sys.exit(f"--font {explicit!r} not found")
        return explicit
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    sys.exit(
        "No bold sans-serif font found on this machine. Pass one explicitly with "
        "--font /path/to/some-bold.ttf (any .ttf/.otf works)."
    )


def _resolve_logo_path(logo: str) -> Path:
    if logo in LOGO_PRESETS:
        path = Path(LOGO_PRESETS[logo])
    else:
        path = Path(logo)
    if not path.exists():
        presets = ", ".join(sorted(LOGO_PRESETS)) or "(none registered yet - edit LOGO_PRESETS in this file)"
        sys.exit(f"--logo {logo!r} isn't a known preset or an existing file path. Known presets: {presets}")
    return path


def discover_pairs(folder: Path):
    """Returns (base_path, [(number, original_path, result_path), ...]) sorted by number."""
    files = [p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS]
    numbered = {}   # number -> path (plain)
    lettered = {}   # number -> path ("a" suffix)
    base_path = None
    for p in files:
        m = re.match(r"^(\d+)(a)?$", p.stem, re.IGNORECASE)
        if not m:
            continue
        number = int(m.group(1))
        if number == 1 and not m.group(2):
            base_path = p
        elif m.group(2):
            lettered[number] = p
        else:
            numbered[number] = p
    if base_path is None:
        sys.exit(f"No base template photo found in {folder} (expected a file named 1.jpg / 1.png / etc.)")
    pairs = []
    for number in sorted(numbered):
        if number in lettered:
            pairs.append((number, numbered[number], lettered[number]))
        else:
            print(f"    skipping #{number}: has the original photo but no matching '{number}a' result photo")
    for number in sorted(lettered):
        if number not in numbered:
            print(f"    skipping #{number}a: has the result photo but no matching '{number}' original photo")
    if not pairs:
        sys.exit(f"No complete original/result pairs found in {folder}")
    return base_path, pairs


def crop_to_fill(img: Image.Image, size: tuple) -> Image.Image:
    """Scale-to-cover + center-crop, ffmpeg 'crop to fill' equivalent for PIL."""
    target_w, target_h = size
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = round(src_w * scale), round(src_h * scale)
    resized = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def fit_font(text: str, font_path: str, max_width: int, start_size: int) -> ImageFont.FreeTypeFont:
    """Grows/shrinks font size so `text` rendered in it is as wide as possible
    without exceeding max_width."""
    size = start_size
    font = ImageFont.truetype(font_path, size)
    width = font.getbbox(text)[2]
    if width < max_width:
        while width < max_width:
            size += 2
            font = ImageFont.truetype(font_path, size)
            width = font.getbbox(text)[2]
        size -= 2
    else:
        while width > max_width and size > 4:
            size -= 2
            font = ImageFont.truetype(font_path, size)
            width = font.getbbox(text)[2]
    return ImageFont.truetype(font_path, size)


def draw_text_centered_x(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
                          canvas_width: int, top_y: int, fill=(255, 255, 255)):
    bbox = font.getbbox(text)
    text_width = bbox[2] - bbox[0]
    x = (canvas_width - text_width) // 2 - bbox[0]
    draw.text((x, top_y), text, font=font, fill=fill)
    return bbox[3] - bbox[1]   # rendered text height


def rounded_alpha_mask(size: tuple, radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def build_cover_slide(base_img: Image.Image, font_path: str, prompt_text: str, swipe_text: str) -> Image.Image:
    canvas = base_img.copy().convert("RGB")
    w, h = canvas.size
    draw = ImageDraw.Draw(canvas)

    prompt_font = fit_font(prompt_text, font_path, w - 2 * round(w * PROMPT_SIDE_MARGIN_PCT), start_size=round(h * 0.1))
    draw_text_centered_x(draw, prompt_text, prompt_font, w, round(h * PROMPT_TOP_MARGIN_PCT))

    swipe_font = ImageFont.truetype(font_path, round(h * 0.028))
    dashed = f"\u2014 {swipe_text} \u2192"
    bbox = swipe_font.getbbox(dashed)
    text_h = bbox[3] - bbox[1]
    bottom_y = h - round(h * SWIPE_BOTTOM_MARGIN_PCT) - text_h
    draw_text_centered_x(draw, dashed, swipe_font, w, bottom_y)
    return canvas


def build_reveal_slide(result_img: Image.Image, original_img: Image.Image, canvas_size: tuple,
                        font_path: str, page_num: int, total_pages: int) -> Image.Image:
    w, h = canvas_size
    canvas = crop_to_fill(result_img, canvas_size).convert("RGB")

    inset_w = round(w * INSET_WIDTH_PCT)
    original_fit = crop_to_fill(original_img, (inset_w, inset_w))  # square inset, matches the reference screenshots
    border = round(w * INSET_BORDER_PX_PCT)
    radius = round(w * INSET_CORNER_RADIUS_PCT)

    bordered_size = (inset_w + 2 * border, inset_w + 2 * border)
    bordered = Image.new("RGB", bordered_size, (255, 255, 255))
    bordered.paste(original_fit, (border, border))
    mask = rounded_alpha_mask(bordered_size, radius)

    margin = round(w * INSET_MARGIN_PCT)
    pos = (w - margin - bordered_size[0], h - margin - bordered_size[1])
    canvas.paste(bordered, pos, mask)

    draw = ImageDraw.Draw(canvas)
    badge_font = ImageFont.truetype(font_path, round(h * PAGE_BADGE_FONT_PCT))
    badge_text = f"{page_num}/{total_pages}"
    bbox = badge_font.getbbox(badge_text)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = round(text_h * 0.6), round(text_h * 0.4)
    badge_margin = round(w * PAGE_BADGE_MARGIN_PCT)
    box_right = w - badge_margin
    box_top = badge_margin
    box = (box_right - text_w - 2 * pad_x, box_top, box_right, box_top + text_h + 2 * pad_y)
    draw.rounded_rectangle(box, radius=(box[3] - box[1]) // 2, fill=(0, 0, 0, 160))
    draw.text((box[0] + pad_x - bbox[0], box[1] + pad_y - bbox[1]), badge_text, font=badge_font, fill=(255, 255, 255))
    return canvas


def build_cta_slide(base_img: Image.Image, font_path: str, line1: str, line2: str, logo_path: Path = None) -> Image.Image:
    canvas = base_img.copy().convert("RGB")
    w, h = canvas.size

    overlay = Image.new("RGB", (w, h), (0, 0, 0))
    canvas = Image.blend(canvas, overlay, CTA_DIM_OPACITY)
    draw = ImageDraw.Draw(canvas)

    line1_font = ImageFont.truetype(font_path, round(h * 0.03))
    line2_font = fit_font(line2, font_path, round(w * 0.6), start_size=round(h * 0.075))

    line1_bbox = line1_font.getbbox(line1)
    line1_h = line1_bbox[3] - line1_bbox[1]
    line1_top = round(h * CTA_LINE1_Y_PCT) - line1_h
    draw_text_centered_x(draw, line1, line1_font, w, line1_top, fill=(255, 255, 255))

    line1_w = line1_bbox[2] - line1_bbox[0]
    underline_y = line1_top + line1_h + round(h * 0.008)
    draw.line(
        ((w - line1_w) // 2, underline_y, (w + line1_w) // 2, underline_y),
        fill=(255, 255, 255), width=max(1, round(h * 0.002)),
    )

    line2_top = underline_y + round(h * CTA_LINE2_GAP_PCT)
    line2_h = draw_text_centered_x(draw, line2, line2_font, w, line2_top, fill=(255, 255, 255))

    if logo_path:
        logo = Image.open(logo_path).convert("RGBA")
        logo_w = round(w * CTA_LOGO_WIDTH_PCT)
        logo_h = round(logo.height * (logo_w / logo.width))
        logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
        logo_x = (w - logo_w) // 2
        logo_y = h - round(h * CTA_LOGO_BOTTOM_MARGIN_PCT) - logo_h
        canvas.paste(logo, (logo_x, logo_y), logo)

    return canvas


def build_carousel(folder: Path, output_dir: Path, font_path: str, prompt_text: str, swipe_text: str,
                    cta_line1: str, cta_line2: str, logo_path: Path = None):
    base_path, pairs = discover_pairs(folder)
    base_img = Image.open(base_path)
    canvas_size = base_img.size
    total_pages = len(pairs) + 2   # cover + reveal slides + cta

    output_dir.mkdir(parents=True, exist_ok=True)

    cover = build_cover_slide(base_img, font_path, prompt_text, swipe_text)
    cover.save(output_dir / "01_cover.jpg", quality=95)
    print(f"  [1/{total_pages}] 01_cover.jpg")

    for i, (number, original_path, result_path) in enumerate(pairs, start=2):
        result_img = Image.open(result_path)
        original_img = Image.open(original_path)
        slide = build_reveal_slide(result_img, original_img, canvas_size, font_path, i, total_pages)
        name = f"{i:02d}_slide.jpg"
        slide.save(output_dir / name, quality=95)
        print(f"  [{i}/{total_pages}] {name}  (pair #{number}: {original_path.name} + {result_path.name})")

    cta = build_cta_slide(base_img, font_path, cta_line1, cta_line2, logo_path)
    cta_name = f"{total_pages:02d}_cta.jpg"
    cta.save(output_dir / cta_name, quality=95)
    print(f"  [{total_pages}/{total_pages}] {cta_name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="Folder containing 1.jpg (base) plus N/Na pairs")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("carousel_out"), help="Where to write the slide images (default: ./carousel_out)")
    parser.add_argument("--logo", help=f"Logo for the final CTA slide - preset name or PNG path. Known presets: {', '.join(sorted(LOGO_PRESETS)) or '(none registered yet)'}. Omit to skip the logo.")
    parser.add_argument("--prompt-text", default=DEFAULT_PROMPT_TEXT, help=f"Cover slide top text (default: {DEFAULT_PROMPT_TEXT!r})")
    parser.add_argument("--swipe-text", default=DEFAULT_SWIPE_TEXT, help=f"Cover slide bottom text (default: {DEFAULT_SWIPE_TEXT!r})")
    parser.add_argument("--cta-line1", default=DEFAULT_CTA_LINE1, help=f"CTA slide small top line (default: {DEFAULT_CTA_LINE1!r})")
    parser.add_argument("--cta-line2", default=DEFAULT_CTA_LINE2, help=f"CTA slide big bottom line (default: {DEFAULT_CTA_LINE2!r})")
    parser.add_argument("--font", help="Path to a .ttf/.otf bold font (auto-detected if omitted)")
    args = parser.parse_args()

    if not args.input.exists() or not args.input.is_dir():
        sys.exit(f"Input folder not found: {args.input}")

    font_path = find_font(args.font)
    logo_path = _resolve_logo_path(args.logo) if args.logo else None

    print(f"Building carousel from {args.input}/ ...")
    build_carousel(args.input, args.output_dir, font_path, args.prompt_text, args.swipe_text,
                    args.cta_line1, args.cta_line2, logo_path)
    print(f"\nDone. Slides in {args.output_dir}/")


if __name__ == "__main__":
    main()
