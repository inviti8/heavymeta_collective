# APP_STORAGE.md — IPFS/IPNS-Backed Linktree & Asset Storage

## Overview

Linktrees, profile images, and card designs move from SQLite-only storage to **IPFS** (via a local Kubo node). Each user's linktree JSON is published under an **IPNS name** — a stable, mutable address that always resolves to the latest version. When content changes, the new version is pinned, the IPNS name is re-published, and old content is unpinned for garbage collection.

SQLite remains the **index** (user accounts, auth, payment records, IPNS key references) while IPFS/IPNS becomes the **content layer**.

---

## Architecture

```
                    heavymeta.coop
                         |
              +----------+----------+
              |                     |
        NiceGUI/FastAPI        Kubo Node
        (port 8080)            (API: 5001, Gateway: 8081)
              |                     |
         SQLite DB             IPFS Datastore
       (user index,           (linktree JSON,
        IPNS key refs,         profile images,
        auth, payments)        card designs)
              |                     |
              +----------+----------+
                         |
              Gateway Route (reverse proxy)
           heavymeta.coop/ipfs/<CID>
           heavymeta.coop/ipns/<key>
```

### Components

| Component | Role |
|-----------|------|
| **Kubo node** | Local IPFS daemon — pins content, manages IPNS keys, serves gateway |
| **NiceGUI app** | Writes linktree JSON + assets to Kubo, publishes IPNS, tracks keys in SQLite |
| **Reverse proxy** (nginx/caddy) | Routes `/ipfs/<CID>` and `/ipns/<key>` to Kubo gateway, everything else to NiceGUI |
| **SQLite** | Stores user accounts, auth, payments, IPNS key name per user |

---

## IPNS — Mutable Names for Linktrees

Each user gets a dedicated **IPNS keypair** managed by Kubo. The IPNS name (public key hash) is a stable address — it never changes even as the linktree content is updated.

```
User "fibo" enrolls
  → Kubo generates IPNS key: ipfs key gen fibo-linktree
  → Key name: "fibo-linktree"
  → IPNS name (peer ID): k51qzi5uqu5d...
  → Stored in SQLite: users.ipns_key_name = "fibo-linktree"

User edits linktree
  → New JSON pinned to IPFS → CID: bafy...xyz
  → IPNS published: ipfs name publish --key=fibo-linktree /ipfs/bafy...xyz
  → IPNS name still resolves at: /ipns/k51qzi5uqu5d...
  → Old JSON CID unpinned
```

### Why IPNS?

- **Stable address** — NFC cards, QR codes, and external links use the IPNS name; no need to update them on every edit
- **Resolvable by any peer** — Pintheon nodes, other IPFS gateways can resolve the name
- **Built into Kubo** — no extra infrastructure needed

---

## Linktree JSON Schema

Each user's public profile is a single JSON document pinned to IPFS and published via IPNS.

```jsonc
{
  "schema_version": 1,
  "moniker": "Fibo Metavinci",
  "member_type": "coop",
  "avatar_cid": "bafy...abc",         // IPFS CID of profile image

  // Color system — dual palette with dark mode preference
  // Modeled after Andromica (glasswing) which uses 6 color roles per mode
  // applied via CSS custom properties + dynamic JS injection
  "dark_mode": null,                   // null = auto (system pref), true = dark, false = light
  "colors": {
    "light": {
      "primary": "#8c52ff",            // brand accent, gradients, active states
      "secondary": "#f2d894",          // badges, secondary accents, CTA highlights
      "text": "#000000",               // moniker, headings, body text
      "bg": "#ffffff",                 // page background
      "card": "#f5f5f5",              // card/container backgrounds, link row fills
      "border": "#e0e0e0"             // card borders, separators, input outlines
    },
    "dark": {
      "primary": "#a87aff",            // lighter purple for dark bg contrast
      "secondary": "#d4a843",          // muted gold
      "text": "#f0f0f0",              // light text on dark bg
      "bg": "#1a1a1a",                // dark page background
      "card": "#2a2a2a",              // dark card backgrounds
      "border": "#444444"             // subtle dark borders
    }
  },

  "links": [
    {
      "label": "Development Site",
      "url": "https://heavymeta.dev",
      "icon_cid": "bafy...def",        // optional — IPFS CID of link icon
      "sort_order": 0
    },
    {
      "label": "Portfolio",
      "url": "https://example.com",
      "icon_cid": null,
      "sort_order": 1
    }
  ],

  "wallets": [
    {
      "network": "stellar",
      "address": "GXXX..."
    }
  ],

  "card_design_cid": "bafy...ghi",    // IPFS CID of NFC card HTML/image

  "override_url": ""                   // external URL redirect (empty = disabled)
}
```

