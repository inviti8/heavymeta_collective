# CARD_WALLET.md — 3D Card Wallet Prototype

## Overview

Replace the current static HTML card-case placeholder (`/card/case`) with a 3D card wallet using standalone Three.js — the same approach as `/card/editor`. Cards are dual-plane meshes (front + back `PlaneGeometry`), matching the card editor's construction. This is a **feel-and-interaction prototype** — visual polish comes later.

---

## Interaction Design

### Vertical Carousel

Cards are arranged in a **vertical ascending stack**. The center card sits closest to the camera; cards above and below recede in depth and scale.

```
     ┌───────┐  ← far, small, dimmed
    ┌─────────┐
   ┌───────────┐  ← CENTER (closest, full size)
    └─────────┘
     └───────┘  ← far, small, dimmed
```

- **Scroll wheel / vertical drag** cycles the carousel (shifts which card is centered)
- Cards animate smoothly between positions (ease-in-out)
- The carousel wraps — scrolling past the last card returns to the first

### Card States

| State | Trigger | Behavior |
|-------|---------|----------|
| **Stack** (default) | — | All cards in vertical carousel positions |
| **Selected** | Click the center card | Center card animates forward toward camera; can be rotated on X-axis by dragging vertically |
| **Deselected** | Click outside the card | Card returns to its carousel position |
| **Open linktree** | Click-and-hold selected card (500ms) | Opens the peer's linktree URL in a new browser tab |

### Selected State Details

- Card moves forward (z increases) and other cards fade/recede
- User can **rotate the card on the X-axis** by vertical drag (to see front/back)
- Horizontal rotation is locked (no Y-axis orbit)
- Clicking anywhere outside the card returns it to the stack

### Click-and-Hold → Open Linktree

