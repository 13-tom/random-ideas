# SJClothes — "Your Style. Your Choice." (28 s Reel)

1080 × 1920 · 30 fps · 28.0 s · H.264 + AAC, loudness-normalised to −14 LUFS for Reels.

**Output:** `out/sjclothes-reel.mp4`, plus `out/end-card.png` for use as a cover or thumbnail.

The reel is a motion-graphics edit built in code (`reel.html`) and rendered frame by frame (`render.js`).
The typography, logo animation, collage, transitions, CTA, music and voiceover are all finished.
**The people and clothes in it are styled placeholders.** Each shot is a named *footage slot*.
Drop your real clips into `footage/` and re-render. The edit, timing and titles stay the same,
and your footage replaces the placeholders.

## Shoot list: what to film for each slot

Name each file exactly after its slot: `footage/<slot>.mp4`. `.mov`, `.jpg` and `.png` also work.
Shoot vertical (9:16) if you can; landscape clips are centre-cropped. Up to 12 s of each clip is used.

| Slot | Used at | What to film |
|---|---|---|
| `men_look1` | 0.0–0.5 (hook), 7.5–9.5, collage | Male model, look 1, full-body walk towards camera, white or studio background |
| `women_look1` | 0.5–1.0 (hook), 11.75–13.5, collage | Female model, look 1, full-body editorial pose |
| `hook_detail` | 1.0–1.5 (hook) + triptych | Clothing close-up (fabric, buttons, label). Falls back to `women_detail` |
| `presenter` | 4.0–7.5 | Female presenter, medium shot, looking at camera, modern studio. Leave space on the right for the logo. She can lip-sync "Meet SJClothes!" |
| `men_detail` | 9.5–10.5, collage | Close-up of the men's outfit details |
| `men_look2` | 10.5–11.75, collage | Male model, look 2 |
| `women_detail` | 13.5–14.75, collage | Close-up of the women's garment details |
| `women_look2` | 14.75–16.25, collage | Female model, look 2 |
| `gallery_1` … `gallery_6` | 18.7–22.0 collage swaps | Optional extra looks. Each falls back to the clips above |

Keep faces and outfits in the **upper two-thirds** of the frame, because the titles sit at the bottom.

## Voiceover (timing in `audio/make_audio.py → VO_LINES`)

| Start | Line |
|---|---|
| 0.30 | Looking for a style that feels like you? |
| 4.15 | Meet SJClothes! |
| 7.75 | From everyday looks, |
| 11.75 | to styles that make a statement. Explore clothing for both men and women. |
| 16.35 | Different styles. Different vibes. One destination. |
| 19.95 | Your next favourite outfit is waiting. |
| 22.25 | Don't just follow fashion. Make it yours. |
| 24.75 | DM SJClothes today, and discover your style! |

The current voice is a **scratch AI read** (Piper TTS, "lessac" voice) used for timing.
For the final version, record the presenter or a voice artist line by line. Save the lines as
`audio/vo/l1.wav` … `l8.wav` and re-run. The music is an original synthesized 120 BPM beat with cuts landing on the beat.
To use licensed music instead, save it as `audio/music.wav`.

## Re-render

```bash
python3 audio/make_audio.py          # soundtrack (music + VO, ducked, -14 LUFS)
node render.js --notags              # -> out/sjclothes-reel.mp4 (~1 min)
node render.js --stills 2.6,6,23.6   # quick PNG checks in out/stills/
```

You can also open `reel.html` in a browser to preview it live. Click pauses, and double-click restarts with sound
(run `make_audio.py` first). Requirements: Node with Playwright/Chromium, ffmpeg, Python 3 with numpy.

## Brand system used
- **Colours:** paper `#F6F4F0`, ink `#111111`, SJ orange `#FF5B14`
- **Type:** Anton (impact headlines), Bodoni Moda italic (editorial accents), Archivo (UI and wordmark)
- **Logo:** a placeholder "SJ" monogram badge and SJCLOTHES wordmark. Send your real logo and I'll swap it in.
