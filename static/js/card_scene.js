import * as THREE from 'https://esm.sh/three@0.170.0';
import { OrbitControls } from 'https://esm.sh/three@0.170.0/examples/jsm/controls/OrbitControls.js';

// ─── Scene setup ────────────────────────────────────────────────────────────

const container = document.getElementById('card-scene');

if (!container) {
  console.error('[card_scene] #card-scene not found in DOM!');
}

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
container.appendChild(renderer.domElement);

const canvas = renderer.domElement;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1a1a2e);

const camera = new THREE.PerspectiveCamera(
  45, window.innerWidth / window.innerHeight, 0.1, 100
);
camera.position.set(0, 0, 5);

// ─── Lighting ───────────────────────────────────────────────────────────────

scene.add(new THREE.AmbientLight(0xffffff, 0.6));
const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
dirLight.position.set(5, 5, 5);
scene.add(dirLight);

// ─── Card geometry (NFC ratio: 85.6 x 53.98 mm) ────────────────────────────

const cardGeometry = new THREE.PlaneGeometry(3.2, 2.0);

// Front plane — faces camera (normal +Z)
const frontMaterial = new THREE.MeshStandardMaterial({
  color: 0x333333, roughness: 0.4, metalness: 0.1,
});
const frontMesh = new THREE.Mesh(cardGeometry, frontMaterial);
frontMesh.name = 'CardFront';
scene.add(frontMesh);

// Back plane — rotated 180° around Y (normal -Z)
const backMaterial = new THREE.MeshStandardMaterial({
  color: 0x333333, roughness: 0.4, metalness: 0.1,
});
const backMesh = new THREE.Mesh(cardGeometry, backMaterial);
backMesh.rotation.y = Math.PI;
backMesh.name = 'CardBack';
scene.add(backMesh);

// ─── OrbitControls (horizontal-only turntable) ──────────────────────────────

const controls = new OrbitControls(camera, canvas);
controls.minPolarAngle = Math.PI / 2;
controls.maxPolarAngle = Math.PI / 2;
controls.enablePan = false;
controls.enableDamping = true;
controls.minDistance = 3;
controls.maxDistance = 8;

// ─── Texture loading ────────────────────────────────────────────────────────

const loader = new THREE.TextureLoader();

window.updateCardTexture = function (face, url) {
  const material = face === 'back' ? backMaterial : frontMaterial;
  loader.load(url, (texture) => {
    texture.colorSpace = THREE.SRGBColorSpace;
    material.map = texture;
    material.color.set(0xffffff);
    material.needsUpdate = true;
  });
};

// Load initial textures if available
const initialFrontTexture = container.dataset.frontTexture;
const initialBackTexture = container.dataset.backTexture;
if (initialFrontTexture) {
  window.updateCardTexture('front', initialFrontTexture);
}
if (initialBackTexture) {
  window.updateCardTexture('back', initialBackTexture);
}

// ─── Raycasting — detect which face the pointer is over ─────────────────────

const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();

function getFaceUnderPointer(clientX, clientY) {
  const rect = canvas.getBoundingClientRect();
  pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects([frontMesh, backMesh]);
  if (hits.length > 0) return hits[0].object.name; // 'CardFront' or 'CardBack'
  return null;
}

// ─── Click-and-hold → file dialog ───────────────────────────────────────────

const fileInput = document.createElement('input');
fileInput.type = 'file';
fileInput.accept = 'image/*';
fileInput.style.display = 'none';
document.body.appendChild(fileInput);

let holdTimer = null;
let startX = 0;
let startY = 0;
const HOLD_MS = 500;
const MOVE_THRESHOLD = 3;

// Track which face was detected on hold
window.__cardUploadFace = 'front';

canvas.addEventListener('pointerdown', (e) => {
  startX = e.clientX;
  startY = e.clientY;
  holdTimer = setTimeout(() => {
    // Detect which face the pointer is over
    const hit = getFaceUnderPointer(e.clientX, e.clientY);
    if (hit === 'CardBack') {
      window.__cardUploadFace = 'back';
    } else {
      window.__cardUploadFace = 'front';
    }
    fileInput.click();
    holdTimer = null;
  }, HOLD_MS);
});

canvas.addEventListener('pointermove', (e) => {
  if (holdTimer === null) return;
  const dx = e.clientX - startX;
  const dy = e.clientY - startY;
  if (Math.sqrt(dx * dx + dy * dy) > MOVE_THRESHOLD) {
    clearTimeout(holdTimer);
    holdTimer = null;
  }
});

canvas.addEventListener('pointerup', () => {
  if (holdTimer !== null) {
    clearTimeout(holdTimer);
    holdTimer = null;
  }
});

fileInput.addEventListener('change', () => {
  const file = fileInput.files[0];
  if (!file) return;

  const face = window.__cardUploadFace;

  const reader = new FileReader();
  reader.onload = () => {
    // Instant client-side preview
    const dataUrl = reader.result;
    window.updateCardTexture(face, dataUrl);

    // Store base64 + face for IPFS upload via Python
    const base64 = dataUrl.split(',')[1];
    window.__cardUploadData = base64;

    // Trigger the NiceGUI upload handler
    const trigger = document.getElementById('card-upload-trigger');
    if (trigger) {
      trigger.click();
    } else {
      console.error('[card_scene] trigger button not found!');
    }
  };
  reader.readAsDataURL(file);
  fileInput.value = '';
});

// ─── Resize handler ─────────────────────────────────────────────────────────

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// ─── Render loop ────────────────────────────────────────────────────────────

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}
animate();
