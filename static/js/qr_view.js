import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js';

// ─── Bootstrap: wait for Vue to render ──────────────────────────────────────

function boot() {
  const container = document.getElementById('qr-scene');
  if (!container) return false;

  init(container);
  return true;
}

if (!boot()) {
  const observer = new MutationObserver((_mutations, obs) => {
    if (boot()) obs.disconnect();
  });
  observer.observe(document.body, { childList: true, subtree: true });
}

// ─── Main Init ──────────────────────────────────────────────────────────────

function init(container) {

  // ─── Renderer (dark background, matching card views) ────────────────

  const renderer = new THREE.WebGLRenderer({
    antialias: true,
  });
  renderer.setClearColor(0x1a1a2e, 1);
  renderer.setPixelRatio(window.devicePixelRatio);
  renderer.setSize(window.innerWidth, window.innerHeight);
  container.appendChild(renderer.domElement);
  const canvas = renderer.domElement;
  canvas.style.touchAction = 'none';

  window.addEventListener('resize', () => {
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  // ─── Scene + Camera ────────────────────────────────────────────────

  const scene = new THREE.Scene();

  // Orthographic camera — sized so the QR fills most of the viewport
  const aspect = window.innerWidth / window.innerHeight;
  const viewSize = 1.3;
  const camera = new THREE.OrthographicCamera(
    -viewSize * aspect, viewSize * aspect,
    viewSize, -viewSize,
    0.1, 10
  );
  camera.position.set(0, 0, 3);

  window.addEventListener('resize', () => {
    const a = window.innerWidth / window.innerHeight;
    camera.left = -viewSize * a;
    camera.right = viewSize * a;
    camera.top = viewSize;
    camera.bottom = -viewSize;
    camera.updateProjectionMatrix();
  });

  // NO lighting — MeshBasicMaterial is unlit

  // ─── Rounded Rectangle Geometry ────────────────────────────────────

  const w = 0.6, h = 0.6, r = 0.04;
  const shape = new THREE.Shape();
  shape.moveTo(-w + r, -h);
  shape.lineTo(w - r, -h);
  shape.quadraticCurveTo(w, -h, w, -h + r);
  shape.lineTo(w, h - r);
  shape.quadraticCurveTo(w, h, w - r, h);
  shape.lineTo(-w + r, h);
  shape.quadraticCurveTo(-w, h, -w, h - r);
  shape.lineTo(-w, -h + r);
  shape.quadraticCurveTo(-w, -h, -w + r, -h);

  const geometry = new THREE.ShapeGeometry(shape);

  // Fix UVs — ShapeGeometry derives UVs from vertex positions (-w..+w),
  // but textures expect 0..1. Remap to frontal projection.
  const uvAttr = geometry.attributes.uv;
  for (let i = 0; i < uvAttr.count; i++) {
    uvAttr.setX(i, (uvAttr.getX(i) + w) / (2 * w));
    uvAttr.setY(i, (uvAttr.getY(i) + h) / (2 * h));
  }
  uvAttr.needsUpdate = true;

  // ─── Material (unlit, emissive appearance) ─────────────────────────

  const material = new THREE.MeshBasicMaterial({
    color: 0x333333,
    side: THREE.FrontSide,
  });

  const mesh = new THREE.Mesh(geometry, material);
  scene.add(mesh);

  // ─── Texture Loading ───────────────────────────────────────────────

  const textureLoader = new THREE.TextureLoader();
  const qrUrl = container.dataset.qrUrl;
  if (qrUrl) {
    textureLoader.load(qrUrl, (tex) => {
      tex.colorSpace = THREE.SRGBColorSpace;
      material.map = tex;
      material.color.set(0xffffff);
      material.needsUpdate = true;
    });
  }

  // ─── Pointer Interaction: Drag → Tilt (read-only, no upload) ──────

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
    const rect = canvas.getBoundingClientRect();
    mesh.rotation.y = THREE.MathUtils.clamp(dx / rect.width * 2, -1, 1) * MAX_TILT;
    mesh.rotation.x = THREE.MathUtils.clamp(-dy / rect.height * 2, -1, 1) * MAX_TILT;
  });

  canvas.addEventListener('pointerup', (e) => {
    canvas.releasePointerCapture(e.pointerId);
    isPointerDown = false;
  });

  // ─── Render Loop ───────────────────────────────────────────────────

  const clock = new THREE.Clock();

  function animate() {
    requestAnimationFrame(animate);

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