### Schema Notes

- **`schema_version`** — allows future migrations without breaking existing content
- **`avatar_cid` / `icon_cid` / `card_design_cid`** — images are pinned separately; JSON references them by CID
- **`override_url`** — if non-empty, the public profile redirects here instead of rendering the linktree
- **`wallets`** — array to support future multi-chain (Stellar only for now)
- The JSON is **immutable once pinned** — each edit pins a new CID and re-publishes the IPNS name

### Color System (informed by Andromica/glasswing)

The color schema follows the pattern proven in the Andromica app (`../glasswing`):

**6 color roles per palette** — each role maps to specific UI elements:

| Role | Light Mode Usage | Dark Mode Usage |
|------|-----------------|-----------------|
| `primary` | Brand purple, gradient start, active nav | Lighter purple for contrast |
| `secondary` | Badge fills, CTA accents, gradient end | Muted gold |
| `text` | Moniker, headings, labels, body text | Light text for dark backgrounds |
| `bg` | Page body background | Near-black background |
| `card` | Link rows, card containers, input fills | Dark card surfaces |
| `border` | Card outlines, separators, input borders | Subtle dark borders |

**Dark mode preference** (`dark_mode` field):
- `null` — auto, respects visitor's system preference via `prefers-color-scheme`
- `true` — always dark
- `false` — always light

