import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js';

// ─── Bootstrap: wait for Vue to render the spacer ───────────────────────────

function boot() {
  const container = document.getElementById('avatar-scene');
  const spacer = document.querySelector('.avatar-placeholder');
  if (!container || !spacer) return false;

  init(container, spacer);
  return true;
}

if (!boot()) {
  const observer = new MutationObserver((_mutations, obs) => {
    if (boot()) obs.disconnect();
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

// ─── Main Init ──────────────────────────────────────────────────────────────

function init(container, spacer) {

  // ─── Position overlay on spacer ─────────────────────────────────────

  let lastW = 0, lastH = 0;

  function syncPosition() {
    const r = spacer.getBoundingClientRect();
    container.style.top = r.top + 'px';
    container.style.left = r.left + 'px';
    if (r.width !== lastW || r.height !== lastH) {
      lastW = r.width;
      lastH = r.height;
      container.style.width = r.width + 'px';
      container.style.height = r.height + 'px';
      if (r.width > 0 && r.height > 0) {
        renderer.setSize(r.width, r.height);
      }
    }
  }

  // ─── Renderer (transparent background) ──────────────────────────────

  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    premultipliedAlpha: false,
  });
  renderer.setClearColor(0x000000, 0);
  renderer.setPixelRatio(window.devicePixelRatio);

  const rect = spacer.getBoundingClientRect();
  renderer.setSize(Math.max(rect.width, 1), Math.max(rect.height, 1));
  container.appendChild(renderer.domElement);
  const canvas = renderer.domElement;
  canvas.style.touchAction = 'none';

  syncPosition();

  // ─── Scene + Camera ────────────────────────────────────────────────

  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-1.1, 1.1, 1.1, -1.1, 0.1, 10);
  camera.position.set(0, 0, 3);

  // ─── Lighting ─────────────────────────────────────────────────────

  scene.add(new THREE.AmbientLight(0xffffff, 0.6));
  const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
  dirLight.position.set(2, 2, 5);
  scene.add(dirLight);

  // ─── Circular Mesh ────────────────────────────────────────────────

  const geometry = new THREE.CircleGeometry(1.035, 64);
  const material = new THREE.MeshStandardMaterial({
    color: 0x333333,
    roughness: 0.4,
    metalness: 0.1,
  });
  const mesh = new THREE.Mesh(geometry, material);
  scene.add(mesh);

  // ─── Texture Loading ──────────────────────────────────────────────

  const textureLoader = new THREE.TextureLoader();
  const initialUrl = container.dataset.avatarUrl;
  if (initialUrl) {
    textureLoader.load(initialUrl, (tex) => {
      tex.colorSpace = THREE.SRGBColorSpace;
      material.map = tex;
      material.color.set(0xffffff);
      material.needsUpdate = true;
    });
  }

  // ─── Pointer Interaction: Drag → Tilt (view only, no upload) ──────

  const MAX_TILT = THREE.MathUtils.degToRad(30);
  let isPointerDown = false;
  let pointerStart = { x: 0, y: 0 };

  canvas.addEventListener('pointerdown', (e) => {
    canvas.setPointerCapture(e.pointerId);
    isPointerDown = true;
    pointerStart = { x: e.clientX, y: e.clientY };
  });

  canvas.addEventListener('pointermove', (e) => {
    if (!isPointerDown) return;
    const dx = e.clientX - pointerStart.x;
    const dy = e.clientY - pointerStart.y;
    const r = canvas.getBoundingClientRect();
    mesh.rotation.y = THREE.MathUtils.clamp(dx / r.width * 2, -1, 1) * MAX_TILT;
    mesh.rotation.x = THREE.MathUtils.clamp(-dy / r.height * 2, -1, 1) * MAX_TILT;
  });

  canvas.addEventListener('pointerup', (e) => {
    canvas.releasePointerCapture(e.pointerId);
    isPointerDown = false;
  });

  // ─── Render Loop ──────────────────────────────────────────────────

  const clock = new THREE.Clock();

  function animate() {
    requestAnimationFrame(animate);
    syncPosition();

    const dt = Math.min(clock.getDelta(), 0.05);
    const factor = 1.0 - Math.exp(-6.0 * dt);

    if (!isPointerDown) {
      mesh.rotation.x += (0 - mesh.rotation.x) * factor;
      mesh.rotation.y += (0 - mesh.rotation.y) * factor;
    }

    renderer.render(scene, camera);
  }

  animate();
}
