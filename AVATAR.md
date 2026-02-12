# AVATAR.md — 3D Avatar Prototype

## Overview

Replace the flat `<img>` avatar in the dashboard header with a 3D circular plane rendered via a small inline Three.js scene. The scene has a transparent background so it composites seamlessly into the NiceGUI layout as if it were a regular 2D element. The mesh responds to pointer interaction (tilt on drag, snap-back on release) and supports click-and-hold to upload a new texture — the same pattern used in card customization.

---

## Interaction Design

### Idle State
- Circular plane faces the camera straight-on (rotation 0, 0, 0)
- Displays the user's avatar texture, or `/static/placeholder.png` if none set

### Drag → Tilt
- On pointer-down + move: the mesh tilts toward the pointer
- **X-axis rotation** tracks vertical drag (up/down), clamped to ±20°
- **Y-axis rotation** tracks horizontal drag (left/right), clamped to ±20°
- Gives a subtle 3D "coin" feel without full orbit

### Mouse-Up → Snap Back
- On pointer-up: rotation lerps smoothly back to (0, 0, 0)
- Same exponential lerp as card wallet (fast at first, eases to rest)

### Click-and-Hold → Upload
- 500ms hold (same threshold as card editor) opens file dialog
- Movement >3px cancels the hold (same as card editor)
- On file select:
  1. Instant client-side preview (apply dataURL as texture)
  2. Base64 data passed to Python via hidden trigger button
  3. Python pins to IPFS, stores CID in DB, republishes linktree

---

## Geometry

### Circular Plane via `CircleGeometry`

```javascript
const geometry = new THREE.CircleGeometry(1.0, 64); // radius=1, 64 segments
```

- 64 segments gives a smooth circle
- Single-sided (faces +Z, toward camera)
- No back face needed — user never sees the back

### Camera

```javascript
const camera = new THREE.OrthographicCamera(-1.1, 1.1, 1.1, -1.1, 0.1, 10);
camera.position.set(0, 0, 3);
```

- **Orthographic** — no perspective distortion, looks flat when untilted
- Framing: circle of radius 1.0 with slight padding (±1.1)
- Orthographic is key to making the 3D scene look like a 2D element

### Material

```javascript
const material = new THREE.MeshStandardMaterial({
  color: 0x333333,
  roughness: 0.4,
  metalness: 0.1,
});
```

Same material profile as the card meshes. When a texture is loaded:
```javascript
material.map = texture;
material.color.set(0xffffff);
material.needsUpdate = true;
```

---

## Scene Setup

### Transparent Background

```javascript
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setClearColor(0x000000, 0);
```

`alpha: true` + zero clear alpha = fully transparent canvas. The NiceGUI header gradient shows through behind the avatar.

### Lighting

Match the card editor lighting:
```javascript
scene.add(new THREE.AmbientLight(0xffffff, 0.6));
const dir = new THREE.DirectionalLight(0xffffff, 0.8);
dir.position.set(2, 2, 5);
scene.add(dir);
```

### Container Size

The current avatar is `w-[8vw] h-[8vw]`. The Three.js canvas will match this size. The `#avatar-scene` container is styled to the same dimensions and sits in the same layout position.

```css
#avatar-scene {
  width: 8vw;
  height: 8vw;
  border-radius: 50%;
  overflow: hidden; /* clip canvas to circle */
}
```

The circular clip is done via CSS `border-radius: 50%` + `overflow: hidden` on the container — this avoids needing alpha masking in the shader.

---

## Data Model

### DB Migration

```sql
ALTER TABLE users ADD COLUMN avatar_cid TEXT
```

Add to `init_db()` migrations list in `db.py`.

### Linktree JSON

`build_linktree_json()` already accepts `avatar_cid` and writes it to the JSON. `build_linktree_fresh()` and `republish_linktree()` currently pass `avatar_cid=None` — update these to read from the user row.

### Linktree Renderer

`linktree_renderer.py` already handles `avatar_cid` with a fallback to placeholder. No changes needed there.

---

## File Structure

| File | Action | Description |
|------|--------|-------------|
| `static/js/avatar_scene.js` | **NEW** | Standalone Three.js module for 3D avatar |
| `components.py` | MODIFY | Replace `ui.image()` avatar with `ui.html()` container + Three.js scene |
| `db.py` | MODIFY | Add `avatar_cid` column migration |
| `ipfs_client.py` | MODIFY | Pass `avatar_cid` from user row in `build_linktree_fresh()` and `republish_linktree()` |
| `main.py` | MODIFY | Add upload handler for avatar (same pattern as card editor) |

---

## Implementation Steps

### Step 1: DB — Add `avatar_cid` column

- Add migration to `init_db()`: `ALTER TABLE users ADD COLUMN avatar_cid TEXT`
- Update `build_linktree_fresh()` and `republish_linktree()` in `ipfs_client.py` to pass `user['avatar_cid']` instead of `None`

### Step 2: `static/js/avatar_scene.js` — Three.js Module

