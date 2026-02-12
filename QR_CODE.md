# QR_CODE.md — Personal QR Code View

## 1. Overview

A new dashboard view accessible from the bottom nav bar. Generates a stylized
QR code encoding the user's linktree URL (`/profile/{moniker-slug}`), with:

- **Embedded user avatar** in the center (from `avatar_cid`)
- **Color scheme** derived from the user's primary/secondary colors + dark/light mode
- **3D presentation** on a rounded-corner plane with emissive/unlit material
- **Drag-to-tilt** interaction (same behavior as the avatar mesh)
- **IPFS pinning** — generated QR image is pinned and CID stored in user record
- **Linktree JSON inclusion** — `qr_code_cid` field added to schema

---

## 2. Wireframe

```
┌──────────────────────────────────────────────────┐
│  (dashboard header — hidden, same as card views) │
├──────────────────────────────────────────────────┤
│                                                  │
│              ┌──────────────────┐                │
│              │  ╭──────────────╮│                │
│              │  │              ││                │
│              │  │   ▓▓▓▓▓▓▓   ││                │
│              │  │   ▓     ▓   ││                │
│              │  │   ▓ AVA ▓   ││  ← 3D plane    │
│              │  │   ▓     ▓   ││     with QR     │
│              │  │   ▓▓▓▓▓▓▓   ││     texture     │
│              │  │              ││                │
│              │  ╰──────────────╯│                │
│              └──────────────────┘                │
│                                                  │
│         drag to tilt (±30°, snaps back)          │
│                                                  │
├──────────────────────────────────────────────────┤
│  [badge]  [palette]  [collections]  [qr_code]   │
│                                       ↑ active   │
└──────────────────────────────────────────────────┘
```

---

## 3. Design Decisions

### 3a. QR Data

The QR encodes the user's public linktree URL:
```
https://{APP_HOST}/profile/{moniker-slug}
```

This is the same URL visitors see. If `linktree_override` is enabled, we still
encode the local URL (the override redirect happens server-side).

### 3b. Avatar Embed

The user's avatar image (`avatar_cid`) is embedded in the center of the QR code
using `qrcode`'s `embeded_image_path` parameter, same as the Stellar logo in the
payment QR. If no avatar is set, use `static/placeholder.png`.

The QR uses `ERROR_CORRECT_H` (highest redundancy) to remain scannable with
the center logo overlay.

### 3c. Color Scheme

QR foreground and background colors are derived from the user's selected color
scheme and mode (light/dark):

| QR Element | Color Source |
|------------|-------------|
| Foreground (modules) | `primary` (accent_color / dark_accent_color) |
| Background | `bg` (bg_color / dark_bg_color) |

These are converted from hex to RGB tuples for `SolidFillColorMask`.

### 3d. 3D Presentation

- **Geometry**: `PlaneGeometry` with rounded corners (custom `RoundedRectGeometry`
  or `ShapeGeometry` from a rounded rect path)
- **Material**: `MeshBasicMaterial` with `map` set to the QR texture
  - `MeshBasicMaterial` is unlit — no lighting calculations
  - Colors appear fully saturated, like a screen/print
  - No roughness/metalness needed
- **Camera**: `OrthographicCamera` (same as avatar — makes it look 2D when untilted)
- **Interaction**: Drag-to-tilt ±30° with exponential snap-back (same as avatar)
- **No upload**: Read-only view, no hold-to-upload
- **Transparent background**: `alpha: true`, `premultipliedAlpha: false`

### 3e. IPFS Storage

The generated QR image (PNG bytes) is pinned to IPFS via `replace_asset()`.
The CID is stored in `users.qr_code_cid`. On linktree changes that affect
the QR (moniker, colors, avatar, dark_mode), the QR is regenerated and
re-pinned.

### 3f. Linktree Schema Update

Add `qr_code_cid` to the schema v1 JSON:
```json
{
  "schema_version": 1,
  "qr_code_cid": "bafy...",
  ...
}
```

---

## 4. QR Generation — Server Side

### New function: `generate_user_qr()`

Location: `payments/stellar_pay.py` is payment-specific. Create a new module
or add to `ipfs_client.py` as a high-level operation.

**Recommended: new file `qr_gen.py`** at project root.

