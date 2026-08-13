# Anatomy 3D Explorer (prototype)

A touch-first, browser-based 3D viewer for anatomy teaching — built to run
full-screen on an interactive digital board, and to work the same way in a
student's browser on their own phone/tablet.

This is a working **interaction prototype**: it renders a stylized 3D heart
(built procedurally, not a medical scan) with rotate / zoom / tap-to-label
hotspots. Swap in real anatomical models (see "Using real models" below)
once you're happy with the interaction pattern.

## Run it locally

No build step, no install. From this folder:

```bash
python3 -m http.server 8080
# or: npx serve .
```

Then open `http://localhost:8080` in a browser.

Everything (Three.js + controls) is vendored under `vendor/three/`, so this
also works **fully offline** — no internet connection needed once the files
are on the board's PC.

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
own phone or laptop browser. No app install needed.

## Using real anatomical models

Replace the procedural shape in `buildHeartMesh()` (`main.js`) with a loaded
`.glb`/`.gltf` model:

```js
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const loader = new GLTFLoader();
loader.load("models/heart.glb", (gltf) => {
  scene.add(gltf.scene);
});
```

- **Format**: use **glTF/GLB** — it's the modern standard, loads fast in the
  browser, and the *same file* also works for AR viewing on phones (Android
  Scene Viewer natively, iOS via a glTF→USDZ conversion step).
- Keep hotspot positions in the model's local coordinate space so they stay
  attached to the mesh as it rotates (same pattern as `addHotspots()`).
- Avoid PDF for the interactive 3D piece — "3D PDF" (U3D/PRC) only works in
  desktop Adobe Acrobat, has no real touch support, and is being phased out.
  Use PDF only for a printable/offline companion sheet (labeled screenshots
  + key facts), not the interactive model itself.

## File structure

```
anatomy-3d/
├── index.html          entry point, import map for vendored Three.js
├── style.css            board/touch-friendly UI
├── main.js               scene setup, heart geometry, hotspots, controls
├── vendor/three/        vendored Three.js + OrbitControls + CSS2DRenderer
└── README.md
```
