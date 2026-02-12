import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js';

// ─── Bootstrap: wait for Vue to render ──────────────────────────────────────

function boot() {
  const container = document.getElementById('qr-dialog-scene');
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

  // Size to container (dialog card), not full viewport
  const rect = container.getBoundingClientRect();
  renderer.setSize(rect.width || window.innerWidth, rect.height || window.innerHeight);
  container.appendChild(renderer.domElement);
  const canvas = renderer.domElement;
  canvas.style.touchAction = 'none';

  const resizeObserver = new ResizeObserver(() => {
    const r = container.getBoundingClientRect();
    renderer.setSize(r.width, r.height);
    const a = r.width / r.height;
    camera.left = -viewSize * a;
    camera.right = viewSize * a;
    camera.top = viewSize;
    camera.bottom = -viewSize;
    camera.updateProjectionMatrix();
  });
  resizeObserver.observe(container);

  // ─── Scene + Camera ────────────────────────────────────────────────

  const scene = new THREE.Scene();

  const viewSize = 1.3;
  const aspect = (rect.width || window.innerWidth) / (rect.height || window.innerHeight);
  const camera = new THREE.OrthographicCamera(
    -viewSize * aspect, viewSize * aspect,
    viewSize, -viewSize,
    0.1, 10
  );
  camera.position.set(0, 0, 3);

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

  // ─── Pointer Interaction: Mouse tracking → Tilt (no click needed) ──

  const MAX_TILT = THREE.MathUtils.degToRad(30);
  let targetRotX = 0, targetRotY = 0;

  canvas.addEventListener('pointermove', (e) => {
    const cr = canvas.getBoundingClientRect();
    const nx = ((e.clientX - cr.left) / cr.width) * 2 - 1;
    const ny = -(((e.clientY - cr.top) / cr.height) * 2 - 1);
    targetRotY = nx * MAX_TILT;
    targetRotX = ny * MAX_TILT;
  });

  canvas.addEventListener('pointerleave', () => {
    targetRotX = 0;
    targetRotY = 0;
  });

  // ─── Render Loop ───────────────────────────────────────────────────

  const clock = new THREE.Clock();
  let animId = null;

  function animate() {
    animId = requestAnimationFrame(animate);

    const dt = Math.min(clock.getDelta(), 0.05);
    const factor = 1.0 - Math.exp(-6.0 * dt);

    mesh.rotation.x += (targetRotX - mesh.rotation.x) * factor;
    mesh.rotation.y += (targetRotY - mesh.rotation.y) * factor;

    renderer.render(scene, camera);
  }

  animate();

  // ─── Cleanup on removal ───────────────────────────────────────────

  const cleanupObserver = new MutationObserver(() => {
    if (!document.body.contains(container)) {
      cancelAnimationFrame(animId);
      resizeObserver.disconnect();
      cleanupObserver.disconnect();
      geometry.dispose();
      material.dispose();
      renderer.dispose();
    }
  });
  cleanupObserver.observe(document.body, { childList: true, subtree: true });
}
