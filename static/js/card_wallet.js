import * as THREE from 'three';

// ─── Data ──────────────────────────────────────────────────────────────────

const container = document.getElementById('card-scene');
if (!container) console.error('[card_wallet] #card-scene not found');

const peerDataEl = document.getElementById('peer-data');
const peers = peerDataEl ? JSON.parse(peerDataEl.textContent) : [];
if (peers.length === 0) {
  container.innerHTML = '<p style="color:#888;text-align:center;margin-top:40vh;">No cards collected yet.</p>';
}

// ─── Renderer ──────────────────────────────────────────────────────────────

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
container.appendChild(renderer.domElement);
const canvas = renderer.domElement;

// Critical: prevent browser from intercepting pointer/wheel for its own
// scroll/gesture handling (matches what OrbitControls does in card_scene.js)
canvas.style.touchAction = 'none';

// ─── Scene + Camera ────────────────────────────────────────────────────────

const scene = new THREE.Scene();
// Transparent — NiceGUI body shows through

const camera = new THREE.PerspectiveCamera(
  45, window.innerWidth / window.innerHeight, 0.1, 100
);
camera.position.set(0, 0, 8);

// ─── Lighting ──────────────────────────────────────────────────────────────

scene.add(new THREE.AmbientLight(0xffffff, 0.6));
const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
dirLight.position.set(5, 5, 5);
scene.add(dirLight);

// ─── Card Construction ─────────────────────────────────────────────────────

const textureLoader = new THREE.TextureLoader();
const cardGeometry = new THREE.PlaneGeometry(3.2, 2.0);

function loadTexture(material, url) {
  textureLoader.load(url, (tex) => {
    tex.colorSpace = THREE.SRGBColorSpace;
    material.map = tex;
    material.color.set(0xffffff);
    material.needsUpdate = true;
  });
}

function createCard(peer) {
  const group = new THREE.Group();
  group.userData = { peer };

  // Front plane
  const frontMat = new THREE.MeshStandardMaterial({
    color: 0x333333, roughness: 0.4, metalness: 0.1,
    transparent: true, opacity: 1.0,
  });
  const front = new THREE.Mesh(cardGeometry, frontMat);
  front.name = 'front';
  group.add(front);

  // Back plane (rotated 180° Y)
  const backMat = new THREE.MeshStandardMaterial({
    color: 0x333333, roughness: 0.4, metalness: 0.1,
    transparent: true, opacity: 1.0,
  });
  const back = new THREE.Mesh(cardGeometry, backMat);
  back.rotation.y = Math.PI;
  back.name = 'back';
  group.add(back);

  // Load textures
  if (peer.front_url) loadTexture(frontMat, peer.front_url);
  if (peer.back_url) loadTexture(backMat, peer.back_url);

  scene.add(group);
  return group;
}

const cards = peers.map(createCard);

// ─── Carousel Layout ───────────────────────────────────────────────────────

const CARD_SPACING = 0.96;   // vertical gap between card slots
const DEPTH_FALLOFF = 0.8;   // how much non-center cards recede in Z
const SCALE_FALLOFF = 0.12;  // scale reduction per slot from center

let centerIndex = 0;

// Each card stores its animation target
cards.forEach(card => {
  card._target = { x: 0, y: 0, z: 0, sx: 1, sy: 1, sz: 1, opacity: 1.0 };
});

function computeTargets() {
  const n = cards.length;
  cards.forEach((card, i) => {
    // Shortest distance around the ring
    let offset = i - centerIndex;
    if (offset > n / 2) offset -= n;
    if (offset < -n / 2) offset += n;

    const absOff = Math.abs(offset);
    const t = card._target;
    t.y = -offset * CARD_SPACING;
    t.z = -absOff * DEPTH_FALLOFF;
    t.x = 0;
    const s = Math.max(0.5, 1.0 - absOff * SCALE_FALLOFF);
    t.sx = s; t.sy = s; t.sz = s;
    t.opacity = Math.max(0.15, 1.0 - absOff * 0.3);
  });
}

computeTargets();

// Set initial positions instantly
cards.forEach(card => {
  const t = card._target;
  card.position.set(t.x, t.y, t.z);
  card.scale.set(t.sx, t.sy, t.sz);
  card.rotation.set(0, 0, 0);
  card.children.forEach(mesh => { mesh.material.opacity = t.opacity; });
});

function animateToPositions() {
  computeTargets();
  // Lerp handles the rest in the render loop
}

// ─── Selection State ───────────────────────────────────────────────────────

let selectedCard = null;
const SELECTED_Z = 4.0;

function selectCard(card) {
  selectedCard = card;
  // Push selected card forward
  card._target.z = SELECTED_Z;
  card._target.opacity = 1.0;
  card._target.sx = 1.0;
  card._target.sy = 1.0;
  card._target.sz = 1.0;
  // Dim all others
  cards.forEach(c => {
    if (c !== card) c._target.opacity = 0.1;
  });
}

function deselectCard() {
  if (!selectedCard) return;
  selectedCard = null;
  animateToPositions();
}

// ─── Raycasting ────────────────────────────────────────────────────────────

const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();

function raycast(clientX, clientY) {
  const rect = canvas.getBoundingClientRect();
  pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);
  const meshes = [];
  cards.forEach(card => card.children.forEach(m => meshes.push(m)));
  const hits = raycaster.intersectObjects(meshes);
  if (hits.length > 0) return hits[0].object.parent; // the Group
  return null;
}

