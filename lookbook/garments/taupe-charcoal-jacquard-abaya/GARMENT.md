# Taupe & Charcoal Jacquard Abaya

References: `reference/` (front mannequin, back mannequin, back sleeve, jacquard
close-up, front flat-lay). Model: `../../model/character-sheet.webp`.

## Garment description (garment lock)

- **Type:** open-front, floor-length kimono-style abaya with very wide
  batwing / butterfly sleeves cut in one with the body. No closures, no
  buttons, no belt.
- **Colours:** three tones only.
  - Charcoal slate grey (main body).
  - Mocha taupe brown (collar band and outer sleeve panels).
  - Black / grey / ivory jacquard in an abstract marbled, wave-like
    camouflage pattern with a soft sheen.
- **Collar / front band:** a wide (about 8–9 cm) taupe shawl band runs from the
  back neck down both front edges to the hem.
- **Front panels:**
  - **Wearer's RIGHT front** (viewer's left): a vertical jacquard strip
    (about 10–12 cm wide) sits right beside the taupe band, from shoulder to hem.
    Outside it is a charcoal panel.
  - **Wearer's LEFT front** (viewer's right): plain charcoal next to the
    taupe band, with no jacquard strip.
- **Sleeves (both, identical):** charcoal near the shoulder and body, with a
  diagonal seam into a large taupe outer panel. A horizontal jacquard band
  (about 15 cm deep) crosses the taupe outer sleeve at forearm level, with
  taupe above and below it. The taupe extends down the side to the hem, giving
  a cocoon/trapezoid silhouette.
- **Back:** charcoal centre back, plain, with no jacquard strip and no
  embroidery. Taupe collar band visible at the back neck. The taupe outer
  sleeves and their jacquard bands are visible from behind.
- **Seams:** fine taupe piping between charcoal and jacquard panels.
- **Fabric:** soft, fluid, matte-satin crepe (silk-like) with gentle sheen;
  jacquard slightly stiffer with woven texture and subtle lustre.
- **Do not add:** embroidery, beading, buttons, belt, lining colour, extra
  pattern panels, jewellery or a hijab/shayla.

## Prompts (one image per prompt, never a collage)

Attach **both** the character sheet and the front flat-lay (plus the back
mannequin photo for shot 3) with every prompt.

### Shared block (paste after each shot prompt)

```
MODEL: the exact same woman from the attached character sheet: same face, eyes, nose, lips, warm-beige skin, natural elegant makeup, sleek dark-brown center-parted hair in a low braided bun. Same age and identity.
GARMENT: reproduce the attached abaya exactly: open-front floor-length kimono abaya with wide batwing sleeves; charcoal slate-grey body; wide mocha-taupe collar band down both front edges; one vertical black/grey/ivory marbled jacquard strip ONLY on the wearer's right front beside the taupe band; wearer's left front plain charcoal; each sleeve charcoal near the shoulder turning into a taupe outer panel crossed by a horizontal jacquard band at forearm level; plain charcoal back. Soft fluid matte-satin crepe. No added embroidery, buttons, belt, jewellery or accessories. Do not redesign or simplify.
STYLE: professional luxury fashion e-commerce photograph, pure white seamless studio background (#FFFFFF), soft even studio lighting, realistic skin texture, natural fabric folds, sharp focus, accurate colours. Vertical portrait 9:16. No text, logo, watermark or border. Single image, not a collage.
```

### 1 · Full front
```
Full-length front view: model standing straight, facing the camera, arms relaxed at her sides so the batwing sleeves fall naturally. Entire abaya visible from collar to floor-length hem, head to toe in frame with white space above and below.
```

### 2 · Half front / three-quarter
```
Three-quarter view: model's body turned about 35 degrees to her left, face turned naturally toward the camera. Framed from head to mid-thigh. Highlight the taupe collar band, the vertical jacquard front strip, the sleeve drape and the jacquard sleeve band. One hand lightly holding the front edge.
```

### 3 · Full back
```
Full-length back view: model standing with her back to the camera, head slightly turned so the low braided bun is clearly visible. Show the plain charcoal back, the taupe collar band at the back neck, both taupe outer sleeves with their horizontal jacquard bands, and the full hem, head to toe in frame. No pattern or embroidery on the back panel.
```

### 4 · Design close-up
```
Close-up product detail: tight crop on the wearer's right front where the taupe collar band meets the vertical black/grey/ivory marbled jacquard strip and the charcoal panel, showing the fine taupe piping seam, the woven jacquard texture and the satin sheen. Only fabric fills the frame (part of the model's shoulder may appear). Razor-sharp detail, accurate colours.
```

## Post-processing (done here)

Each output is cropped and resized to **559 × 1000**. Near-white background
pixels are flattened to **#FFFFFF**, and the file is saved as
`output/01-full-front.jpg` … `output/04-detail.jpg`.