**Application method** (from Andromica's approach):
1. Colors defined as CSS custom properties on `:root`
2. `@media (prefers-color-scheme: dark)` handles auto mode
3. Explicit mode overrides via JavaScript setting `--primary-color`, `--text-color`, etc.
4. Component-specific CSS rules reference the variables: `background-color: var(--card-bg)`
5. Quasar variables updated in parallel: `--q-primary`, `--q-secondary`

**How this maps to the current app** (migration from `profile_colors` table):

| Current field | New schema path | Role |
|--------------|-----------------|------|
| `bg_color` | `colors.light.bg` | Page background |
| `text_color` | `colors.light.text` | Text color |
| `accent_color` | `colors.light.primary` | Brand accent |
| `link_color` | `colors.light.secondary` | Link/CTA color |
| *(new)* | `colors.light.card` | Card/row backgrounds |
| *(new)* | `colors.light.border` | Borders/separators |
| *(new)* | `colors.dark.*` | Full dark palette |
| *(new)* | `dark_mode` | Dark mode preference |

---

## Asset Storage & Lifecycle

| Asset | Format | Max Size | Recommended Size | Notes |
|-------|--------|----------|-----------------|-------|
| Profile avatar | PNG/JPG | 2MB | 512x512px square | Pinned on upload, CID in JSON |
| Link icons | PNG/JPG | 500KB | 128x128px square | Optional per-link icon |
| Card design | PNG/JPG | 2MB | 1050x600px (card ratio) | NFC card image |
| Linktree JSON | JSON | ~50KB | — | Assembled profile document |

### Pin/Unpin Policy

Every asset has a clear lifecycle — **pin on create, unpin on replace**.

```
Avatar update:
  1. User uploads new avatar
  2. Pin new image → get new_avatar_cid
  3. Read current linktree JSON (from IPNS or cache)
  4. old_avatar_cid = current JSON's avatar_cid
  5. old_json_cid = current JSON's CID
  6. Build new JSON with new_avatar_cid
  7. Pin new JSON → get new_json_cid
  8. Publish IPNS name → /ipfs/new_json_cid
  9. Unpin old_avatar_cid
  10. Unpin old_json_cid

Link icon update:  same pattern — unpin old icon CID, pin new one
Card design update: same pattern — unpin old card CID, pin new one
```

This ensures the Kubo node only retains current content. Unpinned CIDs become eligible for garbage collection (`ipfs repo gc`).

---

## Kubo Integration

### Installation

```bash
# Download and init
wget https://dist.ipfs.tech/kubo/v0.32.1/kubo_v0.32.1_linux-amd64.tar.gz
tar xzf kubo_*.tar.gz
sudo mv kubo/ipfs /usr/local/bin/
ipfs init --profile=server
```

### Configuration

```bash
# Restrict API to localhost
ipfs config Addresses.API /ip4/127.0.0.1/tcp/5001

# Gateway on localhost (reverse proxy will expose it)
ipfs config Addresses.Gateway /ip4/127.0.0.1/tcp/8081

# Enable CORS for app
ipfs config --json API.HTTPHeaders.Access-Control-Allow-Origin '["http://localhost:8080"]'
```

### Python Client

```python
# ipfs_client.py — thin wrapper around Kubo HTTP API
import httpx
import json

KUBO_API = "http://127.0.0.1:5001/api/v0"


# ── Content Operations ──

async def ipfs_add(data: bytes, filename: str = "data") -> str:
    """Pin bytes to IPFS, return CID."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{KUBO_API}/add",
            files={"file": (filename, data)},
            params={"pin": "true"},
        )
        resp.raise_for_status()
        return resp.json()["Hash"]


async def ipfs_add_json(obj: dict) -> str:
    """Pin JSON object to IPFS, return CID."""
    data = json.dumps(obj, separators=(",", ":")).encode()
    return await ipfs_add(data, "linktree.json")


async def ipfs_cat(cid: str) -> bytes:
    """Retrieve content by CID."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{KUBO_API}/cat", params={"arg": cid})
        resp.raise_for_status()
        return resp.content


async def ipfs_pin(cid: str):
    """Ensure CID is pinned."""
    async with httpx.AsyncClient() as client:
        await client.post(f"{KUBO_API}/pin/add", params={"arg": cid})


async def ipfs_unpin(cid: str):
    """Unpin CID — content becomes garbage-collectible."""
    async with httpx.AsyncClient() as client:
        try:
            await client.post(f"{KUBO_API}/pin/rm", params={"arg": cid})
        except httpx.HTTPStatusError:
            pass  # already unpinned


# ── IPNS Key Management ──

async def ipns_key_gen(name: str) -> str:
    """Generate a new IPNS keypair, return the IPNS name (peer ID)."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{KUBO_API}/key/gen",
            params={"arg": name, "type": "ed25519"},
        )
        resp.raise_for_status()
        return resp.json()["Id"]  # the IPNS name (k51qzi...)


async def ipns_publish(key_name: str, cid: str) -> str:
    """Publish CID under IPNS key, return the IPNS name."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{KUBO_API}/name/publish",
            params={
                "arg": f"/ipfs/{cid}",
                "key": key_name,
                "allow-offline": "true",
            },
        )
        resp.raise_for_status()
        return resp.json()["Name"]  # the IPNS name


async def ipns_resolve(ipns_name: str) -> str:
    """Resolve IPNS name to current CID."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{KUBO_API}/name/resolve",
            params={"arg": ipns_name},
        )
        resp.raise_for_status()
        path = resp.json()["Path"]  # "/ipfs/bafy..."
        return path.split("/ipfs/")[-1]


# ── High-Level Operations ──

async def publish_linktree(key_name: str, linktree: dict,
                           old_json_cid: str = None) -> tuple[str, str]:
    """Pin linktree JSON and publish via IPNS.
    Returns (new_json_cid, ipns_name).
    Unpins old JSON CID if provided."""
    new_cid = await ipfs_add_json(linktree)
    ipns_name = await ipns_publish(key_name, new_cid)
    if old_json_cid and old_json_cid != new_cid:
        await ipfs_unpin(old_json_cid)
    return new_cid, ipns_name


async def replace_asset(new_data: bytes, old_cid: str = None,
                        filename: str = "asset") -> str:
    """Pin new asset, unpin old one. Returns new CID."""
    new_cid = await ipfs_add(new_data, filename)
    if old_cid and old_cid != new_cid:
        await ipfs_unpin(old_cid)
    return new_cid
```

---

## Gateway Setup

The server exposes IPFS and IPNS content via reverse proxy.

### Caddy Example

```caddyfile
heavymeta.coop {
    # IPFS gateway (content-addressed)
    handle /ipfs/* {
        reverse_proxy 127.0.0.1:8081
    }

    # IPNS gateway (name-resolved)
    handle /ipns/* {
        reverse_proxy 127.0.0.1:8081
    }

    # NiceGUI app
    handle {
        reverse_proxy 127.0.0.1:8080
    }
}
```

### Nginx Example

```nginx
server {
    server_name heavymeta.coop;

    location /ipfs/ {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
    }

    location /ipns/ {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## Database Changes

### Users Table — Add IPNS Columns

```sql
ALTER TABLE users ADD COLUMN ipns_key_name TEXT;   -- Kubo key name (e.g., "fibo-linktree")
ALTER TABLE users ADD COLUMN ipns_name TEXT;        -- IPNS address (k51qzi...)
ALTER TABLE users ADD COLUMN linktree_cid TEXT;     -- current JSON CID (for unpin tracking)
```

### Tables to Deprecate (after migration)

| Table | Replaced By |
|-------|-------------|
| `link_tree` | `links` array in linktree JSON on IPFS |
| `profile_colors` | `colors` object in linktree JSON on IPFS |
| `profile_settings` | `override_url` in linktree JSON; `linktree_override` stays in SQLite |

### What Stays in SQLite

| Data | Reason |
|------|--------|
| User accounts (id, email, moniker, password_hash) | Auth is server-side, never public |
| Payment records | Financial records, not shareable |
| `ipns_key_name` / `ipns_name` / `linktree_cid` | Index to resolve user to IPNS + track current CID for unpin |
| `linktree_override` flag | Server-side redirect decision |
| Stellar keys (encrypted) | Sensitive, never on IPFS |

---

## Save Flow (Edit → Pin → Publish → Unpin)

```
1. User edits profile (links, colors, avatar, etc.)
2. If new images uploaded:
   a. Pin new image → get new CID
   b. Unpin old image CID (from current linktree JSON)
3. Assemble linktree JSON with current CIDs
4. Pin new JSON to IPFS → get new_json_cid
5. Publish IPNS: ipns_publish(user.ipns_key_name, new_json_cid)
6. Unpin old JSON CID (user.linktree_cid)
7. Update SQLite: users.linktree_cid = new_json_cid
```

### User Enrollment — IPNS Key Setup

```
New user signs up
  → ipns_key_gen("{user_id}-linktree") → returns ipns_name
  → Store in SQLite: ipns_key_name, ipns_name
  → Build initial linktree JSON (empty links, default colors)
  → Pin JSON → publish IPNS → store linktree_cid
```

### Public Profile Resolution

```
GET /profile/{moniker_slug}
  → SQLite lookup: user.ipns_name, user.linktree_override
  → If linktree_override: redirect to override_url from JSON
  → Else: fetch linktree JSON via IPNS (or from cache/direct CID)
  → Render page with colors, links, avatar from /ipfs/<cid> paths
  → Images served via gateway: heavymeta.coop/ipfs/<avatar_cid>
```

### NFC Card / QR Code Address

```
The IPNS name is the permanent public address for a user's linktree:
  heavymeta.coop/ipns/k51qzi5uqu5d...

This URL never changes, even as the user edits their profile.
Can be encoded in NFC cards, QR codes, printed materials.
```

---

## Migration Strategy

| Phase | Description |
|-------|-------------|
| **Phase 1** (current) | SQLite-only storage (link_tree, profile_colors tables) |
| **Phase 2** | Install Kubo, add ipfs_client.py, generate IPNS keys for existing users |
| **Phase 3** | Dual-write: dashboard saves to SQLite + pins to IPFS/IPNS |
| **Phase 4** | Public profile reads from IPFS JSON (SQLite as fallback) |
| **Phase 5** | Drop legacy tables, SQLite is index-only |

---

## Resolved Design Decisions

### Pinning Redundancy

Heavymeta will operate **multiple public gateways** running Kubo. All gateways pin the same content, providing redundancy and geographic distribution. No third-party pinning services (Pinata, web3.storage) needed.

### IPNS Publish Latency

Not a concern for our deployment. Two types of IPFS content access:

- **`/ipfs/<CID>`** — direct content lookup. If pinned on the gateway node, it's instant. Identical to a traditional file server.
- **`/ipns/<name>`** — requires resolving the IPNS name to a CID first. For *external* peers, this involves a DHT lookup (can take seconds). But since our Kubo nodes are both the publisher and the gateway, the latest IPNS→CID mapping is already in the local datastore — **resolution is near-instant on our own gateways**.

For `heavymeta.coop/ipns/<key>`: effectively instant, just like serving a static file. We use `allow-offline: true` on publish to ensure the record is written to the local store immediately without waiting for DHT propagation.

### Cache Layer

Cache linktree JSON in memory where practical — for the user's own linktree (frequently accessed during editing) and for peer linktrees (card case view). Files are small (~50KB max), so a simple in-memory dict with TTL is sufficient. No Redis or external cache needed.

### Image Size Limits

No server-side image processing (resizing/compressing). Instead, enforce upload size limits and provide guidance:

| Asset | Max Size | Recommended Dimensions |
|-------|----------|----------------------|
| Profile avatar | 2MB | 512x512px, square, PNG or JPG |
| Link icons | 500KB | 128x128px, square, PNG |
| Card design image | 2MB | 1050x600px (standard card ratio), PNG or JPG |

Validation happens at upload time — reject files exceeding limits before pinning.

### Card Design Format

Card designs are **images only** (PNG or JPG), not HTML. The `card_design_cid` field in the linktree JSON points to a pinned image file. The card editor in the dashboard is an image upload tool, not an HTML editor.

Updated schema field:
```jsonc
"card_design_cid": "bafy...ghi"    // IPFS CID of card image (PNG/JPG, max 2MB)
```

### IPNS Key Backup

IPNS private keys are exported from Kubo and stored **encrypted** alongside user data in SQLite. This ensures key recovery if the Kubo keystore is lost.

```sql
ALTER TABLE users ADD COLUMN ipns_key_backup TEXT;  -- exported key, encrypted with Guardian key
```

Backup flow:
```
On IPNS key generation:
  1. ipfs key gen "{user_id}-linktree" → creates key in Kubo keystore
  2. ipfs key export "{user_id}-linktree" → raw key bytes
  3. Encrypt key bytes with Guardian public key (same as launch token encryption)
  4. Store encrypted key in users.ipns_key_backup

On recovery:
  1. Decrypt ipns_key_backup with Guardian key
  2. ipfs key import "{user_id}-linktree" < key_bytes
  3. User's IPNS name is restored
```

### Garbage Collection

Run `ipfs repo gc` on a scheduled cron (e.g., daily at off-peak hours). Unpinned content (old linktree JSON versions, replaced images) is cleaned up automatically.

```cron
# Daily GC at 3am
0 3 * * * /usr/local/bin/ipfs repo gc --silent
```
