import * as THREE from 'https://esm.sh/three@0.170.0';

// ─── Data ──────────────────────────────────────────────────────────────────

const container = document.getElementById('card-scene');
if (!container) console.error('[card_wallet] #card-scene not found');

const cardDataEl = document.getElementById('card-data');
const peers = cardDataEl ? JSON.parse(cardDataEl.textContent) : [];

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
scene.background = new THREE.Color(0x0d0d0d);

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

function createCard(entry) {
  const group = new THREE.Group();
  group.userData = { peer: entry };

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
  if (entry.front_url) loadTexture(frontMat, entry.front_url);
  if (entry.back_url) loadTexture(backMat, entry.back_url);

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

// ─── Input: Click / Pointer-drag ───────────────────────────────────────────

let pointerDownPos = { x: 0, y: 0 };
let pointerIsDown = false;
let carouselDragAccum = 0;
const CLICK_THRESHOLD = 8;
const DRAG_CYCLE_THRESHOLD = 40; // px of vertical drag to cycle one card

canvas.addEventListener('pointerdown', (e) => {
  canvas.setPointerCapture(e.pointerId);
  pointerDownPos = { x: e.clientX, y: e.clientY };
  pointerIsDown = true;
  carouselDragAccum = 0;

  // Hold + drag-rotate detection for selected card
  if (selectedCard) {
    const hit = raycast(e.clientX, e.clientY);
    if (hit === selectedCard) {
      startHold(e);
      startRotateDrag(e);
    }
  }
});

canvas.addEventListener('pointermove', (e) => {
  if (!pointerIsDown) return;

  // Selected card: horizontal drag rotates on Y-axis
  if (isRotateDragging && selectedCard) {
    const dx = e.clientX - rotateDragStartX;
    selectedCard.rotation.y = cardStartRotY + dx * 0.008;
    if (Math.abs(dx) > 3) cancelHold();
    return;
  }

  // No selection: vertical pointer-drag cycles the carousel
  if (!selectedCard) {
    const dy = e.clientY - pointerDownPos.y;
    const travelled = dy - carouselDragAccum;
    if (Math.abs(travelled) >= DRAG_CYCLE_THRESHOLD) {
      const steps = Math.trunc(travelled / DRAG_CYCLE_THRESHOLD);
      // Drag down = positive dy = scroll toward next card (like scroll-down)
      centerIndex = (centerIndex + steps + cards.length) % cards.length;
      carouselDragAccum += steps * DRAG_CYCLE_THRESHOLD;
      animateToPositions();
    }
  }
});

canvas.addEventListener('pointerup', (e) => {
  canvas.releasePointerCapture(e.pointerId);
  cancelHold();
  stopRotateDrag();

  const wasDown = pointerIsDown;
  pointerIsDown = false;

  if (!wasDown) return;

  // Ignore if pointer moved (was a drag, not a click)
  const dx = e.clientX - pointerDownPos.x;
  const dy = e.clientY - pointerDownPos.y;
  const dist = Math.sqrt(dx * dx + dy * dy);
  if (dist > CLICK_THRESHOLD) return;

  const hit = raycast(e.clientX, e.clientY);

  if (selectedCard) {
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

// ─── Input: Drag Selected Card (Y-axis rotation) ──────────────────────────

let isRotateDragging = false;
let rotateDragStartX = 0;
let cardStartRotY = 0;

function startRotateDrag(e) {
  isRotateDragging = true;
  rotateDragStartX = e.clientX;
  cardStartRotY = selectedCard.rotation.y;
}

function stopRotateDrag() {
  isRotateDragging = false;
}

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
      const entry = selectedCard.userData.peer;
      if (entry.type === 'own' && entry.card_id) {
        // Own card: set as active card
        window.__setActiveCardId = entry.card_id;
        const trigger = document.getElementById('set-active-trigger');
        if (trigger) trigger.click();
      } else {
        // Peer card: open linktree
        const url = entry.linktree_url;
        if (url) window.open(url, '_blank');
      }
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

// ─── Live Card Insertion ──────────────────────────────────────────────────

window.addPeerCard = function () {
  const newPeer = window.__newPeerData;
  if (!newPeer) return;
  const card = createCard(newPeer);
  cards.push(card);
  card._target = { x: 0, y: 0, z: 0, sx: 1, sy: 1, sz: 1, opacity: 1.0 };
  centerIndex = cards.length - 1;
  animateToPositions();
  // Set initial position instantly to avoid lerp from origin
  const t = card._target;
  card.position.set(t.x, t.y, t.z);
  card.scale.set(t.sx, t.sy, t.sz);
  window.__newPeerData = null;
};

// ─── QR Scanner (moved from qr_view.js) ──────────────────────────────────

function extractMonikerSlug(text) {
  const match = text.match(/\/profile\/([a-z0-9-]+)/i);
  return match ? match[1].toLowerCase() : null;
}

let qrScanner = null;

// Scan button (top-right)
const scanBtn = document.createElement('button');
scanBtn.innerHTML = '<span class="material-icons" style="font-size:24px;">qr_code_scanner</span>';
scanBtn.style.cssText = `
  position: fixed; top: 16px; right: 16px; z-index: 6000;
  width: 48px; height: 48px; border-radius: 50%;
  background: rgba(255,255,255,0.15); border: none; cursor: pointer;
  color: white; display: flex; align-items: center; justify-content: center;
  backdrop-filter: blur(4px);
`;
document.body.appendChild(scanBtn);

// Manual add button (top-right, next to scan)
const addBtn = document.createElement('button');
addBtn.innerHTML = '<span class="material-icons" style="font-size:24px;">person_add</span>';
addBtn.style.cssText = `
  position: fixed; top: 16px; right: 72px; z-index: 6000;
  width: 48px; height: 48px; border-radius: 50%;
  background: rgba(255,255,255,0.15); border: none; cursor: pointer;
  color: white; display: flex; align-items: center; justify-content: center;
  backdrop-filter: blur(4px);
`;
document.body.appendChild(addBtn);

addBtn.addEventListener('click', () => {
  const trigger = document.getElementById('manual-add-trigger');
  if (trigger) trigger.click();
});

// Video element for nimiq/qr-scanner
let scanVideo = document.createElement('video');
scanVideo.id = 'qr-video';
scanVideo.style.cssText = `
  width: min(80vw, 400px); border-radius: 12px;
  object-fit: cover;
`;

// Scanner overlay
const overlay = document.createElement('div');
overlay.style.cssText = `
  position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
  z-index: 7000; background: rgba(0,0,0,0.9);
  display: none; flex-direction: column; align-items: center; justify-content: center;
`;
overlay.innerHTML = `
  <button id="qr-scan-close" style="
    position: absolute; top: 16px; right: 16px;
    width: 48px; height: 48px; border-radius: 50%;
    background: rgba(255,255,255,0.15); border: none; cursor: pointer;
    color: white; display: flex; align-items: center; justify-content: center;
  "><span class="material-icons" style="font-size:24px;">close</span></button>
  <p style="color: white; margin-bottom: 16px; font-size: 14px; opacity: 0.7;">
    Point camera at a member's QR code
  </p>
  <div id="qr-reader" style="width: min(80vw, 400px); display: flex; justify-content: center;"></div>
  <div id="qr-scan-result" style="
    display: none; color: white; margin-top: 24px; text-align: center;
    padding: 16px; background: rgba(255,255,255,0.1); border-radius: 12px;
    min-width: 250px;
  "></div>
`;
document.body.appendChild(overlay);

// Insert video into reader container
document.getElementById('qr-reader').appendChild(scanVideo);

// Load nimiq/qr-scanner (UMD build, sets window.QrScanner)
async function loadQrScannerLib() {
  if (window.QrScanner) return;
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = '/static/js/qr-scanner.umd.min.js';
    s.onload = resolve;
    s.onerror = reject;
    document.head.appendChild(s);
  });
}

async function openScanner() {
  overlay.style.display = 'flex';
  const resultDiv = document.getElementById('qr-scan-result');
  resultDiv.style.display = 'none';

  try {
    await loadQrScannerLib();

    QrScanner.WORKER_PATH = '/static/js/qr-scanner-worker.min.js';

    qrScanner = new QrScanner(
      scanVideo,
      (result) => onScanSuccess(result.data),
      {
        preferredCamera: 'environment',
        maxScansPerSecond: 15,
        highlightScanRegion: true,
        highlightCodeOutline: true,
        returnDetailedScanResult: true,
        calculateScanRegion: (video) => {
          const size = Math.min(video.videoWidth, video.videoHeight) * 0.67;
          const x = (video.videoWidth - size) / 2;
          const y = (video.videoHeight - size) / 2;
          return { x, y, width: size, height: size,
                   downScaledWidth: 400, downScaledHeight: 400 };
        },
      }
    );
    await qrScanner.start();
  } catch (e) {
    resultDiv.innerHTML = '<p>Camera not available. Check permissions and try again.</p>';
    resultDiv.style.display = 'block';
  }
}

function stopScanner() {
  if (qrScanner) {
    qrScanner.stop();
    qrScanner.destroy();
    qrScanner = null;
  }
}

function closeScanner() {
  stopScanner();
  overlay.style.display = 'none';
}

function onScanSuccess(decodedText) {
  stopScanner();

  const slug = extractMonikerSlug(decodedText);
  const resultDiv = document.getElementById('qr-scan-result');

  if (!slug) {
    resultDiv.innerHTML = `
      <p style="color: #ff6b6b;">Not a valid member QR code</p>
      <button onclick="document.getElementById('qr-scan-retry').click()"
              style="margin-top: 12px; padding: 8px 24px; border-radius: 8px;
                     background: rgba(255,255,255,0.2); border: none;
                     color: white; cursor: pointer;">
        SCAN ANOTHER
      </button>
    `;
    resultDiv.style.display = 'block';
    return;
  }

  // Trigger NiceGUI bridge
  window.__scannedPeerSlug = slug;
  window.__peerScanResult = null;
  document.getElementById('peer-scan-trigger').click();

  resultDiv.innerHTML = '<p style="opacity: 0.7;">Looking up member...</p>';
  resultDiv.style.display = 'block';

  // Poll for result from Python handler
  const poll = setInterval(() => {
    if (window.__peerScanResult === null) return;
    clearInterval(poll);

    const result = window.__peerScanResult;
    const moniker = window.__peerScanMoniker || '';

    if (result === 'ok') {
      resultDiv.innerHTML = `
        <p style="color: #69db7c; font-size: 18px; font-weight: bold;">Peer added!</p>
        <p style="margin-top: 8px; font-size: 16px;">${moniker}</p>
        <div style="display: flex; gap: 12px; margin-top: 16px; justify-content: center;">
          <button onclick="document.getElementById('qr-scan-close').click(); window.addPeerCard && window.addPeerCard();"
                  style="padding: 8px 24px; border-radius: 8px;
                         background: rgba(122,72,169,0.6); border: none;
                         color: white; cursor: pointer;">
            DONE
          </button>
          <button onclick="document.getElementById('qr-scan-retry').click()"
                  style="padding: 8px 24px; border-radius: 8px;
                         background: rgba(255,255,255,0.2); border: none;
                         color: white; cursor: pointer;">
            SCAN ANOTHER
          </button>
        </div>
      `;
    } else if (result === 'not_found') {
      resultDiv.innerHTML = `
        <p style="color: #ff6b6b;">Member not found</p>
        <button onclick="document.getElementById('qr-scan-retry').click()"
                style="margin-top: 12px; padding: 8px 24px; border-radius: 8px;
                       background: rgba(255,255,255,0.2); border: none;
                       color: white; cursor: pointer;">
          SCAN ANOTHER
        </button>
      `;
    } else if (result === 'self') {
      resultDiv.innerHTML = `
        <p style="color: #ffd43b;">That's your own QR code!</p>
        <button onclick="document.getElementById('qr-scan-retry').click()"
                style="margin-top: 12px; padding: 8px 24px; border-radius: 8px;
                       background: rgba(255,255,255,0.2); border: none;
                       color: white; cursor: pointer;">
          SCAN ANOTHER
        </button>
      `;
    }
  }, 100);
}

// Hidden retry button to restart scanner
const retryBtn = document.createElement('button');
retryBtn.id = 'qr-scan-retry';
retryBtn.style.display = 'none';
retryBtn.addEventListener('click', () => {
  const resultDiv = document.getElementById('qr-scan-result');
  resultDiv.style.display = 'none';
  // Re-insert video element (destroyed by previous scanner)
  const readerEl = document.getElementById('qr-reader');
  if (!readerEl.querySelector('video')) {
    const newVideo = document.createElement('video');
    newVideo.id = 'qr-video';
    newVideo.style.cssText = `
      width: min(80vw, 400px); border-radius: 12px;
      object-fit: cover;
    `;
    readerEl.appendChild(newVideo);
    scanVideo = newVideo;
  }
  openScanner();
});
document.body.appendChild(retryBtn);

scanBtn.addEventListener('click', openScanner);
document.getElementById('qr-scan-close').addEventListener('click', closeScanner);
