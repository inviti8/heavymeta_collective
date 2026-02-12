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

  // ─── Pointer Interaction: Mouse tracking → Tilt (no click needed) ──

  const MAX_TILT = THREE.MathUtils.degToRad(30);
  let targetRotX = 0, targetRotY = 0;

  canvas.addEventListener('pointermove', (e) => {
    const rect = canvas.getBoundingClientRect();
    const nx = ((e.clientX - rect.left) / rect.width) * 2 - 1;   // -1..+1
    const ny = -(((e.clientY - rect.top) / rect.height) * 2 - 1); // -1..+1 (inverted)
    targetRotY = nx * MAX_TILT;
    targetRotX = ny * MAX_TILT;
  });

  canvas.addEventListener('pointerleave', () => {
    targetRotX = 0;
    targetRotY = 0;
  });

  // ─── Click-and-Hold → Download QR Image ─────────────────────────────

  const HOLD_MS = 500;
  const MOVE_THRESHOLD = 3;
  let holdTimer = null;
  let holdStart = { x: 0, y: 0 };

  function downloadQr() {
    if (!qrUrl) return;
    fetch(qrUrl)
      .then(r => r.blob())
      .then(blob => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'heavymeta-qr.png';
        a.click();
        URL.revokeObjectURL(url);
      })
      .catch(() => {});
  }

  function cancelHold() {
    if (holdTimer !== null) {
      clearTimeout(holdTimer);
      holdTimer = null;
    }
  }

  canvas.addEventListener('pointerdown', (e) => {
    holdStart = { x: e.clientX, y: e.clientY };
    cancelHold();
    holdTimer = setTimeout(() => {
      downloadQr();
      holdTimer = null;
    }, HOLD_MS);
  });

  canvas.addEventListener('pointermove', (e) => {
    if (holdTimer === null) return;
    const dx = e.clientX - holdStart.x;
    const dy = e.clientY - holdStart.y;
    if (Math.sqrt(dx * dx + dy * dy) > MOVE_THRESHOLD) {
      cancelHold();
    }
  });

  canvas.addEventListener('pointerup', () => {
    cancelHold();
  });

  // ─── QR Scanner ────────────────────────────────────────────────────

  let html5QrCode = null;

  function extractMonikerSlug(text) {
    const match = text.match(/\/profile\/([a-z0-9-]+)/i);
    return match ? match[1].toLowerCase() : null;
  }

  // Scan button (upper-right, above 3D scene)
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
    <div id="qr-reader" style="width: min(80vw, 400px);"></div>
    <div id="qr-scan-result" style="
      display: none; color: white; margin-top: 24px; text-align: center;
      padding: 16px; background: rgba(255,255,255,0.1); border-radius: 12px;
      min-width: 250px;
    "></div>
  `;
  document.body.appendChild(overlay);

  function openScanner() {
    overlay.style.display = 'flex';
    const resultDiv = document.getElementById('qr-scan-result');
    resultDiv.style.display = 'none';

    html5QrCode = new Html5Qrcode('qr-reader');
    html5QrCode.start(
      { facingMode: 'environment' },
      { fps: 10, qrbox: { width: 250, height: 250 } },
      onScanSuccess,
    ).catch(() => {
      // Camera failed — try file-based fallback
      resultDiv.innerHTML = '<p>Camera not available. Try uploading a QR image instead.</p>';
      resultDiv.style.display = 'block';
    });
  }

  function closeScanner() {
    if (html5QrCode) {
      html5QrCode.stop().catch(() => {});
      html5QrCode.clear();
      html5QrCode = null;
    }
    overlay.style.display = 'none';
  }

  async function onScanSuccess(decodedText) {
    // Stop scanning immediately
    if (html5QrCode) {
      await html5QrCode.stop().catch(() => {});
      html5QrCode.clear();
      html5QrCode = null;
    }

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
            <button onclick="window.location.href='/card/case'"
                    style="padding: 8px 24px; border-radius: 8px;
                           background: rgba(140,82,255,0.6); border: none;
                           color: white; cursor: pointer;">
              VIEW CARDS
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
    openScanner();
  });
  document.body.appendChild(retryBtn);

  scanBtn.addEventListener('click', openScanner);
  document.getElementById('qr-scan-close').addEventListener('click', closeScanner);

  // ─── Render Loop ───────────────────────────────────────────────────

  const clock = new THREE.Clock();

  function animate() {
    requestAnimationFrame(animate);

    const dt = Math.min(clock.getDelta(), 0.05);
    const factor = 1.0 - Math.exp(-6.0 * dt);

    mesh.rotation.x += (targetRotX - mesh.rotation.x) * factor;
    mesh.rotation.y += (targetRotY - mesh.rotation.y) * factor;

    renderer.render(scene, camera);
  }

  animate();
}
