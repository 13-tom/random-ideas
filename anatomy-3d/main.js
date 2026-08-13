import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const viewport = document.getElementById("viewport");
const statusText = document.getElementById("status-text");
const infoPanel = document.getElementById("info-panel");
const infoTitle = document.getElementById("info-title");
const infoBody = document.getElementById("info-body");
const infoClose = document.getElementById("info-close");
const btnReset = document.getElementById("btn-reset");
const btnAutorotate = document.getElementById("btn-autorotate");
const btnFullscreen = document.getElementById("btn-fullscreen");

const MODEL_URL = "models/heart.glb";

/**
 * Coordinates are in the model's own local space (it loads already centered
 * near the origin) and were picked by raycasting against the real mesh from
 * several front-view screen positions, so each dot sits exactly on the
 * surface feature it names. Source model: NIH 3D Print Exchange, "Human
 * Heart 3d Model" (3DPX-022787), Public Domain / CC0. See README.md.
 */
const HOTSPOTS = [
  {
    position: [0.0472, 0.4482, 0.2069],
    title: "Great Vessels (Aorta / Pulmonary Artery)",
    body: "The large arteries at the top of the heart that carry blood away toward the body and lungs.",
  },
  {
    position: [0.112, 0.1191, 0.1868],
    title: "Atria (Pulmonary Vein Region)",
    body: "The upper chambers where blood enters the heart — the left atrium receives oxygen-rich blood from the lungs here.",
  },
  {
    position: [0.0565, -0.1131, 0.2888],
    title: "Left Ventricle (Anterior Surface)",
    body: "The heart's main pumping chamber — thick, muscular walls push oxygenated blood out through the aorta to the whole body.",
  },
  {
    position: [-0.0931, -0.1164, 0.2332],
    title: "Coronary Arteries",
    body: "The vessels running across the heart's own surface that supply the heart muscle itself with oxygenated blood.",
  },
  {
    position: [0.0349, -0.4648, 0.2362],
    title: "Inferior Vena Cava / Apex Region",
    body: "Near the bottom (apex) of the heart, where the great vein returning blood from the lower body enters the right atrium.",
  },
];

function showError(message) {
  statusText.textContent = message;
  const box = document.createElement("div");
  box.style.cssText =
    "position:absolute;inset:0;display:flex;align-items:center;justify-content:center;" +
    "padding:24px;text-align:center;color:#eef3f7;font-size:1.1rem;background:#0f1720;";
  box.textContent = message;
  viewport.appendChild(box);
}

function hasWebGL() {
  try {
    const canvas = document.createElement("canvas");
    return !!(
      window.WebGLRenderingContext &&
      (canvas.getContext("webgl") || canvas.getContext("experimental-webgl"))
    );
  } catch (e) {
    return false;
  }
}

function addHotspots(parent) {
  HOTSPOTS.forEach((spot) => {
    const el = document.createElement("div");
    el.className = "hotspot";
    el.title = spot.title;

    const marker = new CSS2DObject(el);
    marker.position.set(...spot.position);
    parent.add(marker);

    el.addEventListener("click", (e) => {
      e.stopPropagation();
      document
        .querySelectorAll(".hotspot.selected")
        .forEach((n) => n.classList.remove("selected"));
      el.classList.add("selected");
      infoTitle.textContent = spot.title;
      infoBody.textContent = spot.body;
      infoPanel.style.display = "block";
    });
  });
}

function init() {
  if (!hasWebGL()) {
    showError(
      "This browser/device does not support WebGL, which is required for the 3D viewer. Please use an up-to-date Chrome, Edge, or Safari on the digital board."
    );
    return;
  }

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0f1720);

  const camera = new THREE.PerspectiveCamera(
    45,
    viewport.clientWidth / viewport.clientHeight,
    0.01,
    100
  );
  camera.position.set(0, 0, 2);

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(viewport.clientWidth, viewport.clientHeight);
  viewport.appendChild(renderer.domElement);

  const labelRenderer = new CSS2DRenderer();
  labelRenderer.setSize(viewport.clientWidth, viewport.clientHeight);
  labelRenderer.domElement.style.position = "absolute";
  labelRenderer.domElement.style.top = "0";
  labelRenderer.domElement.style.left = "0";
  labelRenderer.domElement.style.pointerEvents = "none";
  viewport.appendChild(labelRenderer.domElement);

  scene.add(new THREE.AmbientLight(0xffffff, 0.8));
  const key = new THREE.DirectionalLight(0xffffff, 1.2);
  key.position.set(4, 6, 8);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x88aaff, 0.6);
  rim.position.set(-6, -3, -4);
  scene.add(rim);

  const controls = new OrbitControls(camera, labelRenderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 1.4;
  controls.target.set(0, 0, 0);

  let initialCameraPos = camera.position.clone();

  btnReset.addEventListener("click", () => {
    camera.position.copy(initialCameraPos);
    controls.target.set(0, 0, 0);
    controls.update();
  });

  btnAutorotate.addEventListener("click", () => {
    controls.autoRotate = !controls.autoRotate;
    btnAutorotate.textContent = `Auto-rotate: ${controls.autoRotate ? "On" : "Off"}`;
  });

  btnFullscreen.addEventListener("click", () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  });

  infoClose.addEventListener("click", () => {
    infoPanel.style.display = "none";
    document
      .querySelectorAll(".hotspot.selected")
      .forEach((n) => n.classList.remove("selected"));
  });

  // Any drag/zoom interaction pauses auto-rotate so it doesn't fight the user.
  controls.addEventListener("start", () => {
    controls.autoRotate = false;
    btnAutorotate.textContent = "Auto-rotate: Off";
  });

  function onResize() {
    const w = viewport.clientWidth;
    const h = viewport.clientHeight;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
    labelRenderer.setSize(w, h);
  }
  window.addEventListener("resize", onResize);

  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
    labelRenderer.render(scene, camera);
  }
  animate();

  statusText.textContent = "Loading heart model…";
  new GLTFLoader().load(
    MODEL_URL,
    (gltf) => {
      const model = gltf.scene;
      scene.add(model);
      addHotspots(model);

      const box = new THREE.Box3().setFromObject(model);
      const size = new THREE.Vector3();
      box.getSize(size);
      const maxDim = Math.max(size.x, size.y, size.z) || 1;

      camera.near = maxDim / 100;
      camera.far = maxDim * 20;
      camera.position.set(0, 0, maxDim * 1.7);
      camera.updateProjectionMatrix();
      controls.minDistance = maxDim * 0.5;
      controls.maxDistance = maxDim * 6;
      controls.update();
      initialCameraPos = camera.position.clone();

      statusText.textContent =
        "Heart model ready — source: NIH 3D Print Exchange (3DPX-022787), Public Domain.";
    },
    undefined,
    (err) => {
      console.error(err);
      showError(
        "Could not load the 3D heart model (models/heart.glb). Check that the file exists and that you're serving this folder over http:// (not opening index.html directly from disk)."
      );
    }
  );
}

try {
  init();
} catch (err) {
  console.error(err);
  showError("Something went wrong loading the 3D viewer: " + err.message);
}