```python
import io
import os
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer
from qrcode.image.styles.colormasks import SolidFillColorMask
import config


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert '#8c52ff' to (140, 82, 255)."""
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def generate_user_qr(moniker: str, avatar_path: str,
                     fg_hex: str = '#8c52ff',
                     bg_hex: str = '#ffffff') -> bytes:
    """Generate a branded QR code encoding the user's linktree URL.

    Args:
        moniker: User display name (used to build URL slug).
        avatar_path: Filesystem path to avatar image for center embed.
        fg_hex: Foreground color (QR modules) as hex string.
        bg_hex: Background color as hex string.

    Returns:
        PNG image bytes.
    """
    slug = moniker.lower().replace(' ', '-')
    url = f"{config.APP_HOST}/profile/{slug}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=RoundedModuleDrawer(),
        color_mask=SolidFillColorMask(
            back_color=hex_to_rgb(bg_hex),
            front_color=hex_to_rgb(fg_hex),
        ),
        embeded_image_path=avatar_path,
    )

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()
```

### Avatar resolution for embed

The `embeded_image_path` parameter needs a filesystem path. For the avatar:

1. If `avatar_cid` exists → fetch from IPFS via `ipfs_cat(avatar_cid)`,
   write to a temp file, pass the temp path
2. If no avatar → use `static/placeholder.png`

```python
import tempfile
import ipfs_client

async def get_avatar_path(avatar_cid: str | None) -> str:
    """Return filesystem path to avatar image for QR embed."""
    if not avatar_cid:
        return os.path.join(os.path.dirname(__file__), 'static', 'placeholder.png')

    data = await ipfs_client.ipfs_cat(avatar_cid)
    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    tmp.write(data)
    tmp.close()
    return tmp.name
```

---

## 5. QR Regeneration Triggers

The QR must be regenerated when any of these change:

| Change | Where it happens |
|--------|-----------------|
| Avatar updated | `process_avatar_upload()` in `/profile/edit` |
| Color scheme changed | `_save_colors()` in `/settings` |
| Dark mode toggled | `_save_settings()` in `/settings` |
| Moniker changed | (future — moniker is currently immutable after signup) |

After regeneration:
1. `generate_user_qr(...)` → PNG bytes
2. `replace_asset(png_bytes, old_qr_cid, 'qr_code.png')` → new CID
3. `db.update_user(user_id, qr_code_cid=new_cid)`
4. `schedule_republish(user_id)` (linktree JSON now includes `qr_code_cid`)

### Helper function

```python
async def regenerate_qr(user_id: str):
    """Regenerate the user's QR code image and update IPFS + DB."""
    user = await db.get_user_by_id(user_id)
    colors = await db.get_profile_colors(user_id)
    settings = await db.get_profile_settings(user_id)

    dark = bool(settings.get('dark_mode', 0))
    fg = colors.get('dark_accent_color' if dark else 'accent_color', '#8c52ff')
    bg = colors.get('dark_bg_color' if dark else 'bg_color', '#ffffff')

    avatar_path = await get_avatar_path(user.get('avatar_cid'))

    try:
        png_bytes = generate_user_qr(user['moniker'], avatar_path, fg, bg)
        old_cid = user.get('qr_code_cid')
        new_cid = await ipfs_client.replace_asset(png_bytes, old_cid, 'qr_code.png')
        await db.update_user(user_id, qr_code_cid=new_cid)
    finally:
        # Clean up temp file if we created one
        if user.get('avatar_cid') and os.path.exists(avatar_path):
            os.unlink(avatar_path)
```

---

## 6. Database Migration

Add column to users table:

```python
# In db.py _MIGRATIONS list:
"ALTER TABLE users ADD COLUMN qr_code_cid TEXT",
```

---

## 7. Linktree Schema Update

In `ipfs_client.py` → `build_linktree_json()`, add:

```python
return {
    "schema_version": 1,
    ...
    "qr_code_cid": qr_code_cid,      # ← new field
    "override_url": override_url or "",
}
```

Update function signature to accept `qr_code_cid=None` parameter.
Update callers in `build_linktree_fresh()` and `republish_linktree()`:
```python
qr_code_cid=dict(user).get('qr_code_cid'),
```

---

## 8. Three.js — `static/js/qr_view.js`

### Scene Setup

