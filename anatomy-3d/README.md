# Anatomy 3D Explorer

A touch-first, browser-based 3D viewer for anatomy teaching — built to run
full-screen on an interactive digital board, and to work the same way in a
student's browser on their own phone/tablet.

Renders a **real anatomical heart model** (not a cartoon shape) with
rotate / zoom / tap-to-label hotspots on the great vessels, atria, left
ventricle, coronary arteries, and vena cava/apex region.

## Model source & license

`models/heart.glb` — "Human Heart 3d Model" (entry 3DPX-022787), NIH 3D
Print Exchange, by Sourav Pan / Biology Notes Online.
**License: Public Domain (CC0)** — free to use, modify, and redistribute,
no attribution required. Credited here anyway as good practice.
https://3d.nih.gov/entries/3DPX-022787

## Run it locally

No build step, no install. From this folder:

```bash
python3 -m http.server 8080
# or: npx serve .
```

Then open `http://localhost:8080` in a browser. (Opening `index.html`
directly from disk won't work — glTF loading requires `http://`.)

Everything (Three.js, controls, GLTF loader, and the model itself) is
vendored in this folder, so this also works **fully offline** — no internet
connection needed once the files are copied onto the board's PC.

## Using it on a digital board

1. Copy this folder onto the PC/laptop driving the board (or host it — see
   below — and open the URL in the board's browser).
2. Open `index.html` in Chrome/Edge and click **Fullscreen** (or press F11).
   Most interactive boards forward touch as standard pointer/touch events to
   whatever browser is on screen, so drag-to-rotate, pinch-to-zoom, and tap
   just work — no special board software required.
3. Leave **Auto-rotate** on for an idle "ambient" demo when you're not
   actively presenting; it automatically turns off the moment someone
   touches the model.
4. Use **Reset** to snap back to the default camera angle between classes.

## Hosting it for students

Deploy the folder to any static host (Vercel, Netlify, GitHub Pages) and
share the link — students get the same rotate/zoom/tap experience on their
own phone or laptop browser. No app install needed. The same `.glb` file
also works for phone AR viewing (Android Scene Viewer natively, iOS via a
glTF→USDZ conversion step).

## Adding more organs / swapping the model

`main.js` loads whatever path is in `MODEL_URL` via `GLTFLoader` and fits
the camera to it automatically. To add another organ:

1. Drop a `.glb` file in `models/` (NIH 3D Print Exchange and Sketchfab's
   CC0/CC-BY listings are good sources — always check the license on the
   model's page before using it).
2. Point `MODEL_URL` at it, or extend the code to switch models when an
   organ button in the top nav is clicked.
3. Re-pick hotspot coordinates for the new mesh — the easiest way is to
   temporarily log `raycaster.intersectObject(model, true)` results while
   clicking on the rendered model, then hardcode the returned `point`
   coordinates into a new `HOTSPOTS` array (same pattern used for the heart).

Avoid PDF for the interactive 3D piece — "3D PDF" (U3D/PRC) only works in
desktop Adobe Acrobat, has no real touch support, and is being phased out.
Use PDF only for a printable/offline companion sheet (labeled screenshots +
key facts), not the interactive model itself.

## File structure

```
anatomy-3d/
├── index.html                entry point, import map for vendored Three.js
├── style.css                 board/touch-friendly UI
├── main.js                   scene setup, model loading, hotspots, controls
├── models/heart.glb          NIH 3D Print Exchange heart model (CC0)
├── vendor/three/             vendored Three.js, OrbitControls, CSS2DRenderer, GLTFLoader
└── README.md
```