New standalone module:

```
avatar_scene.js
├── Renderer (alpha: true, transparent clear)
├── Orthographic camera (framing the circle)
├── CircleGeometry(1.0, 64) + MeshStandardMaterial
├── Lighting (ambient + directional)
├── Pointer interaction
│   ├── pointerdown → start tracking + hold timer
│   ├── pointermove → tilt mesh (clamped ±20°), cancel hold if moved
│   └── pointerup → cancel hold, snap-back rotation via lerp
├── Hold → file dialog → texture upload bridge
│   ├── fileInput.click() on hold completion
│   ├── FileReader → dataURL → instant preview
│   ├── window.__avatarUploadData = base64
│   └── trigger #avatar-upload-trigger click
├── window.updateAvatarTexture(url) — exposed for Python
├── Resize observer (adapts to container size changes)
└── Render loop (lerp rotation, render)
```

### Step 3: `components.py` — Replace Avatar Element

In `dashboard_header()`, replace:
```python
ui.image('/static/placeholder.png').classes('w-[8vw] h-[8vw] rounded-full shadow-md')
```

With an inline container for the Three.js scene. The Three.js import map and CSS are injected via `ui.add_head_html()`. The scene container, data attributes, and script tag are added inline.

The `dashboard_header()` function will need to accept `avatar_cid` so it can pass the initial texture URL to the scene.

### Step 4: Upload Handler in `main.py`

Add an avatar upload handler on pages that show the header (primarily `/profile/edit`). Same bridge pattern as card editor:

1. Hidden `ui.button(on_click=process_avatar_upload)` with `id=avatar-upload-trigger`
2. `process_avatar_upload()` reads `window.__avatarUploadData` via `ui.run_javascript()`
3. Decodes base64, pins to IPFS via `replace_asset()`
4. Updates `db.update_user(user_id, avatar_cid=new_cid)`
5. Calls `schedule_republish(user_id)`

### Step 5: Initial Texture on Page Load

When the page loads, if the user has an `avatar_cid`, the Python handler passes it as a `data-avatar-url` attribute on the `#avatar-scene` container. The JS reads it and calls `updateAvatarTexture(url)` on init.

---

## Rotation Math

```javascript
const MAX_TILT = THREE.MathUtils.degToRad(20); // ±20°

canvas.addEventListener('pointermove', (e) => {
  if (!isPointerDown) return;
  const dx = e.clientX - pointerStart.x;
  const dy = e.clientY - pointerStart.y;

  // Map pixel displacement to rotation (sensitivity tuned to small element)
  const rect = canvas.getBoundingClientRect();
  const rotY = THREE.MathUtils.clamp(dx / rect.width * 2, -1, 1) * MAX_TILT;
  const rotX = THREE.MathUtils.clamp(-dy / rect.height * 2, -1, 1) * MAX_TILT;

  mesh.rotation.x = rotX;
  mesh.rotation.y = rotY;
});
```

Snap-back in render loop:
```javascript
if (!isPointerDown) {
  mesh.rotation.x += (0 - mesh.rotation.x) * factor;
  mesh.rotation.y += (0 - mesh.rotation.y) * factor;
}
```

---

## Considerations

### Performance
- Single circle mesh, no post-processing — very lightweight
- `ResizeObserver` used instead of window resize event (element may resize with viewport without window resize firing)
- Render loop can run at reduced FPS (30) since animations are smooth lerps

### Header Visibility
- The dashboard header is hidden on `/settings`, `/card/editor`, `/card/case` via `hide_dashboard_chrome()`
- The avatar scene only needs to initialize when the header is visible
- On pages where header is hidden, the avatar scene won't render (container is `display: none`)

### Three.js Import Map
- The card editor and card wallet already inject the Three.js import map via `ui.add_head_html()`
- The avatar scene needs the same import map
- Must ensure the import map is only injected ONCE per page (multiple `<script type="importmap">` tags cause errors)
- Solution: `dashboard_header()` injects the import map; card editor/wallet pages check if already present

### Circular Clipping
- CSS `border-radius: 50%; overflow: hidden;` on the container clips the rectangular canvas to a circle
- This is simpler and more performant than alpha masking in the shader
- The `shadow-md` class on the container provides the drop shadow (same as current avatar)

---

## Verification

1. Navigate to `/profile/edit` — avatar shows as 3D circle with placeholder texture
2. Click and drag on avatar — tilts up to ±20° on both axes
3. Release mouse — avatar smoothly snaps back to flat
4. Click and hold (500ms) — file dialog opens
5. Select an image — instant preview on the 3D circle
6. Image pinned to IPFS, CID stored in DB
7. Navigate away and return — avatar shows the saved image
8. Public linktree (`/profile/{moniker}`) — shows avatar image (2D, unchanged)
9. Header hidden views (`/settings`, `/card/editor`) — no errors, scene not initialized
10. Resize browser — avatar scene adapts to new `8vw` dimensions