```javascript
import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js';

// MutationObserver bootstrap (same pattern as avatar_scene.js)

function init(container, spacer) {

  // syncPosition() — same overlay pattern as avatar

  // Renderer — transparent, unlit
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    premultipliedAlpha: false,
  });

  // Orthographic camera (same as avatar)
  const camera = new THREE.OrthographicCamera(-1.1, 1.1, 1.1, -1.1, 0.1, 10);
  camera.position.set(0, 0, 3);

  // NO lighting needed — MeshBasicMaterial is unlit

  // Rounded rectangle geometry
  const shape = new THREE.Shape();
  const w = 1.0, h = 1.0, r = 0.08;  // square with rounded corners
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

  // MeshBasicMaterial — unlit, emissive appearance
  const material = new THREE.MeshBasicMaterial({
    color: 0xffffff,
    side: THREE.FrontSide,
  });

  const mesh = new THREE.Mesh(geometry, material);
  scene.add(mesh);

  // Load QR texture from data attribute
  const textureLoader = new THREE.TextureLoader();
  const qrUrl = container.dataset.qrUrl;
  if (qrUrl) {
    textureLoader.load(qrUrl, (tex) => {
      tex.colorSpace = THREE.SRGBColorSpace;
      material.map = tex;
      material.needsUpdate = true;
    });
  }

  // Drag-to-tilt — same as avatar_view.js (±30°, snap-back)
  // ... (identical pointer event handlers)

  // Render loop — same as avatar_view.js
}
```

### Key differences from avatar:
- **No lighting** — scene has no AmbientLight or DirectionalLight
- **MeshBasicMaterial** instead of MeshStandardMaterial (unlit, fully saturated)
- **ShapeGeometry** from rounded rect path instead of CircleGeometry
- **Square aspect ratio** — QR codes are always square
- **No upload capability** — read-only view

---

## 9. Route + Page Setup

### Nav bar update (`components.py`)

Add QR code entry to `dashboard_nav()`:

```python
items = [
    ('badge',       '/profile/edit', 'dashboard'),
    ('palette',     '/card/editor',  'card_editor'),
    ('collections', '/card/case',    'card_case'),
    ('qr_code',     '/qr',           'qr_code'),       # ← new
]
```

### Page handler (`main.py`)

```python
@ui.page('/qr')
async def qr_view():
    user_id, moniker, member_type = require_auth()
    if user_id is None:
        return

    user = await db.get_user_by_id(user_id)

    header = dashboard_header(moniker, member_type, user_id=user_id, ...)
    footer = dashboard_nav(active='qr_code')

    hide_dashboard_chrome(header, footer)

    # QR image URL (from IPFS or generate on-the-fly if missing)
    qr_cid = user.get('qr_code_cid') if user else None
    if qr_cid:
        qr_url = f'{config.KUBO_GATEWAY}/ipfs/{qr_cid}'
    else:
        # First visit — generate and pin QR
        await regenerate_qr(user_id)
        user = await db.get_user_by_id(user_id)
        qr_cid = user.get('qr_code_cid')
        qr_url = f'{config.KUBO_GATEWAY}/ipfs/{qr_cid}' if qr_cid else ''

    # 3D scene container
    ui.add_head_html('''
    <style>
      #qr-scene {
        position: fixed;
        top: 0; left: 0;
        width: 100vw; height: 100vh;
        z-index: 5000;
        pointer-events: auto;
      }
    </style>
    ''')

    _cache_v = int(time.time())
    ui.add_body_html(
        f'<div id="qr-scene" data-qr-url="{qr_url}"></div>'
        f'<script type="module" src="/static/js/qr_view.js?v={_cache_v}"></script>'
    )
```

---

## 10. File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `qr_gen.py` | **NEW** | `generate_user_qr()`, `get_avatar_path()`, `regenerate_qr()`, `hex_to_rgb()` |
| `static/js/qr_view.js` | **NEW** | 3D scene — rounded plane, unlit material, drag-to-tilt, QR texture |
| `db.py` | **MODIFY** | Add `qr_code_cid TEXT` migration |
| `ipfs_client.py` | **MODIFY** | Add `qr_code_cid` param to `build_linktree_json()` and callers |
| `components.py` | **MODIFY** | Add `qr_code` icon to `dashboard_nav()` |
| `main.py` | **MODIFY** | Add `/qr` route handler |

