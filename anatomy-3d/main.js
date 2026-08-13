import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { CSS2DRenderer, CSS2DObject } from "three/addons/renderers/CSS2DRenderer.js";

const viewport = document.getElementById("viewport");
const statusText = document.getElementById("status-text");
const infoPanel = document.getElementById("info-panel");
const infoTitle = document.getElementById("info-title");
const infoBody = document.getElementById("info-body");
const infoClose = document.getElementById("info-close");
const btnReset = document.getElementById("btn-reset");
const btnAutorotate = document.getElementById("btn-autorotate");
const btnFullscreen = document.getElementById("btn-fullscreen");

/**
 * NOTE FOR THE TEACHER / DEVELOPER:
 * The heart below is a stylized, procedurally-extruded shape used to
 * demonstrate the touch interaction pattern (rotate / zoom / tap-hotspot)
 * on a digital board. It is NOT anatomically precise. For classroom use,
 * swap `buildHeartMesh()` for a loaded .glb/.gltf anatomical model (see
 * README.md) and keep the same hotspot + info-panel wiring.
 */
const HOTSPOTS = [
  {
    u: 0.03,
    title: "Great Vessels (Aorta / Pulmonary Trunk)",
    body: "The large arteries at the top of the heart, between the two atria, that carry blood away toward the body and lungs.",
  },
  {
    u: 0.18,
    title: "Left Ventricle",
    body: "The heart's main pumping chamber — thick, muscular walls push oxygenated blood out through the aorta to the whole body.",
  },
  {
    u: 0.4,
    title: "Left Atrium",
    body: "Receives oxygen-rich blood from the lungs via the pulmonary veins, then passes it to the left ventricle.",
  },
  {
    u: 0.63,
    title: "Right Atrium",
    body: "Receives deoxygenated blood returning from the body via the vena cava, then passes it to the right ventricle.",
  },
  {
    u: 0.85,
    title: "Right Ventricle",
    body: "Pumps deoxygenated blood into the pulmonary artery, toward the lungs.",
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

function buildHeartShape() {
  const shape = new THREE.Shape();
  const x = 0;
  const y = 0;
  shape.moveTo(x + 5, y + 5);
  shape.bezierCurveTo(x + 5, y + 5, x + 4, y, x, y);
  shape.bezierCurveTo(x - 6, y, x - 6, y + 7, x - 6, y + 7);
  shape.bezierCurveTo(x - 6, y + 11, x - 3, y + 15.4, x + 5, y + 19);
  shape.bezierCurveTo(x + 12, y + 15.4, x + 16, y + 11, x + 16, y + 7);
  shape.bezierCurveTo(x + 16, y + 7, x + 16, y, x + 10, y);
  shape.bezierCurveTo(x + 7, y, x + 5, y + 5, x + 5, y + 5);
  return shape;
}

function buildHeartMesh() {
  const shape = buildHeartShape();
  const extrudeSettings = {
    depth: 6,
    bevelEnabled: true,
    bevelThickness: 1.2,
    bevelSize: 1,
    bevelSegments: 6,
    curveSegments: 32,
  };

  const geometry = new THREE.ExtrudeGeometry(shape, extrudeSettings);
  geometry.computeBoundingBox();
  const center = new THREE.Vector3();
  geometry.boundingBox.getCenter(center);
  geometry.translate(-center.x, -center.y, -center.z);
  geometry.computeVertexNormals();
  geometry.scale(0.28, 0.28, 0.28);
  center.multiplyScalar(0.28);

  const material = new THREE.MeshStandardMaterial({
    color: 0xd6455c,
    roughness: 0.45,
    metalness: 0.05,
  });

  const mesh = new THREE.Mesh(geometry, material);
  mesh.rotation.z = Math.PI; // point (apex) downward like a real heart

  const frontZ = (extrudeSettings.depth + extrudeSettings.bevelThickness) * 0.28 - center.z;
  const curve = shape.getSpacedPoints(400);

  return { mesh, shape, frontZ, center };
}

function addHotspots(mesh, shape, frontZ) {
  const group = new THREE.Group();
  mesh.add(group);

  HOTSPOTS.forEach((spot) => {
    const p = shape.getPointAt(spot.u);
    const local = new THREE.Vector3(
      (p.x - 5) * 0.28,
      (p.y - 9.5) * 0.28,
      frontZ
    );

    const el = document.createElement("div");
    el.className = "hotspot";
    el.title = spot.title;

    const marker = new CSS2DObject(el);
    marker.position.copy(local);
    group.add(marker);

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

  // rotation.z = PI on the parent mesh flips local group children too,
  // so hotspots stay attached to the correct visual location automatically.
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
    0.1,
    100
  );
  camera.position.set(0, 0, 9);

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

  scene.add(new THREE.AmbientLight(0xffffff, 0.65));
  const key = new THREE.DirectionalLight(0xffffff, 1.1);
  key.position.set(4, 6, 8);
  scene.add(key);
  const rim = new THREE.DirectionalLight(0x88aaff, 0.5);
  rim.position.set(-6, -3, -4);
  scene.add(rim);

  const { mesh, shape, frontZ } = buildHeartMesh();
  scene.add(mesh);
  addHotspots(mesh, shape, frontZ);

  const controls = new OrbitControls(camera, labelRenderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.08;
  controls.minDistance = 4;
  controls.maxDistance = 20;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 1.4;
  controls.target.set(0, 0, 0);

  const initialCameraPos = camera.position.clone();

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

  statusText.textContent = "Heart model ready — stylized schematic demo.";
  animate();
}

try {
  init();
} catch (err) {
  console.error(err);
  showError("Something went wrong loading the 3D viewer: " + err.message);
}