// ─── Input: Scroll to Cycle ───────────────────────────────────────────────

let scrollAccum = 0;
const SCROLL_THRESHOLD = 50;

// Listen on canvas directly (matches OrbitControls pattern from card_scene.js)
canvas.addEventListener('wheel', (e) => {
  if (selectedCard) return;
  e.preventDefault();
  scrollAccum += e.deltaY;
  if (Math.abs(scrollAccum) >= SCROLL_THRESHOLD) {
    const dir = scrollAccum > 0 ? 1 : -1;
    centerIndex = (centerIndex + dir + cards.length) % cards.length;
    animateToPositions();
    scrollAccum = 0;
  }
}, { passive: false });

// ─── Input: Click to Select / Deselect ─────────────────────────────────────

let pointerDownPos = { x: 0, y: 0 };
const CLICK_THRESHOLD = 8;

canvas.addEventListener('pointerdown', (e) => {
  // Capture pointer so move/up events route here even if pointer drifts
  // (matches what OrbitControls does internally)
  canvas.setPointerCapture(e.pointerId);

  pointerDownPos = { x: e.clientX, y: e.clientY };

  // Hold + drag detection for selected card
  if (selectedCard) {
    const hit = raycast(e.clientX, e.clientY);
    if (hit === selectedCard) {
      startHold(e);
      startDrag(e);
    }
  }
});

canvas.addEventListener('pointerup', (e) => {
  canvas.releasePointerCapture(e.pointerId);
  cancelHold();
  stopDrag();

  // Ignore if pointer moved (was a drag, not a click)
  const dx = e.clientX - pointerDownPos.x;
  const dy = e.clientY - pointerDownPos.y;
  const dist = Math.sqrt(dx * dx + dy * dy);
  if (dist > CLICK_THRESHOLD) return;

  const hit = raycast(e.clientX, e.clientY);

  if (selectedCard) {
    // Clicked outside the selected card → deselect
    if (hit !== selectedCard) {
      deselectCard();
    }
    return;
  }

  // Clicked the center card → select it
  if (hit && cards.indexOf(hit) === centerIndex) {
    selectCard(hit);
  }
});

// ─── Input: Drag Selected Card (X-axis rotation) ──────────────────────────

let isDragging = false;
let dragStartX = 0;
let cardStartRotY = 0;

function startDrag(e) {
  isDragging = true;
  dragStartX = e.clientX;
  cardStartRotY = selectedCard.rotation.y;
}

function stopDrag() {
  isDragging = false;
}

canvas.addEventListener('pointermove', (e) => {
  if (!isDragging || !selectedCard) return;
  const dx = e.clientX - dragStartX;
  selectedCard.rotation.y = cardStartRotY + dx * 0.008;

  // Cancel hold if moved enough
  if (Math.abs(dx) > 3) cancelHold();
});

// ─── Input: Touch drag to Cycle ───────────────────────────────────────────

let touchStartY = 0;

canvas.addEventListener('touchstart', (e) => {
  if (selectedCard) return;
  touchStartY = e.touches[0].clientY;
}, { passive: true });

canvas.addEventListener('touchend', (e) => {
  if (selectedCard) return;
  const dy = e.changedTouches[0].clientY - touchStartY;
  if (Math.abs(dy) > 30) {
    centerIndex = dy < 0
      ? (centerIndex + 1) % cards.length
      : (centerIndex - 1 + cards.length) % cards.length;
    animateToPositions();
  }
}, { passive: true });

// ─── Input: Hold Selected Card → Open Linktree ────────────────────────────

let holdTimer = null;
const HOLD_MS = 500;

function startHold() {
  cancelHold();
  holdTimer = setTimeout(() => {
    if (selectedCard) {
      const url = selectedCard.userData.peer.linktree_url;
      if (url) window.open(url, '_blank');
    }
    holdTimer = null;
  }, HOLD_MS);
}

function cancelHold() {
  if (holdTimer !== null) {
    clearTimeout(holdTimer);
    holdTimer = null;
  }
}

// ─── Resize ────────────────────────────────────────────────────────────────

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

// ─── Render Loop ───────────────────────────────────────────────────────────

const clock = new THREE.Clock();
const _v3 = new THREE.Vector3();
const _v3s = new THREE.Vector3();

function animate() {
  requestAnimationFrame(animate);
  const dt = Math.min(clock.getDelta(), 0.05); // cap to avoid huge jumps
  const speed = 6.0;
  const factor = 1.0 - Math.exp(-speed * dt);

  cards.forEach(card => {
    const t = card._target;

    // Lerp position
    _v3.set(t.x, t.y, t.z);
    card.position.lerp(_v3, factor);

    // Lerp scale
    _v3s.set(t.sx, t.sy, t.sz);
    card.scale.lerp(_v3s, factor);

    // Lerp opacity
    card.children.forEach(mesh => {
      mesh.material.opacity += (t.opacity - mesh.material.opacity) * factor;
    });

    // Lerp rotation.y toward 0 for non-selected cards (reset after deselect)
    if (card !== selectedCard) {
      card.rotation.y += (0 - card.rotation.y) * factor;
    }
  });

  renderer.render(scene, camera);
}

animate();
