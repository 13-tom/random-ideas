# Fashion Lookbook Studio

Standing brief for every garment shoot. The model reference lives in
`model/character-sheet.webp` and must be supplied as the identity reference
for every generated image.

## Model profile (identity lock)

- Same woman in every image: young adult, oval face with defined cheekbones,
  softly arched dark brows, almond-shaped brown eyes, straight refined nose,
  full neutral-rose lips, light-olive / warm-beige skin tone.
- Hair: sleek dark brown, **center part**, pulled back smoothly into a
  **low braided (coiled) bun** at the nape. No loose strands, no fringe.
- Makeup: natural and elegant. Soft brown eyeshadow, defined lashes,
  light blush, nude-rose lip.
- Expression: calm, confident, closed-mouth, editorial.
- No jewellery or accessories unless they are part of the garment.

## Shot list (four separate files per garment, never a collage)

| # | File | Shot |
|---|------|------|
| 1 | `01-full-front.jpg` | Full body, head to toe, facing camera, relaxed hands, entire garment and hem visible |
| 2 | `02-half-front.jpg` | Body turned 30–45°, face toward camera, framed head to mid-thigh; neckline, drape, sleeves, front detail |
| 3 | `03-full-back.jpg` | Full body from behind, braided bun visible; real back construction only, never invented embroidery |
| 4 | `04-detail.jpg` | Close-up of the actual embroidery / print / texture / cuffs, sharp and colour-accurate |

## Output spec

- Exactly **559 × 1000 px**, vertical portrait.
- Pure white seamless background **#FFFFFF**.
- Soft, even studio lighting; realistic skin and fabric folds; accurate colours.
- No text, watermark, logo, border or overlay.

## Garment rules

Reproduce the supplied garment exactly: colours, fabric, embroidery, prints,
panel placement and orientation, sleeves, collar, neckline, cuffs, silhouette.
Add nothing (no extra buttons, patterns, embroidery or accessories) and
simplify nothing.

## Folder layout per garment

```
lookbook/garments/<garment-name>/
  reference/      # the photos you send
  output/         # 01-full-front.jpg … 04-detail.jpg (559x1000)
```