Same hold pattern as card editor (500ms threshold, 3px move cancels):
- On hold completion, open `/{peer_moniker}` (the peer's public linktree) in a new tab
- Visual feedback: subtle scale pulse at hold start

---

## Data Model

### New DB Table: `peer_cards`

Tracks which cards a user has collected from other members.

```sql
CREATE TABLE IF NOT EXISTS peer_cards (
    id          TEXT PRIMARY KEY,
    owner_id    TEXT REFERENCES users(id),   -- the collector
    peer_id     TEXT REFERENCES users(id),   -- the card owner
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(owner_id, peer_id)                -- one card per peer
);
```

### DB Functions (db.py)

```python
async def add_peer_card(owner_id, peer_id) -> str
async def remove_peer_card(owner_id, peer_id)
async def get_peer_cards(owner_id) -> list[Row]  # returns peer user rows with card data
```

`get_peer_cards` joins `peer_cards` → `users` to return each peer's:
- `moniker`
- `nfc_image_cid` (front texture)
- `nfc_back_image_cid` (back texture)
- `ipns_name` (for linktree URL)
- `member_type`

### Dummy Peer Data (Seed Script)

Create a seed function `seed_dummy_peers(owner_moniker='tester0')` that:

1. Creates 5 dummy users in the `users` table (if not existing):
   - `peer_alpha`, `peer_bravo`, `peer_charlie`, `peer_delta`, `peer_echo`
   - Each with `member_type='coop'`, placeholder passwords, no real stellar addresses
   - Each with `nfc_image_cid` and `nfc_back_image_cid` pointing to colored placeholder textures

2. Generates simple colored card textures (solid color planes with moniker text):
   - Uses Python `PIL`/`Pillow` to create 856x540 PNG images (card ratio)
   - Each peer gets a unique color scheme
   - Pins to IPFS via `ipfs_add()`, stores CIDs on the dummy user rows

3. Adds `peer_cards` entries linking `tester0` → each dummy peer

4. Triggered via CLI: `uv run python -m seed_peers` (standalone script)

### Peer Color Schemes (for dummy textures)

| Peer | Front Color | Back Color | Text |
|------|------------|------------|------|
| peer_alpha | `#e74c3c` | `#c0392b` | white |
| peer_bravo | `#3498db` | `#2980b9` | white |
| peer_charlie | `#2ecc71` | `#27ae60` | white |
| peer_delta | `#f39c12` | `#e67e22` | black |
| peer_echo | `#9b59b6` | `#8e44ad` | white |

---

## Page Structure: `/card/case`

### Python Side (main.py)

```python
@ui.page('/card/case')
async def card_case():
    require_auth()
    user_id = app.storage.user.get('user_id')

    # Load peer cards from DB
    peers = await db.get_peer_cards(user_id)

    # Build peer data list for JS
    peer_data = []
    for p in peers:
        peer_data.append({
            'moniker': p['moniker'],
            'front_url': f'{KUBO_GATEWAY}/ipfs/{p["nfc_image_cid"]}' if p['nfc_image_cid'] else '',
            'back_url': f'{KUBO_GATEWAY}/ipfs/{p["nfc_back_image_cid"]}' if p['nfc_back_image_cid'] else '',
            'linktree_url': f'/profile/{p["moniker"].lower().replace(" ", "-")}',
        })

    # Header hidden, footer visible
    header = dashboard_header(...)
    hide_dashboard_chrome(header)

    # Three.js import map + full-viewport CSS (same as card editor)
    ui.add_head_html(...)

    # Pass peer data as JSON in a data attribute
    ui.add_body_html(f'''
    <div id="card-scene" data-peers='{json.dumps(peer_data)}'></div>
    <script type="module" src="/static/js/card_wallet.js?v={cache_v}"></script>
    ''')

    dashboard_nav(active='card_case')
```

### JavaScript Side: `static/js/card_wallet.js`

New standalone module — does NOT share code with `card_scene.js` (they're separate pages).

#### Module Structure

```
card_wallet.js
├── Scene setup (renderer, camera, lights)
├── Card creation (dual-plane per peer)
├── Carousel layout engine
│   ├── positionCards(centerIndex) — compute Y, Z, scale, opacity per slot
│   └── animateToPositions() — GSAP or manual lerp
├── Input handling
│   ├── Wheel / touch-drag → cycle carousel
│   ├── Click center card → select
│   ├── Click outside → deselect
│   ├── Drag selected card → rotate X-axis
│   └── Hold selected card → open linktree
└── Render loop
```

#### Scene Setup

```javascript
import * as THREE from 'three';

const container = document.getElementById('card-scene');
const peers = JSON.parse(container.dataset.peers);

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, w/h, 0.1, 100);
camera.position.set(0, 0, 8);

// Lighting — same as card editor
scene.add(new THREE.AmbientLight(0xffffff, 0.6));
const dir = new THREE.DirectionalLight(0xffffff, 0.8);
dir.position.set(5, 5, 5);
scene.add(dir);
```

#### Card Construction (Per Peer)

Each card = `THREE.Group` with two `PlaneGeometry` children, identical to card editor:

```javascript
function createCard(peer) {
    const group = new THREE.Group();
    group.userData = { peer };

    const geo = new THREE.PlaneGeometry(3.2, 2.0);

    // Front plane
    const frontMat = new THREE.MeshStandardMaterial({
        color: 0x333333, roughness: 0.4, metalness: 0.1
    });
    const front = new THREE.Mesh(geo, frontMat);
    front.name = 'front';
    group.add(front);

    // Back plane (rotated 180° Y)
    const backMat = new THREE.MeshStandardMaterial({
        color: 0x333333, roughness: 0.4, metalness: 0.1
    });
    const back = new THREE.Mesh(geo, backMat);
    back.rotation.y = Math.PI;
    back.name = 'back';
    group.add(back);

    // Load textures
    if (peer.front_url) loadTexture(frontMat, peer.front_url);
    if (peer.back_url) loadTexture(backMat, peer.back_url);

    return group;
}
```

#### Carousel Layout

Cards positioned along the Y-axis. The `centerIndex` determines which card is centered.

```javascript
const CARD_SPACING = 2.2;  // vertical gap between cards
const DEPTH_FALLOFF = 1.5; // how much non-center cards recede in Z
const SCALE_FALLOFF = 0.15; // scale reduction per slot from center
const VISIBLE_CARDS = 5;   // max cards rendered above + below center

function getCardTransform(slotOffset) {
    // slotOffset: 0 = center, ±1 = adjacent, ±2 = two away, etc.
    return {
        y: slotOffset * CARD_SPACING,
        z: -Math.abs(slotOffset) * DEPTH_FALLOFF,
        scale: Math.max(0.5, 1.0 - Math.abs(slotOffset) * SCALE_FALLOFF),
        opacity: Math.max(0.2, 1.0 - Math.abs(slotOffset) * 0.3),
    };
}
```

#### Input: Scroll / Drag to Cycle

```javascript
// Mouse wheel
container.addEventListener('wheel', (e) => {
    if (selectedCard) return; // don't scroll while card is selected
    e.preventDefault();
    if (e.deltaY > 0) centerIndex = (centerIndex + 1) % cards.length;
    else centerIndex = (centerIndex - 1 + cards.length) % cards.length;
    animateToPositions();
}, { passive: false });

// Touch drag (vertical)
let touchStartY = 0;
container.addEventListener('touchstart', (e) => {
    touchStartY = e.touches[0].clientY;
});
container.addEventListener('touchend', (e) => {
    const dy = e.changedTouches[0].clientY - touchStartY;
    if (Math.abs(dy) > 30) {
        centerIndex = dy < 0
            ? (centerIndex + 1) % cards.length
            : (centerIndex - 1 + cards.length) % cards.length;
        animateToPositions();
    }
});
```

#### Input: Select / Deselect

```javascript
let selectedCard = null;

canvas.addEventListener('click', (e) => {
    if (selectedCard) {
        // Click outside check via raycaster
        const hit = raycast(e);
        if (!hit || hit.object.parent !== selectedCard) {
            deselectCard();
        }
        return;
    }
    // Click on center card → select
    const hit = raycast(e);
    if (hit && hit.object.parent === cards[centerIndex]) {
        selectCard(cards[centerIndex]);
    }
});

function selectCard(card) {
    selectedCard = card;
    // Animate card forward
    animateTo(card, { z: 3 });
    // Dim other cards
    cards.forEach(c => { if (c !== card) fadeCard(c, 0.15); });
}

function deselectCard() {
    fadeAllCards(1.0);
    animateToPositions();
    selectedCard = null;
}
```

#### Input: Rotate Selected Card (X-axis)

When a card is selected, vertical drag rotates it around the X-axis (to see front/back).

```javascript
let isDragging = false;
let dragStartY = 0;
let cardStartRotX = 0;

canvas.addEventListener('pointerdown', (e) => {
    if (!selectedCard) return;
    const hit = raycast(e);
    if (hit && hit.object.parent === selectedCard) {
        isDragging = true;
        dragStartY = e.clientY;
        cardStartRotX = selectedCard.rotation.x;
    }
});

canvas.addEventListener('pointermove', (e) => {
    if (!isDragging) return;
    const dy = e.clientY - dragStartY;
    selectedCard.rotation.x = cardStartRotX + dy * 0.01;
});

canvas.addEventListener('pointerup', () => {
    isDragging = false;
});
```

#### Input: Hold Selected Card → Open Linktree

```javascript
let holdTimer = null;
const HOLD_MS = 500;

canvas.addEventListener('pointerdown', (e) => {
    if (!selectedCard) return;
    const hit = raycast(e);
    if (hit && hit.object.parent === selectedCard) {
        holdTimer = setTimeout(() => {
            const url = selectedCard.userData.peer.linktree_url;
            window.open(url, '_blank');
            holdTimer = null;
        }, HOLD_MS);
    }
});

// Cancel on move or up (same pattern as card editor)
```

---

## Animation

Use manual lerp in the render loop (no GSAP dependency for prototype):

```javascript
// Each card has a .targetPosition, .targetScale, .targetOpacity
function updateAnimations(dt) {
    const speed = 8.0; // lerp speed
    cards.forEach(card => {
        card.position.lerp(card.targetPosition, speed * dt);
        card.scale.lerp(card.targetScale, speed * dt);
        // opacity via material
        card.children.forEach(mesh => {
            mesh.material.opacity += (card.targetOpacity - mesh.material.opacity) * speed * dt;
        });
    });
}
```

This avoids an external dependency and keeps the prototype simple. GSAP can be swapped in for production polish later.

---

## Files to Create / Modify

| File | Action | Description |
|------|--------|-------------|
| `db.py` | MODIFY | Add `peer_cards` table to SCHEMA, migration, `add_peer_card()`, `remove_peer_card()`, `get_peer_cards()` |
| `seed_peers.py` | **NEW** | CLI script: creates 5 dummy peers, generates card textures, pins to IPFS, links to tester0 |
| `static/js/card_wallet.js` | **NEW** | Standalone Three.js card wallet scene |
| `main.py` | MODIFY | Replace `/card/case` placeholder with Three.js wallet (same pattern as `/card/editor`) |

---

## Implementation Steps

### Step 1: DB Schema + Functions

- Add `peer_cards` table to `SCHEMA` in `db.py`
- Add migration `ALTER TABLE` (for existing DBs — though CREATE IF NOT EXISTS covers it)
- Add `add_peer_card(owner_id, peer_id)`
- Add `remove_peer_card(owner_id, peer_id)`
- Add `get_peer_cards(owner_id)` — joins `peer_cards` → `users` to return peer profile data

### Step 2: Seed Script (`seed_peers.py`)

- Create 5 dummy user rows (skip if moniker already exists)
- Generate 856x540 solid-color PNG card images with moniker text overlay (Pillow)
- Pin each image to IPFS via `ipfs_add()`
- Update dummy user rows with CIDs
- Create `peer_cards` entries linking tester0 → each dummy peer
- Run: `uv run python seed_peers.py`

### Step 3: Card Wallet JS (`static/js/card_wallet.js`)

- Scene, camera, renderer, lights (same setup as card_scene.js)
- `createCard(peer)` — dual-plane construction
- Carousel layout: `positionCards()`, `animateToPositions()`
- Scroll/drag input → cycle `centerIndex`
- Click center → select (forward + dim others)
- Click outside → deselect
- Drag selected → X-axis rotation
- Hold selected → open linktree in new tab
- Render loop with lerp-based animations
- Transparent background (composites over NiceGUI footer)

### Step 4: Wire Up `/card/case` Page

- Load peer data from DB
- Serialize as JSON into `data-peers` attribute
- Inject Three.js import map + CSS (same as card editor)
- Add `#card-scene` div + `card_wallet.js` script tag
- Keep `dashboard_nav(active='card_case')` footer

---

## Verification

1. `uv run python seed_peers.py` — seeds DB + IPFS without errors
2. Navigate to `/card/case` — 5 cards visible in vertical carousel
3. Scroll wheel cycles through cards smoothly
4. Touch-drag (mobile) cycles carousel
5. Click center card → card moves forward, others dim
6. Drag vertically on selected card → rotates on X-axis (shows front/back)
7. Click outside selected card → returns to stack
8. Click-and-hold selected card (500ms) → peer's linktree opens in new tab
9. Footer nav remains visible and functional
10. No console errors; transparent background composites correctly

---

## Future Enhancements (Not This Prototype)

- NFC tap to collect real peer cards
- Remove card from wallet
- Card sorting / favorites
- GLTF card model with PBR materials (clearcoat, metalness)
- Holographic / iridescent shader effects
- GSAP-powered spring animations
- Card details overlay (peer stats, mutual connections)
