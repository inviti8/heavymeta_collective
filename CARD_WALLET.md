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

## Phase 2: Empty State, QR Scan & Manual Add

### Overview

Three changes to the card wallet:

1. **Remove empty-state text** — when the wallet has no cards, show only the empty 3D viewport (dark background, footer nav). No "No cards collected yet" text.
2. **Move QR scan into the card wallet** — the scan button currently lives in `/qr` (qr_view.js). Move it into `/card/case` so users can scan peer QR codes directly from the wallet. Remove the scan button and scanner overlay from qr_view.js (the QR view becomes display-only for your own QR code).
3. **Add manual peer input** — a `+` button that opens a NiceGUI dialog with a text input for entering a moniker slug manually (for when QR scanning isn't available).

### UI Layout

Two floating action buttons in the card wallet viewport:

```
┌──────────────────────────────────┐
│                                  │
│     (3D card carousel or         │
│      empty dark viewport)        │
│                                  │
│                      [scan] [+]  │  ← fixed, bottom-right, above footer
│──────────────────────────────────│
│  badge  palette  cards  qr_code  │  ← footer nav
└──────────────────────────────────┘
```

- **Scan button**: `qr_code_scanner` material icon, same style as current (circular, translucent backdrop)
- **+ button**: `person_add` material icon, matching style
- Both positioned `fixed`, bottom-right, above the footer (z-index above card-scene but below scanner overlay)

### Changes by File

#### `card_wallet.js`

**Remove empty-state text (line 10-12):**
```javascript
// DELETE this block:
if (peers.length === 0) {
  container.innerHTML = '<p style="...">No cards collected yet.</p>';
}
```

**Add scan button + scanner overlay:**
Move the entire QR scanner section from `qr_view.js` into `card_wallet.js`:
- `scanBtn` creation and styling
- `overlay` creation (camera viewfinder UI)
- `loadQrScannerLib()`, `openScanner()`, `stopScanner()`, `closeScanner()`
- `onScanSuccess()` with NiceGUI bridge trigger (`peer-scan-trigger`)
- `retryBtn` for "SCAN ANOTHER" flow
- `extractMonikerSlug()` helper

Adjust scan button position so it sits above the footer nav (~`bottom: 80px; right: 16px`).

After successful scan + "ok" result, instead of showing "VIEW CARDS" link, dynamically add the new card to the 3D scene:
```javascript
// On successful peer add, fetch new peer data and insert card
if (result === 'ok') {
  // Python handler sets window.__newPeerData with {moniker, front_url, back_url, linktree_url}
  const newPeer = window.__newPeerData;
  if (newPeer) {
    const card = createCard(newPeer);
    cards.push(card);
    animateToPositions();
  }
}
```

**Add `+` (manual add) button:**
Create a second floating button next to the scan button. On click, dispatch a custom event or trigger a hidden NiceGUI button that opens the dialog (same bridge pattern as scan).

```javascript
const addBtn = document.createElement('button');
addBtn.innerHTML = '<span class="material-icons" style="font-size:24px;">person_add</span>';
addBtn.style.cssText = `
  position: fixed; bottom: 80px; right: 72px; z-index: 6000;
  width: 48px; height: 48px; border-radius: 50%;
  background: rgba(255,255,255,0.15); border: none; cursor: pointer;
  color: white; display: flex; align-items: center; justify-content: center;
  backdrop-filter: blur(4px);
`;
document.body.appendChild(addBtn);

addBtn.addEventListener('click', () => {
  document.getElementById('manual-add-trigger').click();
});
```

#### `qr_view.js`

**Remove scanner section entirely:**
- Delete `scanBtn`, `overlay`, `loadQrScannerLib`, `openScanner`, `stopScanner`, `closeScanner`, `onScanSuccess`, `retryBtn`, `extractMonikerSlug`
- The QR view becomes a simple 3D display of the user's own QR code with tilt interaction and hold-to-download

#### `main.py` — `/card/case` route

**Add peer-scan bridge** (move from `/qr` route):
```python
# Peer scan bridge (hidden trigger)
async def process_scanned_peer():
    # ... same logic as current /qr route ...
    # On success, also set __newPeerData for JS to pick up
    peer_data = {
        'moniker': peer['moniker'],
        'front_url': f'{config.KUBO_GATEWAY}/ipfs/{peer["nfc_image_cid"]}' if peer.get('nfc_image_cid') else '',
        'back_url': f'{config.KUBO_GATEWAY}/ipfs/{peer["nfc_back_image_cid"]}' if peer.get('nfc_back_image_cid') else '',
        'linktree_url': f'/profile/{peer_moniker_slug}',
    }
    await ui.run_javascript(
        f'window.__newPeerData = {json.dumps(peer_data)};'
    )

ui.button(on_click=process_scanned_peer).props(
    'id=peer-scan-trigger').style('position:absolute;left:-9999px;')
```

**Add manual-add bridge:**
```python
async def open_manual_add_dialog():
    with ui.dialog() as dlg, ui.card().classes('p-6 gap-4'):
        ui.label('Add a peer').classes('text-lg font-semibold')
        slug_input = ui.input(placeholder='Enter moniker (e.g. jane-doe)').props(
            'outlined dense'
        ).classes('w-full')

        async def do_add():
            slug = slug_input.value.strip().lower().replace(' ', '-')
            if not slug:
                ui.notify('Enter a moniker', type='warning')
                return
            peer = await db.get_user_by_moniker_slug(slug)
            if not peer:
                ui.notify('Member not found', type='warning')
                return
            if peer['id'] == user_id:
                ui.notify("That's you!", type='info')
                return
            await db.add_peer_card(user_id, peer['id'])
            ui.notify(f'Added {peer["moniker"]} to your wallet!', type='positive')
            # Pass new peer data to JS for live card insert
            peer_moniker_slug = peer['moniker'].lower().replace(' ', '-')
            peer_data = {
                'moniker': peer['moniker'],
                'front_url': (f'{config.KUBO_GATEWAY}/ipfs/{peer["nfc_image_cid"]}'
                              if peer.get('nfc_image_cid') else ''),
                'back_url': (f'{config.KUBO_GATEWAY}/ipfs/{peer["nfc_back_image_cid"]}'
                              if peer.get('nfc_back_image_cid') else ''),
                'linktree_url': f'/profile/{peer_moniker_slug}',
            }
            await ui.run_javascript(
                f'window.__newPeerData = {json.dumps(peer_data)};'
                f'window.addPeerCard && window.addPeerCard();'
            )
            dlg.close()

        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Cancel', on_click=dlg.close).props('flat')
            ui.button('Add', on_click=do_add)
    dlg.open()

ui.button(on_click=open_manual_add_dialog).props(
    'id=manual-add-trigger').style('position:absolute;left:-9999px;')
```

#### `main.py` — `/qr` route

**Remove scan bridge:**
- Delete `process_scanned_peer()` function
- Delete `peer-scan-trigger` hidden button
- The `/qr` route only needs the QR display scene and `dashboard_nav(active='qr_code')`

### Implementation Steps

1. **`card_wallet.js`** — Remove empty-state text; add scan button, scanner overlay, and `+` button; add `window.addPeerCard()` function for live card insertion
2. **`qr_view.js`** — Strip out all scanner code (scan button, overlay, bridge interaction, retry button)
3. **`main.py` `/card/case`** — Add `process_scanned_peer` bridge (moved from `/qr`), add `open_manual_add_dialog` bridge
4. **`main.py` `/qr`** — Remove `process_scanned_peer` bridge and hidden trigger button

### Verification

1. Navigate to `/card/case` with no peers — empty dark viewport, no text, scan + add buttons visible
2. Click scan button — camera overlay opens, scans peer QR → card appears in wallet
3. Click `+` button — dialog opens, enter moniker slug → card appears in wallet
4. Navigate to `/qr` — no scan button visible, just QR display with tilt + hold-to-download
5. New cards animate into the carousel immediately (no page reload needed)

---

## Phase 3: Multi-Card Support & Card Checkout

### Overview

Members can design and order multiple physical NFC cards. The card editor becomes a design → checkout flow: customize both faces, then finalize via a shopping-cart button. Tier entitlements grant the first card(s) free; additional cards go through a payment dialog (variant of the join-flow dialog). After payment (or entitlement skip), a shipping address form collects delivery details.

### Design Principles

- **Every card goes through checkout** — even entitled (free) cards need shipping info
- **Entitlements skip payment, not checkout** — the cart button always opens the checkout flow; payment is conditionally skipped
- **Card images are draft until ordered** — the editor writes to a draft `user_cards` row; only finalized cards appear in the card wallet and are shared with peers
- **The user's "active card"** is their most recently ordered card (used for peer_cards display)

---

### Schema Changes

#### `tiers.json` — Add `cards_included` and `card_price_usd`

Each tier gains a `cards_included` field (number of NFC cards included with membership) and a flat `card_price_usd` for additional cards:

```json
[
  {
    "index": 0, "key": "free", "label": "FREE",
    "badge": "FREE MEMBER",
    "description": "Linktree only",
    "join_usd": 0, "annual_usd": 0,
    "cards_included": 0, "card_price_usd": 19.99,
    "image": "/static/tier0.png"
  },
  {
    "index": 1, "key": "spark", "label": "SPARK",
    "badge": "SPARK MEMBER",
    "description": "QR cards, basic access",
    "join_usd": 29.99, "annual_usd": 49.99,
    "cards_included": 1, "card_price_usd": 14.99,
    "image": "/static/tier1.png"
  },
  {
    "index": 3, "key": "forge", "label": "FORGE",
    "badge": "FORGE MEMBER",
    "description": "NFC cards, Pintheon node, full access",
    "join_usd": 59.99, "annual_usd": 99.99,
    "cards_included": 1, "card_price_usd": 14.99,
    "image": "/static/tier3.png"
  },
  {
    "index": 4, "key": "founding_forge", "label": "FOUNDING FORGE",
    "badge": "FOUNDING FORGE",
    "description": "Limited to 100 — governance vote, unlimited invites",
    "join_usd": 79.99, "annual_usd": 49.99,
    "cards_included": 2, "card_price_usd": 9.99,
    "image": "/static/tier4.png"
  },
  {
    "index": 5, "key": "anvil", "label": "ANVIL",
    "badge": "ANVIL MEMBER",
    "description": "Advisory board access",
    "join_usd": 149.99, "annual_usd": 249.99,
    "cards_included": 3, "card_price_usd": 9.99,
    "image": "/static/tier5.png"
  }
]
```

#### New DB Table: `user_cards`

Replaces the single `nfc_image_cid` / `nfc_back_image_cid` columns on `users`. Each row is one card design.

```sql
CREATE TABLE IF NOT EXISTS user_cards (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id),
    front_image_cid TEXT,
    back_image_cid  TEXT,
    status          TEXT DEFAULT 'draft',   -- draft | ordered | shipped | delivered
    is_active       INTEGER DEFAULT 0,      -- 1 = this card is shown to peers
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

- `draft` — being edited, not yet ordered
- `ordered` — checkout complete, awaiting fulfillment
- `shipped` / `delivered` — future statuses for tracking
- `is_active` — exactly one card per user is active (shown in card wallet / peer exchanges). Set when order completes.

#### New DB Table: `card_orders`

Tracks payment + shipping for each card checkout.

```sql
CREATE TABLE IF NOT EXISTS card_orders (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL REFERENCES users(id),
    card_id          TEXT NOT NULL REFERENCES user_cards(id),
    payment_method   TEXT,           -- 'entitlement' | 'card' | 'xlm'
    payment_status   TEXT DEFAULT 'pending',  -- pending | paid | failed
    tx_hash          TEXT,
    amount_usd       REAL,
    shipping_name    TEXT,
    shipping_street  TEXT,
    shipping_city    TEXT,
    shipping_state   TEXT,
    shipping_zip     TEXT,
    shipping_country TEXT,
    order_status     TEXT DEFAULT 'pending',  -- pending | processing | shipped | delivered
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### Migration: Existing User Cards

Migrate existing `nfc_image_cid` / `nfc_back_image_cid` from the `users` table into `user_cards` rows:

```python
# In db.init_db() migrations
"""
INSERT INTO user_cards (id, user_id, front_image_cid, back_image_cid, status, is_active)
SELECT hex(randomblob(16)), id, nfc_image_cid, nfc_back_image_cid, 'ordered', 1
FROM users
WHERE nfc_image_cid IS NOT NULL
AND NOT EXISTS (SELECT 1 FROM user_cards WHERE user_id = users.id)
"""
```

The legacy columns remain on `users` for backward compat but are no longer written to by the card editor.

#### DB Functions (db.py)

```python
async def create_user_card(user_id) -> str
    """Create a new draft card. Returns card_id."""

async def get_draft_card(user_id) -> Row | None
    """Get the user's current draft card (status='draft'), or None."""

async def get_user_cards(user_id, status=None) -> list[Row]
    """All cards for a user, optionally filtered by status."""

async def get_active_card(user_id) -> Row | None
    """The card with is_active=1."""

async def update_card_images(card_id, front_cid=None, back_cid=None)
    """Update front/back CIDs on a card."""

async def set_active_card(user_id, card_id)
    """Set is_active=1 on card_id, 0 on all others for this user."""

async def count_ordered_cards(user_id) -> int
    """Count cards with status != 'draft' for entitlement math."""

async def create_card_order(card_id, user_id, payment_method, amount_usd,
                            shipping_name, shipping_street, shipping_city,
                            shipping_state, shipping_zip, shipping_country) -> str
    """Create a card_order row. Returns order_id."""

async def finalize_card_order(order_id, tx_hash=None)
    """Set payment_status='paid', card status='ordered', card is_active=1."""
```

---

### Card Editor Changes (`main.py` — `/card/editor`)

#### Draft Card Loading

On page load, find or create a draft card:

```python
draft = await db.get_draft_card(user_id)
if not draft:
    card_id = await db.create_user_card(user_id)
    draft = await db.get_user_card(card_id)
else:
    card_id = draft['id']

existing_front_cid = draft['front_image_cid']
existing_back_cid = draft['back_image_cid']
```

#### Image Upload Target

`process_upload()` writes to `user_cards` instead of `users`:

```python
# Before: await db.update_user(user_id, **{cid_column: new_cid})
# After:
if face == 'front':
    await db.update_card_images(card_id, front_cid=new_cid)
else:
    await db.update_card_images(card_id, back_cid=new_cid)
```

#### Shopping Cart Button

A floating cart button in the top-right corner of the 3D viewport (same z-index layer as the scan/add buttons in card_wallet.js):

```javascript
// In card_scene.js
const cartBtn = document.createElement('button');
cartBtn.innerHTML = '<span class="material-icons" style="font-size:28px;">shopping_cart</span>';
cartBtn.style.cssText = `
  position: fixed; top: 16px; right: 16px; z-index: 6000;
  width: 52px; height: 52px; border-radius: 50%;
  background: rgba(140, 82, 255, 0.85); border: none; cursor: pointer;
  color: white; display: flex; align-items: center; justify-content: center;
  backdrop-filter: blur(4px); box-shadow: 0 2px 8px rgba(0,0,0,0.3);
`;
document.body.appendChild(cartBtn);

cartBtn.addEventListener('click', () => {
    document.getElementById('card-checkout-trigger').click();
});
```

Python-side hidden trigger in `/card/editor`:

```python
async def start_checkout():
    # 1. Check both sides have images
    draft = await db.get_draft_card(user_id)
    if not draft or not draft['front_image_cid'] or not draft['back_image_cid']:
        ui.notify('Please add images to both sides of the card.', type='warning')
        return

    # 2. Check entitlement
    tier_data = TIERS.get(member_type, TIERS['free'])
    cards_included = tier_data.get('cards_included', 0)
    cards_ordered = await db.count_ordered_cards(user_id)
    entitled = cards_ordered < cards_included

    if entitled:
        # Skip payment → go straight to shipping
        _open_shipping_dialog(draft['id'], payment_method='entitlement', amount_usd=0)
    else:
        # Open payment dialog
        card_price = tier_data.get('card_price_usd', 19.99)
        _open_card_payment_dialog(draft['id'], card_price)

ui.button(on_click=start_checkout).props(
    'id=card-checkout-trigger').style('position:absolute;left:-9999px;')
```

---

### Card Payment Dialog

A variant of the join-flow payment dialog (`auth_dialog.py:_open_payment_dialog`), but for card purchases instead of membership enrollment.

```python
def _open_card_payment_dialog(card_id, card_price_usd):
    """Payment dialog for purchasing additional NFC cards."""

    with ui.dialog().props('persistent') as pay_dialog, \
         ui.card().classes('w-full max-w-lg mx-auto p-6 gap-0').style(
             'max-height: 90vh; overflow-y: auto;'
         ):

        with ui.row().classes('w-full items-center justify-between mb-4'):
            ui.label('CARD CHECKOUT').classes('text-xl font-semibold tracking-wide')
            ui.button(icon='close', on_click=pay_dialog.close).props('flat round dense')

        ui.label('Custom NFC Card').classes('text-sm font-bold')
        ui.label(f'${card_price_usd:.2f} USD').classes('text-lg font-bold mb-2')

        with ui.tabs().classes('w-full') as pay_tabs:
            card_tab = ui.tab('CARD')
            xlm_tab = ui.tab('XLM')
        pay_tabs.value = 'CARD'

        # ... same CARD / XLM tab panels as join payment dialog ...
        # ... same price loading, XLM conversion, pay button logic ...

        async def handle_pay():
            if pay_tabs.value == 'CARD':
                # Stripe checkout for card purchase
                session = create_checkout_session(
                    order_id=f"card-{uuid.uuid4().hex[:8]}",
                    email=user_email,
                    moniker=moniker,
                    password_hash='',      # not enrollment
                    tier_key=member_type,
                    card_id=card_id,        # new: attach card_id to session metadata
                    amount_usd=card_price_usd,
                )
                # ... redirect to Stripe ...
            elif pay_tabs.value == 'XLM':
                # Stellar payment for card purchase
                # ... same QR flow, but on confirmation → open shipping dialog ...
                pass

    pay_dialog.open()
```

Key differences from the join payment dialog:
- Title says "CARD CHECKOUT" instead of "PAYMENT"
- No enrollment — no user creation on success
- On payment success → opens shipping dialog (instead of redirecting to dashboard)
- No OPUS tab (cards are physical goods, not membership)

---

### Shipping Address Dialog

Opened after payment confirmation (or immediately for entitled cards):

```python
def _open_shipping_dialog(card_id, payment_method, amount_usd, tx_hash=None):
    """Collect shipping address and finalize the card order."""

    with ui.dialog().props('persistent') as ship_dialog, \
         ui.card().classes('w-full max-w-lg mx-auto p-6 gap-4'):

        with ui.row().classes('w-full items-center justify-between mb-2'):
            ui.label('SHIPPING ADDRESS').classes('text-xl font-semibold tracking-wide')
            ui.button(icon='close', on_click=ship_dialog.close).props('flat round dense')

        name_field = form_field('FULL NAME', 'First and Last Name', dense=True)
        street_field = form_field('STREET ADDRESS', '123 Main St, Apt 4', dense=True)
        city_field = form_field('CITY', 'City', dense=True)

        with ui.row().classes('w-full gap-2'):
            with ui.column().classes('flex-1 gap-0'):
                state_field = form_field('STATE / PROVINCE', 'CA', dense=True)
            with ui.column().classes('flex-1 gap-0'):
                zip_field = form_field('ZIP / POSTAL CODE', '90210', dense=True)

        country_field = form_field('COUNTRY', 'United States', dense=True)

        ship_error = ui.label('').classes('text-red-500 text-sm')
        ship_error.set_visibility(False)

        async def submit_order():
            # Validate required fields
            if not all([name_field.value, street_field.value,
                        city_field.value, zip_field.value, country_field.value]):
                ship_error.text = 'Please fill in all required fields.'
                ship_error.set_visibility(True)
                return

            order_id = await db.create_card_order(
                card_id=card_id,
                user_id=user_id,
                payment_method=payment_method,
                amount_usd=amount_usd,
                shipping_name=name_field.value.strip(),
                shipping_street=street_field.value.strip(),
                shipping_city=city_field.value.strip(),
                shipping_state=state_field.value.strip(),
                shipping_zip=zip_field.value.strip(),
                shipping_country=country_field.value.strip(),
            )
            await db.finalize_card_order(order_id, tx_hash=tx_hash)
            ship_dialog.close()
            ui.notify('Card ordered! You will be notified when it ships.', type='positive')
            ui.navigate.to('/profile/edit')

        ui.button('PLACE ORDER', on_click=submit_order).classes(
            'mt-4 px-8 py-3 text-lg w-full'
        )

    ship_dialog.open()
```

---

### Checkout Flow Summary

```
                    ┌─────────────────┐
                    │  Card Editor    │
                    │  (both images   │
                    │   applied)      │
                    └────────┬────────┘
                             │
                        [🛒 Cart]
                             │
                    ┌────────▼────────┐
                    │ Both sides set? │
                    └────┬───────┬────┘
                         │ NO    │ YES
                    (toast)      │
                         │ ┌────▼──────────┐
                         │ │ Entitlement?  │
                         │ │ (cards_ordered │
                         │ │ < cards_incl.) │
                         │ └──┬─────────┬──┘
                         │  YES         NO
                         │    │    ┌────▼────────┐
                         │    │    │  Payment    │
                         │    │    │  Dialog     │
                         │    │    │  (Card/XLM) │
                         │    │    └────┬────────┘
                         │    │         │ paid
                         │    │    ┌────▼────────┐
                         │    └───►│  Shipping   │
                         │         │  Dialog     │
                         │         └────┬────────┘
                         │              │ submitted
                         │         ┌────▼────────┐
                         │         │  Order      │
                         │         │  Created    │
                         │         │  Card set   │
                         │         │  as active  │
                         │         └─────────────┘
```

---

### Unified Card Wallet (`/card/case`)

The card wallet merges two collections into a single carousel:

1. **Own cards** — the user's finalized cards from `user_cards` (status != `'draft'`)
2. **Peer cards** — cards collected from other members (each peer's active card)

Own cards appear first (newest at top), followed by peer cards. A visual separator or badge distinguishes them (e.g. own cards have a subtle gold border; peer cards show the peer's moniker).

#### Data Assembly (`main.py` — `/card/case`)

```python
# 1. Own finalized cards
own_cards = await db.get_user_cards(user_id, exclude_draft=True)
own_data = []
for c in own_cards:
    c = dict(c)
    own_data.append({
        'type': 'own',
        'card_id': c['id'],
        'moniker': moniker,              # owner's own moniker
        'front_url': f'{config.KUBO_GATEWAY}/ipfs/{c["front_image_cid"]}' if c.get('front_image_cid') else '',
        'back_url': f'{config.KUBO_GATEWAY}/ipfs/{c["back_image_cid"]}' if c.get('back_image_cid') else '',
        'is_active': bool(c.get('is_active')),
        'status': c['status'],           # ordered | shipped | delivered
        'linktree_url': f'/profile/{moniker_slug}',
    })

# 2. Peer cards (each peer's active card)
peers = await db.get_peer_cards(user_id)
peer_data = []
for p in peers:
    pd = dict(p)
    peer_slug = pd['moniker'].lower().replace(' ', '-')
    peer_data.append({
        'type': 'peer',
        'moniker': pd['moniker'],
        'front_url': (f'{config.KUBO_GATEWAY}/ipfs/{pd["front_image_cid"]}'
                      if pd.get('front_image_cid') else ''),
        'back_url': (f'{config.KUBO_GATEWAY}/ipfs/{pd["back_image_cid"]}'
                      if pd.get('back_image_cid') else ''),
        'is_active': False,               # not applicable for peers
        'status': None,
        'linktree_url': f'/profile/{peer_slug}',
    })

# Merge: own cards first, then peers
all_cards = own_data + peer_data
```

#### Updated `get_peer_cards()` Query

Joins through `user_cards` instead of reading CIDs from the `users` row:

```sql
SELECT u.moniker, uc.front_image_cid, uc.back_image_cid,
       u.ipns_name, u.member_type
FROM peer_cards pc
JOIN users u ON pc.peer_id = u.id
LEFT JOIN user_cards uc ON uc.user_id = u.id AND uc.is_active = 1
WHERE pc.owner_id = ?
ORDER BY pc.collected_at DESC
```

#### New `get_user_cards()` for Own Cards

```sql
SELECT id, front_image_cid, back_image_cid, status, is_active, created_at
FROM user_cards
WHERE user_id = ? AND status != 'draft'
ORDER BY created_at DESC
```

#### JS Data Shape

The card wallet JS receives a single `all_cards` array. Each entry has a `type` field (`'own'` or `'peer'`) so the scene can render them differently:

```javascript
const allCards = JSON.parse(
    document.getElementById('card-data').textContent
);

allCards.forEach(entry => {
    const card = createCard(entry);
    if (entry.type === 'own') {
        // Gold border ring or "YOUR CARD" label overlay
        addOwnCardBadge(card, entry.is_active, entry.status);
    }
    cards.push(card);
});
```

**Own card visual indicators:**
- Active card: gold border + small star icon
- Ordered (not yet shipped): "ORDERED" status chip
- Shipped: "SHIPPED" status chip
- Delivered: no chip (just the gold border)

**Peer card indicators:**
- Peer moniker label below the card (same as current behavior)

#### Interactions by Card Type

| Action | Own Card | Peer Card |
|--------|----------|-----------|
| Click center → select | Select + rotate (same) | Select + rotate (same) |
| Hold selected → action | Set as active card (if not already) | Open peer's linktree |
| Long-press info | Show order status | Show peer moniker |

---

### Files Modified / Created

| # | File | Change |
|---|------|--------|
| 1 | `static/tiers.json` | Add `cards_included`, `card_price_usd` per tier |
| 2 | `db.py` | Add `user_cards` + `card_orders` tables to SCHEMA; migration for existing cards; new DB functions (`get_user_cards`, `get_draft_card`, `count_ordered_cards`, `create_card_order`, `finalize_card_order`, `set_active_card`) |
| 3 | `main.py` `/card/editor` | Load/create draft card; upload writes to `user_cards`; add checkout trigger |
| 4 | `static/js/card_scene.js` | Add floating cart button (top-right) |
| 5 | `main.py` (new functions) | `_open_card_payment_dialog()`, `_open_shipping_dialog()` |
| 6 | `main.py` `/card/case` | Merge own finalized cards + peer cards into single `all_cards` list; pass unified JSON to JS |
| 7 | `db.py` `get_peer_cards()` | Join through `user_cards` for peer's active card CIDs |
| 8 | `static/js/card_wallet.js` | Handle `type` field (`own` / `peer`); render own-card badges (gold border, status chips); differentiate hold action by type |
| 9 | `payments/stripe_pay.py` | Handle `card_id` in checkout session metadata (for card purchases vs. enrollment) |

---

### Implementation Steps

#### Step 1: Schema + Migrations
- Add `cards_included` and `card_price_usd` to `tiers.json`
- Add `user_cards` and `card_orders` tables to `db.py` SCHEMA
- Add migration to copy existing `nfc_image_cid` / `nfc_back_image_cid` into `user_cards`
- Add all new DB functions

#### Step 2: Card Editor — Draft Cards
- `/card/editor` creates/loads a draft `user_cards` row
- `process_upload()` writes to `user_cards.front_image_cid` / `back_image_cid`
- Pass `card_id` to the JS scene via data attribute

#### Step 3: Cart Button + Checkout Trigger
- Add cart button to `card_scene.js` (top-right floating button)
- Add `card-checkout-trigger` hidden button in `/card/editor`
- Implement `start_checkout()`: validate both images → check entitlement → route to payment or shipping

#### Step 4: Card Payment Dialog
- Create `_open_card_payment_dialog()` — variant of `_open_payment_dialog()` for card purchases
- Wire up Stripe + XLM payment flows with `card_id` metadata
- On payment success → open shipping dialog

#### Step 5: Shipping Address Dialog
- Create `_open_shipping_dialog()` with address form fields
- On submit → `create_card_order()` + `finalize_card_order()`
- Set card as active, navigate to dashboard

#### Step 6: Unified Card Wallet
- Update `get_peer_cards()` to join through `user_cards.is_active = 1`
- Add `get_user_cards(user_id, exclude_draft=True)` for own finalized cards
- `/card/case` merges own cards + peer cards into single `all_cards` array
- Each entry carries `type` (`'own'` or `'peer'`), `is_active`, `status`
- `card_wallet.js` reads `type` to render own-card badges (gold border, status chips) vs. peer moniker labels
- Hold action: own card → set as active; peer card → open linktree

---

### Phase 4: Vendor Order Email Fulfillment

Card orders are finalized in the DB and communicated to the card vendor via email. The existing Mailtrap integration (`email_service.py`) sends a vendor fulfillment email containing order details, card image links (via IPFS gateway), and the shipping address.

#### Config

- `CARD_VENDOR_EMAIL` env var in `config.py` — the vendor's email address. When empty, no vendor email is sent.

#### `email_service.py` — `send_card_order_email()`

Sends an HTML email to `CARD_VENDOR_EMAIL` with:
- Order ID, member moniker + email + tier
- Payment method + amount
- Front/back card image links: `{KUBO_GATEWAY}/ipfs/{cid}`
- Full shipping address (name, street, city, state, zip, country)

Follows the same Mailtrap SDK pattern as `send_welcome_email()` and `send_launch_key_email()`. Wrapped in try/except — email failure never blocks order finalization.

#### `db.py` — `get_user_card_by_id(card_id)`

Simple lookup to retrieve a card row by ID (needed to read CIDs for the email).

#### Integration Point

The vendor email fires in exactly **one place**: `_open_shipping_dialog.handle_submit()` in `main.py`, after `finalize_card_order()` succeeds. The order data dict is built from local scope variables (shipping fields, payment method, amount). The card row is fetched via `get_user_card_by_id()` for image CIDs.

The Stripe webhook path does NOT send the email — shipping info isn't available there (it's collected on the `/card/order/success` redirect, which opens the shipping dialog).

#### Files Modified

| File | Change |
|------|--------|
| `config.py` | `CARD_VENDOR_EMAIL` env var |
| `.env.example` | `CARD_VENDOR_EMAIL=` placeholder |
| `email_service.py` | `send_card_order_email()` function |
| `db.py` | `get_user_card_by_id()` helper |
| `main.py` | Import + call in `handle_submit()` |

#### Future Fulfillment Work

- [ ] Admin dashboard to view/manage card orders (`/admin/orders`)
- [ ] Order status progression: `pending` → `processing` → `shipped` → `delivered`
- [ ] Email notifications at each status change
- [ ] Bulk order batching (aggregate orders for vendor submission)
- [ ] Reorder flow: clone an existing card design into a new draft
- [ ] Order history view in member settings

---

### Verification

1. `uv run python -c "from payments.pricing import TIERS; print(TIERS['forge']['cards_included'])"` — JSON loads with new fields
2. `uv run pytest tests/test_pricing.py` — existing pricing tests pass
3. Navigate to `/card/editor` → cart button visible top-right
4. Upload front + back images → click cart → entitlement check runs
5. Entitled user → shipping dialog opens directly
6. Non-entitled user → payment dialog opens → after payment → shipping dialog
7. Submit shipping → order created, card set as active, redirect to dashboard
8. Navigate to `/card/case` → own finalized cards appear first with gold border
9. Active card shows star icon; ordered cards show "ORDERED" chip
10. Peer cards appear after own cards with peer moniker labels
11. Hold own card → sets it as active; hold peer card → opens linktree
12. Create a second card → cart shows payment dialog (entitlement used up)
13. New card appears in card wallet after checkout, merged with existing cards + peers

---

## Future Enhancements

- NFC tap to collect real peer cards
- Remove card from wallet (long-press or swipe)
- Card sorting / favorites
- GLTF card model with PBR materials (clearcoat, metalness)
- Holographic / iridescent shader effects
- GSAP-powered spring animations
- Card details overlay (peer stats, mutual connections)
- Card gallery: browse all your ordered cards, set any as active