### Regeneration trigger points (modify existing handlers):

| File | Handler | Add call to |
|------|---------|-------------|
| `main.py` | `process_avatar_upload()` | `await regenerate_qr(user_id)` |
| `main.py` | color save handler in `/settings` | `await regenerate_qr(user_id)` |
| `main.py` | dark mode toggle in `/settings` | `await regenerate_qr(user_id)` |

---

## 11. Implementation Sequence

1. **`db.py`** — Add `qr_code_cid TEXT` migration
2. **`qr_gen.py`** — Create QR generation module
3. **`ipfs_client.py`** — Add `qr_code_cid` to linktree schema + callers
4. **`static/js/qr_view.js`** — Create 3D scene JS
5. **`components.py`** — Add nav bar icon
6. **`main.py`** — Add `/qr` route + regeneration triggers
7. **Test** — Generate QR, verify scan, verify 3D view, verify regeneration on avatar/color change

---

## 12. Peer QR Scanning

### Overview

A scan button in the upper-right corner of the `/qr` view opens the device
camera to scan another member's QR code. The scanned URL is parsed to identify
the peer, and they are automatically added to the scanner's peer card collection
(the card wallet at `/card/case`).

### Wireframe

```
┌──────────────────────────────────────────┐
│                              [📷 SCAN]   │  ← upper-right button
│                                          │
│           ┌──────────────┐               │
│           │   QR CODE    │               │
│           │   (3D mesh)  │               │
│           └──────────────┘               │
│                                          │
│  [badge] [palette] [collections] [qr]    │
└──────────────────────────────────────────┘

        ↓ tap SCAN button

┌──────────────────────────────────────────┐
│                              [✕ CLOSE]   │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │                                    │  │
│  │         CAMERA VIEWFINDER          │  │
│  │                                    │  │
│  │      ┌──────────────────┐          │  │
│  │      │   scan target    │          │  │
│  │      └──────────────────┘          │  │
│  │                                    │  │
│  └────────────────────────────────────┘  │
│                                          │
│  Point camera at a member's QR code      │
│                                          │
└──────────────────────────────────────────┘

        ↓ QR detected

┌──────────────────────────────────────────┐
│                                          │
│  ┌────────────────────────────────────┐  │
│  │  ✓ Peer added!                     │  │
│  │                                    │  │
│  │  [avatar]  MonkerName              │  │
│  │            COOP MEMBER             │  │
│  │                                    │  │
│  │  [ VIEW CARD ]  [ SCAN ANOTHER ]   │  │
│  └────────────────────────────────────┘  │
│                                          │
└──────────────────────────────────────────┘
```

### QR Data Format

Each member's QR encodes their profile URL path:

```
/profile/{moniker-slug}
```

The scanner extracts the `moniker-slug` from the URL and looks up the user
in the database via the same query used in `/profile/{moniker_slug}`:

```sql
SELECT id, moniker, member_type, avatar_cid, nfc_image_cid
FROM users
WHERE LOWER(REPLACE(moniker, ' ', '-')) = ?
```

### Client-Side: QR Scanner

**Library:** Use `html5-qrcode` (lightweight, no dependencies, works on
mobile and desktop). Load from CDN:

```html
<script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
```

**Scanner flow in `qr_view.js`:**

1. Scan button creates a `<div id="qr-reader">` overlay on top of the 3D scene
2. Initialize `Html5Qrcode` with the reader div
3. Start camera with `html5Qrcode.start()`
4. On successful decode:
   - Stop scanner
   - Parse the URL to extract moniker slug
   - POST to `/api/peer/add` with the slug
5. Show result overlay (success or error)
6. Close button returns to the 3D QR view

**URL parsing:** The scanned text could be:
- Relative path: `/profile/some-moniker`
- Full URL: `https://example.com/profile/some-moniker`

Extract the slug with:

```javascript
function extractMonikerSlug(scannedText) {
  const match = scannedText.match(/\/profile\/([a-z0-9-]+)/i);
  return match ? match[1].toLowerCase() : null;
}
```

### Server-Side: Peer Add API

**New FastAPI route in `main.py`:**

```python
@app.post('/api/peer/add')
async def api_add_peer(request: Request):
    """Add a peer by moniker slug. Called from QR scanner."""
    data = await request.json()
    slug = data.get('slug', '').strip().lower()

    # Authenticate
    user_id = request.session.get('user_id')  # or from app.storage
    if not user_id:
        raise HTTPException(status_code=401, detail='Not authenticated')

    # Look up peer
    peer = await db.get_user_by_moniker_slug(slug)
    if not peer:
        raise HTTPException(status_code=404, detail='Member not found')

    peer_id = peer['id']

    # Prevent self-peering
    if peer_id == user_id:
        raise HTTPException(status_code=400, detail='Cannot add yourself')

    # Add peer (INSERT OR IGNORE handles duplicates)
    await db.add_peer_card(user_id, peer_id)

    return {
        'status': 'ok',
        'peer': {
            'moniker': peer['moniker'],
            'member_type': peer['member_type'],
            'avatar_cid': peer.get('avatar_cid'),
        },
    }
```

### Database: New Query

Add `get_user_by_moniker_slug()` to `db.py`:

```python
async def get_user_by_moniker_slug(slug: str):
    """Look up user by URL-style moniker slug (lowercase, hyphens)."""
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM users WHERE LOWER(REPLACE(moniker, ' ', '-')) = ?",
            (slug,),
        )
        return await cursor.fetchone()
```

### NiceGUI + FastAPI Session Bridge

NiceGUI uses `app.storage.user` (cookie-based), not FastAPI's session
middleware. The `/api/peer/add` route is a raw FastAPI endpoint that won't
have access to `app.storage.user`. Two approaches:

**Option A — NiceGUI bridge (recommended):** Instead of a raw API route,
use a hidden NiceGUI button + `ui.run_javascript()` to call back from JS
to Python. This is the same pattern used for avatar and card uploads:

```javascript
// JS: after successful QR decode
window.__scannedPeerSlug = slug;
document.getElementById('peer-scan-trigger').click();
```

```python
# Python: hidden button handler
async def process_scanned_peer():
    slug = await ui.run_javascript('return window.__scannedPeerSlug')
    peer = await db.get_user_by_moniker_slug(slug)
    if not peer:
        ui.notify('Member not found', type='warning')
        return
    if peer['id'] == user_id:
        ui.notify('That\'s your own QR code!', type='info')
        return
    await db.add_peer_card(user_id, peer['id'])
    ui.notify(f'Added {peer["moniker"]} to your card wallet!', type='positive')

ui.button(on_click=process_scanned_peer).props(
    'id=peer-scan-trigger').style('position:absolute;left:-9999px;')
```

**Option B — FastAPI API route:** Add a raw `/api/peer/add` endpoint and
extract `user_id` from NiceGUI's storage cookie. More complex, less
consistent with existing patterns.

**Recommendation:** Option A — matches the avatar/card upload bridge pattern.

### File Changes

| File | Action | Description |
|------|--------|-------------|
| `static/js/qr_view.js` | **MODIFY** | Add scan button, html5-qrcode scanner overlay, URL parsing, trigger hidden button |
| `main.py` | **MODIFY** | Add hidden peer-scan-trigger button + handler on `/qr` route |
| `db.py` | **MODIFY** | Add `get_user_by_moniker_slug()` query |
| `/qr` page | **MODIFY** | Load `html5-qrcode` CDN script via `ui.add_head_html()` |

### Implementation Sequence

1. **`db.py`** — Add `get_user_by_moniker_slug()`
2. **`main.py`** — Add `html5-qrcode` CDN script + hidden trigger button + handler on `/qr`
3. **`static/js/qr_view.js`** — Add scan button UI, scanner overlay, decode handler, trigger bridge
4. **Test** — Scan QR from another device, verify peer appears in `/card/case`

### Edge Cases

| Scenario | Handling |
|----------|---------|
| Self-scan | Show "That's your own QR code!" info toast |
| Already a peer | `INSERT OR IGNORE` — no error, show "Already in your wallet" |
| Invalid QR (not a profile URL) | Show "Not a valid member QR code" warning |
| Camera permission denied | Show error message, scanner stays closed |
| No camera available (desktop) | Button still works — `html5-qrcode` shows file upload fallback |
| Member not found in DB | Show "Member not found" warning |
