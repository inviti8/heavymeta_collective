# Heavymeta Collective — Architecture

A complete technical reference for the cooperative onboarding platform. This document covers every subsystem, data flow, and integration point so that any developer — human or AI — can understand, modify, and extend the application.

---

## Table of Contents

1. [Tech Stack](#1-tech-stack)
2. [Project Structure](#2-project-structure)
3. [Configuration & Environment](#3-configuration--environment)
4. [Database Schema](#4-database-schema)
5. [Authentication & Sessions](#5-authentication--sessions)
6. [Enrollment Flows](#6-enrollment-flows)
7. [Stellar Integration](#7-stellar-integration)
8. [IPFS/IPNS Content Layer](#8-ipfsipns-content-layer)
9. [Payment Systems](#9-payment-systems)
10. [Wallet Systems](#10-wallet-systems)
11. [UI Architecture](#11-ui-architecture)
12. [Theme System](#12-theme-system)
13. [QR Code Generation](#13-qr-code-generation)
14. [Email Service](#14-email-service)
15. [Launch Credentials](#15-launch-credentials)
16. [Adjacent Repos & Bindings](#16-adjacent-repos--bindings)
17. [Testing](#17-testing)
18. [Key Patterns & Conventions](#18-key-patterns--conventions)

---

## 1. Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Web UI | NiceGUI 3.7 | Python-native UI framework built on Vue/Quasar |
| HTTP | FastAPI | Async API routes (Stripe webhook), bundled with NiceGUI |
| Database | SQLite via aiosqlite | Single-file DB at `./data/collective.db` |
| Blockchain | Stellar SDK 13.x | Horizon queries, transaction building, Soroban contract calls |
| Smart Contracts | Soroban (Stellar) | `hvym_roster`, `hvym_collective`, `opus_token`, `hvym_pin_service` |
| Encryption | hvym_stellar (local) | X25519 ECDH shared keys, token serialization |
| Content Storage | IPFS via Kubo | Local node, HTTP API on `:5001`, gateway on `:8081` |
| Fiat Payments | Stripe | Hosted checkout + webhook |
| Email | Mailtrap | Transactional email API |
| Auth | argon2 (passlib) | Password hashing |
| QR Codes | qrcode + Pillow | Branded QR with embedded images and denomination badges |
| Package Manager | uv | All commands use `uv run`, `uv pip install` |

---

## 2. Project Structure

```
heavymeta_collective/
├── main.py                 # All NiceGUI page routes (~1500 lines)
├── config.py               # Environment loading, Stellar keys, constants
├── db.py                   # SQLite schema + async CRUD
├── auth.py                 # Password hashing, login, rate limiting
├── auth_dialog.py          # NiceGUI login/join modal dialogs
├── enrollment.py           # Free + paid enrollment flows
├── stellar_ops.py          # Horizon operations (fund, balance, send, roster)
├── launch.py               # Pintheon launch token generation
├── wallet_ops.py           # Denomination wallet creation
├── ipfs_client.py          # Kubo HTTP API wrapper (IPFS + IPNS)
├── linktree_renderer.py    # Unified public profile HTML renderer
├── qr_gen.py               # QR code generation (profile, link, denom)
├── components.py           # Reusable NiceGUI components
├── theme.py                # Dynamic CSS theme injection
├── email_service.py        # Mailtrap email delivery
├── seed_peers.py           # Dev helper: seed dummy peer data
├── payments/
│   ├── pricing.py          # XLM price feed (CoinGecko, 5-min cache)
│   ├── stellar_pay.py      # Stellar payment requests + detection
│   └── stripe_pay.py       # Stripe checkout + webhook handling
├── bindings/
│   └── hvym_roster/        # Auto-generated Soroban contract bindings
├── static/
│   ├── placeholder.png     # Default avatar/icon
│   ├── stellar_logo.png    # Stellar branding (wallet QR)
│   ├── pintheon_logo.png   # Pintheon branding (launch section)
│   └── stellar_logo_*.png  # Light/dark variants
├── tests/
│   ├── conftest.py         # Pytest fixtures
│   ├── test_auth.py
│   ├── test_enrollment.py
│   ├── test_payments.py
│   ├── test_pricing.py
│   ├── test_stellar_ops.py
│   └── test_ipfs_client.py
├── docs/
│   ├── VISION.md           # Product vision and use case
│   └── ARCHITECTURE.md     # This file
├── data/
│   └── collective.db       # SQLite database (created at startup)
└── requirements.txt        # Pinned dependencies
```

---

## 3. Configuration & Environment

All configuration lives in `config.py`, loaded from environment variables (via `.env` / `python-dotenv`).

### Required Environment Variables

| Variable | Purpose | Crash on Missing |
|----------|---------|:---:|
| `BANKER_SECRET` | Stellar keypair secret for the Collective treasury | Yes |
| `GUARDIAN_SECRET` | Stellar keypair secret for encryption co-signer | Yes |
| `APP_SECRET_KEY` | NiceGUI session cookie signing key | Yes |

### Optional Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `STELLAR_NETWORK` | `testnet` | `testnet` or `mainnet` — switches all Stellar endpoints |
| `DATABASE_PATH` | `./data/collective.db` | SQLite file location |
| `STRIPE_SECRET_KEY` | — | Stripe API secret |
| `STRIPE_PUBLISHABLE_KEY` | — | Stripe frontend key |
| `STRIPE_WEBHOOK_SECRET` | — | Stripe webhook signature verification |
| `MAILTRAP_API_TOKEN` | — | Mailtrap email API |
| `KUBO_API` | `http://127.0.0.1:5001/api/v0` | Kubo IPFS API endpoint |
| `KUBO_GATEWAY` | `http://127.0.0.1:8081` | IPFS gateway URL |

### Derived Configuration (config.py)

```python
# Network-dependent values resolved at import time
HORIZON_URL  = NETWORK_CONFIG[NET]["horizon_url"]
RPC_URL      = NETWORK_CONFIG[NET]["rpc_url"]
NET_PW       = NETWORK_CONFIG[NET]["passphrase"]
EXPLORER_URL = NETWORK_CONFIG[NET]["explorer"]

# Keypairs
BANKER_KP      = Keypair.from_secret(BANKER_SECRET)
GUARDIAN_KP    = Keypair.from_secret(GUARDIAN_SECRET)
BANKER_25519   = Stellar25519KeyPair(BANKER_KP)    # X25519 for ECDH
GUARDIAN_25519 = Stellar25519KeyPair(GUARDIAN_KP)

# Constants
XLM_COST           = 333       # Coop membership price in XLM
DENOM_PRESETS       = [1, 2, 3, 5, 8, 13, 21]  # Fibonacci
DENOM_FEE_PERCENT   = 3        # 3% collective fee
FALLBACK_PRICE      = 0.10     # USD/XLM if CoinGecko fails
CACHE_TTL           = 300      # Price cache: 5 minutes
```

### Soroban Contract Addresses (Testnet)

```python
CONTRACTS = {
    "hvym_roster":      "CDWX72R3Z7CAKWWBNKVNDLSUH5WZOC4CR7OOFJQANO2IX37S3IE4JRRO",
    "hvym_collective":  "CAYD2PS5KR4VSEQPQZEUDF3KHT2NDWTGVXAHPPMLLS4HHM5ARUNALFUU",
    "opus_token":       "CB3MM62JMDTNVJVOXORUOOPBFAWVTREJLA5VN4YME4MBNCHGBHQPQH7G",
    "hvym_pin_service": "CCEDYFIHUCJFITWEOT7BWUO2HBQQ72L244ZXQ4YNOC6FYRDN3MKDQFK7",
}
```

---

## 4. Database Schema

Eight tables in SQLite, initialized at app startup via `db.init_db()`.

### `users`

The central identity table. Free members have NULL Stellar fields.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `email` | TEXT UNIQUE | Login identifier |
| `moniker` | TEXT UNIQUE | Display name |
| `member_type` | TEXT | `'free'` or `'coop'` |
| `password_hash` | TEXT | argon2 hash |
| `stellar_address` | TEXT | Public key (coop only) |
| `shared_pub` | TEXT | X25519 public key (coop only) |
| `encrypted_token` | TEXT | Dual-key encrypted secret (coop only) |
| `nfc_image_cid` | TEXT | IPFS CID of front NFC card image |
| `nfc_back_image_cid` | TEXT | IPFS CID of back NFC card image |
| `avatar_cid` | TEXT | IPFS CID of profile avatar |
| `qr_code_cid` | TEXT | IPFS CID of personal QR code |
| `ipns_key_name` | TEXT | Kubo key name (e.g. `"{user_id}-linktree"`) |
| `ipns_name` | TEXT | IPNS public address (`k51qzi...`) |
| `linktree_cid` | TEXT | Current published linktree JSON CID |
| `ipns_key_backup` | TEXT | Guardian-encrypted IPNS private key |
| `created_at` | TIMESTAMP | Enrollment time |
| `network` | TEXT | `'testnet'` or `'mainnet'` |

### `link_tree`

User's link-tree entries, ordered by `sort_order`.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `user_id` | TEXT FK | References `users(id)` |
| `label` | TEXT | Display text |
| `url` | TEXT | Target URL |
| `icon_url` | TEXT | Legacy icon URL |
| `icon_cid` | TEXT | IPFS CID of icon image |
| `qr_cid` | TEXT | IPFS CID of branded QR for this link |
| `sort_order` | INTEGER | Ordering index |

### `profile_colors`

12-color palette (6 light + 6 dark) per user.

| Column | Type | Default |
|--------|------|---------|
| `user_id` | TEXT PK | FK to `users` |
| `bg_color` | TEXT | `#ffffff` |
| `text_color` | TEXT | `#000000` |
| `accent_color` | TEXT | `#8c52ff` |
| `link_color` | TEXT | `#f2d894` |
| `card_color` | TEXT | `#f5f5f5` |
| `border_color` | TEXT | `#e0e0e0` |
| `dark_bg_color` | TEXT | `#1a1a1a` |
| `dark_text_color` | TEXT | `#f0f0f0` |
| `dark_accent_color` | TEXT | `#a87aff` |
| `dark_link_color` | TEXT | `#d4a843` |
| `dark_card_color` | TEXT | `#2a2a2a` |
| `dark_border_color` | TEXT | `#444444` |

### `profile_settings`

Per-user settings (dark mode, linktree override).

| Column | Type | Default |
|--------|------|---------|
| `user_id` | TEXT PK | FK to `users` |
| `linktree_override` | INTEGER | `0` (boolean) |
| `linktree_url` | TEXT | `''` |
| `dark_mode` | INTEGER | `0` (boolean) |

### `peer_cards`

NFC card collection (card case feature).

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `owner_id` | TEXT FK | User who collected the card |
| `peer_id` | TEXT FK | User whose card was collected |
| `collected_at` | TIMESTAMP | When card was added |
| | UNIQUE | `(owner_id, peer_id)` |

### `payments`

Payment audit trail for enrollment.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `user_id` | TEXT FK | |
| `method` | TEXT | `'stellar'` or `'stripe'` |
| `amount` | TEXT | XLM or USD amount as string |
| `xlm_price_usd` | REAL | Exchange rate at payment time |
| `memo` | TEXT | Stellar memo or Stripe session ID |
| `tx_hash` | TEXT | Stellar tx hash or Stripe payment intent |
| `status` | TEXT | `'pending'`, `'completed'`, `'failed'` |
| `created_at` | TIMESTAMP | |

### `denom_wallets`

Denomination wallet instances per user.

| Column | Type | Notes |
|--------|------|-------|
| `id` | TEXT PK | UUID |
| `user_id` | TEXT FK | Owner |
| `denomination` | INTEGER | 1, 2, 3, 5, 8, 13, or 21 XLM |
| `stellar_address` | TEXT | Shared public key |
| `token` | TEXT | Serialized `StellarSharedAccountToken` |
| `qr_cid` | TEXT | IPFS CID of branded QR with denomination badge |
| `status` | TEXT | `'active'`, `'spent'`, `'discarded'` |
| `sort_order` | INTEGER | Display order |
| `created_at` | TIMESTAMP | |
| `spent_at` | TIMESTAMP | When payment received |
| `merge_hash` | TEXT | AccountMerge tx hash |
| `payout_hash` | TEXT | Banker-to-user payment tx hash |
| `fee_xlm` | REAL | Collective fee retained |

---

## 5. Authentication & Sessions

### Password Handling (`auth.py`)

- **Hashing:** argon2 via passlib's `CryptContext`
- **Verification:** constant-time comparison
- **No plaintext storage** anywhere in the system

### Rate Limiting (`auth.py`)

- **Max 5 failed attempts** per email address
- **5-minute lockout** after exceeding limit
- **In-memory tracking** (resets on app restart)
- Failed attempts return generic "Invalid email or password" (no user enumeration)

### Session Management

Sessions use NiceGUI's `app.storage.user`, which is server-side storage backed by a browser cookie.

**Session fields set at login/enrollment:**
```python
app.storage.user['authenticated'] = True
app.storage.user['user_id'] = user['id']
app.storage.user['moniker'] = user['moniker']
app.storage.user['member_type'] = user['member_type']
app.storage.user['email'] = user['email']
```

**Route guards:**
- `require_auth()` — redirects to `/` if not authenticated
- `require_coop()` — redirects to `/join` if not a coop member

**Logout:** `app.storage.user.clear()` + navigate to `/`

### Auth Dialog (`auth_dialog.py`)

A modal dialog with two tabs:
1. **LOGIN** — email + password form
2. **JOIN** — membership tier selector (free/coop), form fields, payment method toggle (XLM/Card)

The dialog handles the full signup flow inline, including Stellar payment QR display and Stripe redirect.

---

## 6. Enrollment Flows

### Free Tier

```
User fills JOIN form (email, moniker, password) with "Free" tier selected
  → auth.py: validate inputs, hash password
  → db.create_user(member_type='free', stellar fields=NULL)
  → email_service.send_welcome_email()
  → enrollment._setup_ipns():
      → ipfs_client.ipns_key_gen("{user_id}-linktree")
      → ipfs_client.ipns_key_export() → encrypt with Guardian
      → ipfs_client.build_linktree_json() → initial JSON
      → ipfs_client.publish_linktree() → pin JSON, publish IPNS
      → db.update_user(ipns_key_name, ipns_name, linktree_cid, ipns_key_backup)
  → auth.set_session()
  → redirect to /profile/edit
```

### Paid Tier — XLM Payment

```
User fills JOIN form with "Coop" tier, XLM payment selected
  → Create pending user (member_type='free' initially)
  → stellar_pay.create_stellar_payment_request()
      → Generate order_id, memo = "hvym-{order_id}"
      → Build web+stellar:pay URI (333 XLM, memo)
      → Generate QR code (Stellar logo embedded)
  → Navigate to /join/pay/xlm (shows QR + address + memo)
  → Poll stellar_pay.check_payment(memo) every 5 seconds via Horizon
  → On detection:
      → enrollment.process_paid_enrollment():
          → Keypair.random() → user's Stellar keypair
          → stellar_ops.fund_account(pub, "22") → Banker sends 22 XLM
          → StellarSharedKey encrypt → encrypted_token
          → db.create_user(member_type='coop', stellar_address, encrypted_token, ...)
          → db.create_payment(method='stellar', amount='333', tx_hash)
          → stellar_ops.register_on_roster(user_keys, moniker) → Soroban call
          → email_service.send_welcome_email()
          → enrollment._setup_ipns()
      → auth.set_session()
      → redirect to /profile/edit
```

### Paid Tier — Stripe Payment

```
User fills JOIN form with "Coop" tier, Card payment selected
  → stripe_pay.create_checkout_session(order_id, email, moniker, password_hash)
      → pricing.get_stripe_price_cents() → XLM_COST * xlm_usd * 2 * 100
      → Stripe session created (metadata = signup data)
  → Redirect to Stripe hosted checkout

On Stripe payment completion:
  → Stripe sends POST to /api/stripe/webhook
  → stripe_pay.handle_webhook() verifies signature, extracts data
  → enrollment.process_paid_enrollment() (same as XLM path)
  → Return 200 OK

Meanwhile, user redirected to /join/success?session_id=...
  → Polls DB every 3 seconds for user.member_type == 'coop'
  → On detection: set session, redirect to /profile/edit
```

---

## 7. Stellar Integration

### Dual-Key Encryption (Banker + Guardian)

The core security model. User Stellar secrets are encrypted such that neither the Banker key nor the Guardian key alone can decrypt them.

**Encryption (at enrollment):**
```python
from hvym_stellar import StellarSharedKey, Stellar25519KeyPair

# Convert Ed25519 → X25519 for ECDH
banker_25519   = Stellar25519KeyPair(BANKER_KP)
guardian_25519 = Stellar25519KeyPair(GUARDIAN_KP)

# Encrypt user secret
encryptor = StellarSharedKey(banker_25519, guardian_25519.public_key())
encrypted = encryptor.encrypt(user_keys.secret.encode())
# Result format: "base64_salt|base64_nonce|base64_sig|hex_ciphertext"
```

**Decryption (at send, launch token generation):**
```python
from hvym_stellar import StellarSharedDecryption

decryptor = StellarSharedDecryption(GUARDIAN_25519, BANKER_25519.public_key())
enc = user['encrypted_token']
if isinstance(enc, str):
    enc = enc.encode()
secret = decryptor.decrypt(enc, from_address=BANKER_KP.public_key)
if isinstance(secret, bytes):
    secret = secret.decode()
user_kp = Keypair.from_secret(secret)
```

This pattern appears in `launch.py` (lines 20-27) and `main.py` (settings wallet send dialog). It is the canonical way to recover a user's keypair from the database.

### Horizon Operations (`stellar_ops.py`)

| Function | Purpose |
|----------|---------|
| `fund_account(pub, amount="22")` | Banker creates + funds a new Stellar account |
| `get_xlm_balance(address)` | Query native XLM balance from Horizon |
| `send_xlm(source_kp, dest, amount, memo)` | Build, sign, submit a payment transaction |
| `register_on_roster(user_keys, moniker)` | Call `hvym_roster.join()` Soroban contract |

### Network Switching

A single env var controls the entire Stellar stack:

```python
NET = os.getenv("STELLAR_NETWORK", "testnet")
```

This resolves `HORIZON_URL`, `RPC_URL`, `NET_PW` (network passphrase), and `EXPLORER_URL` from a config dictionary. No code changes needed for mainnet deployment.

---

## 8. IPFS/IPNS Content Layer

### Architecture

```
NiceGUI App ──HTTP──→ Kubo Node (localhost:5001) ──IPFS──→ DHT / Gateways
                          │
                      Gateway (localhost:8081)
                          │
                   Public visitors fetch content via gateway
```

- **Kubo** (Go-IPFS) runs locally as the IPFS daemon
- **ipfs_client.py** wraps the Kubo HTTP API with httpx
- **Content types:** Linktree JSON, profile images, QR code PNGs, NFC card designs

### IPFS Operations (`ipfs_client.py`)

| Function | Purpose |
|----------|---------|
| `ipfs_add(data, filename)` | Pin bytes to IPFS, return CID |
| `ipfs_add_json(obj)` | Pin JSON object, return CID |
| `ipfs_cat(cid)` | Retrieve content by CID |
| `ipfs_pin(cid)` | Pin an existing CID |
| `ipfs_unpin(cid)` | Unpin a CID (allows garbage collection) |
| `replace_asset(new_data, old_cid, filename)` | Pin new, unpin old, return new CID |

### IPNS Operations (`ipfs_client.py`)

| Function | Purpose |
|----------|---------|
| `ipns_key_gen(name)` | Generate a new IPNS keypair in Kubo |
| `ipns_key_export(name)` | Export private key bytes (for encrypted backup) |
| `ipns_key_import(name, key_bytes)` | Import key (for recovery) |
| `ipns_publish(key_name, cid)` | Publish CID under IPNS name |
| `ipns_resolve(ipns_name)` | Resolve IPNS name to current CID |

### IPNS Key Lifecycle

1. **Created** at enrollment — `ipns_key_gen("{user_id}-linktree")`
2. **Exported + encrypted** — Guardian-encrypted backup stored in `users.ipns_key_backup`
3. **Used for publishing** — every profile edit triggers `ipns_publish()`
4. **Recoverable** — if Kubo keystore is lost, decrypt backup and `ipns_key_import()`

### Linktree JSON Schema (v1)

```json
{
  "schema_version": 1,
  "moniker": "Fibo Metavinci",
  "member_type": "coop",
  "avatar_cid": "bafy...abc",
  "dark_mode": null,
  "colors": {
    "light": {
      "primary": "#8c52ff",
      "secondary": "#f2d894",
      "text": "#000000",
      "bg": "#ffffff",
      "card": "#f5f5f5",
      "border": "#e0e0e0"
    },
    "dark": { ... }
  },
  "links": [
    {
      "label": "My Site",
      "url": "https://example.com",
      "icon_cid": "bafy...def",
      "qr_cid": "bafy...xyz",
      "sort_order": 0
    }
  ],
  "wallets": [
    {
      "network": "stellar",
      "type": "denom",
      "denomination": 5,
      "address": "GABC...DEFG",
      "qr_cid": "bafy..."
    }
  ],
  "card_design_cid": "bafy...ghi",
  "override_url": ""
}
```

### Publish Flow

```
User edits profile (links, colors, card, etc.)
  → ipfs_client.build_linktree_json(user_id) — assemble from SQLite
  → ipfs_client.publish_linktree(key_name, json, old_cid)
      → ipfs_add_json(json) → new_cid
      → ipns_publish(key_name, new_cid)
      → ipfs_unpin(old_cid)
  → db.update_user(linktree_cid=new_cid)
```

Republishing is fire-and-forget via `schedule_republish(user_id)` — an asyncio background task that doesn't block the UI response.

### Public Routes

| Route | Handler | Source |
|-------|---------|--------|
| `/lt/{ipns_name}` | NiceGUI (`main.py`) | Owner: fresh SQLite build. Visitor: IPFS JSON fetch |
| `/ipns/{name}` | Kubo gateway | Raw JSON (machine-readable) |
| `/ipfs/{cid}` | Kubo gateway | Direct asset access (images, QR PNGs) |

---

## 9. Payment Systems

### XLM Payment (`payments/stellar_pay.py`)

1. Generate unique `order_id` and memo (`hvym-{order_id}`)
2. Build `web+stellar:pay?destination={BANKER_PUB}&amount=333&memo={memo}` URI
3. Generate QR code with Stellar logo embedded
4. Display on `/join/pay/xlm` page
5. Poll `check_payment(memo)` every 5 seconds — queries Horizon for operations on Banker account matching the memo
6. On match: trigger `process_paid_enrollment()`

### Stripe Payment (`payments/stripe_pay.py`)

1. Calculate dynamic price: `XLM_COST * xlm_price_usd * 2` (2x market rate)
2. Create Stripe Checkout Session with signup metadata
3. Redirect user to Stripe hosted checkout
4. On completion: Stripe POSTs to `/api/stripe/webhook`
5. Webhook handler verifies signature, extracts metadata
6. Triggers `process_paid_enrollment()`

### Pricing (`payments/pricing.py`)

- **Source:** CoinGecko free API (`/simple/price?ids=stellar&vs_currencies=usd`)
- **Cache:** 5-minute TTL, in-memory
- **Fallback:** `$0.10` if API fails
- **Stripe multiplier:** 2x (Stripe price = 2 * XLM_COST * xlm_price_usd)

---

## 10. Wallet Systems

### Main Wallet (User's Stellar Account)

The user's primary Stellar keypair, created at paid enrollment.

- **Secret storage:** Dual-key encrypted in `users.encrypted_token`
- **Funded:** 22 XLM at enrollment (from Banker)
- **Visibility:** Settings page only (never in public linktree)
- **Operations (settings page):**
  - **Balance** — `get_xlm_balance()` via Horizon, refreshable
  - **Receive** — QR dialog encoding `web+stellar:pay?destination={address}` with Stellar logo
  - **Send** — Form dialog (destination, amount, memo) → decrypt secret → `send_xlm()`

### Denomination Wallets (Disposable Payment Addresses)

Ephemeral Stellar accounts for quick peer-to-peer payments at fixed amounts.

**Denominations:** 1, 2, 3, 5, 8, 13, 21 XLM (Fibonacci sequence)

**Creation (`wallet_ops.py`):**
```python
token = StellarSharedAccountTokenBuilder(
    senderKeyPair=BANKER_25519,
    receiverPub=GUARDIAN_25519.public_key(),
    caveats={'denomination': denomination, 'user_id': user_id},
)
address = token.shared_public_key    # Deterministic from ECDH
serialized = token.serialize()       # Stored in denom_wallets.token
```

**Pay URI:** `web+stellar:pay?destination={address}&amount={denomination}&asset_code=XLM`

**QR Codes:** User's branded QR (avatar + colors) with a circular denomination badge in the bottom-right corner.

**Payment Settlement Flow (future watcher):**
```
Payer scans QR → sends {denomination} XLM → account created on-ledger
  → Watcher detects account exists (polling)
  → Extract keypair from token (StellarSharedAccountTokenBuilder)
  → AccountMerge: denom wallet → Banker (recovers all XLM)
  → Calculate: fee = balance * 3%, payout = balance - fee
  → Payment: Banker → user's main wallet (payout amount)
  → Mark wallet 'spent', record merge_hash, payout_hash, fee_xlm
  → Auto-generate replacement wallet with same denomination
```

**Public visibility:** Active denom wallets appear in the linktree JSON and are rendered on the public profile with clickable QR thumbnails.

---

## 11. UI Architecture

### Page Routes (`main.py`)

| Route | Auth | Description |
|-------|------|-------------|
| `/` | None | Landing page with hero image, join/login CTAs |
| `/join` | None | Opens auth dialog on JOIN tab |
| `/login` | None | Opens auth dialog on LOGIN tab |
| `/join/pay/xlm` | None | XLM payment QR + polling page |
| `/join/success` | None | Stripe success confirmation + auto-login poll |
| `/profile/edit` | Required | Main dashboard: links CRUD, wallets, card design |
| `/card/editor` | Coop | NFC card front/back image upload |
| `/card/case` | Coop | Collected peer cards (3D card flip) |
| `/qr` | Coop | Personal QR code viewer (3D, downloadable) |
| `/settings` | Required | Theme editor (THEME expansion) + wallet (WALLET expansion, coop only) |
| `/launch` | Coop | Pintheon launch token generation + email |
| `/lt/{ipns_name}` | None | Public linktree (rendered from IPFS or SQLite) |
| `/profile/{slug}` | None | Legacy redirect to `/lt/{ipns_name}` |
| `/api/stripe/webhook` | FastAPI | Stripe event handler (no UI) |

### Component Library (`components.py`)

| Component | Usage |
|-----------|-------|
| `form_field(label, placeholder, password)` | Styled input with label |
| `style_page(title)` | Global CSS setup (dark base bg, content fade-in) |
| `image_with_text(src, text)` | Image with overlay text |
| `dashboard_header(moniker, member_type, ...)` | Gradient header bar with moniker, badge, controls |
| `dashboard_nav()` | Bottom navigation bar (4 icons) |
| `hide_dashboard_chrome(header)` / `show_dashboard_chrome(header)` | Toggle header/nav visibility |

### Dashboard Navigation Icons

| Icon | Route | Feature |
|------|-------|---------|
| `badge` | `/profile/edit` | Links & profile editing |
| `palette` | `/settings` | Theme & wallet settings |
| `collections` | `/card/case` | NFC card collection |
| `qr_code` | `/qr` | Personal QR code |

---

## 12. Theme System

### 12-Color Palette

Every user has 12 stored colors — 6 for light mode, 6 for dark mode:

| Role | Light Key | Dark Key | Purpose |
|------|-----------|----------|---------|
| Primary | `accent_color` | `dark_accent_color` | Buttons, badges, highlights |
| Secondary | `link_color` | `dark_link_color` | Link text, secondary accents |
| Text | `text_color` | `dark_text_color` | Body text |
| Background | `bg_color` | `dark_bg_color` | Page background |
| Card | `card_color` | `dark_card_color` | Card/container backgrounds |
| Border | `border_color` | `dark_border_color` | Borders, dividers |

### Theme Application (`theme.py`)

`apply_theme()` injects CSS custom properties and Quasar CSS variables into the page:

```python
def apply_theme(primary, secondary, text, bg, card, border):
    # Sets --q-primary, --q-secondary, body background, text color,
    # card background, border color via ui.run_javascript()
```

`load_and_apply_theme()` loads colors from DB and calls `apply_theme()` — used on page load for non-settings pages.

### Settings Page Live Preview

The settings page has a live preview card that updates in real-time as colors are picked:
- 6 color swatches per palette (light and dark)
- Dark/light toggle switch
- Preview card showing moniker, badge, and link text
- SAVE button persists to DB + regenerates all QR codes + republishes linktree

---

## 13. QR Code Generation

### Core Generator (`qr_gen.py`)

`generate_user_qr(url, avatar_path, fg_hex, bg_hex)` produces a branded QR code:
- **Error correction:** HIGH (allows center image)
- **Style:** Rounded module drawer
- **Color:** User's accent (foreground) and background colors
- **Center image:** Embedded avatar (or placeholder)
- **Output:** PNG bytes

### QR Variants

| Type | Function | Center Image | Extra |
|------|----------|-------------|-------|
| Profile QR | `regenerate_qr()` | User avatar | Pinned to IPFS |
| Link QR | `generate_link_qr()` | User avatar | Per-link, pinned to IPFS |
| Denom QR | `generate_denom_wallet_qr()` | User avatar | Denomination badge overlay |
| Receive QR | Inline in settings | `stellar_logo.png` | Base64 data URI (no IPFS) |

### Regeneration Triggers

QR codes are regenerated when any of these change:
- Avatar image
- Color palette (accent or background)
- Dark mode toggle
- Link URL

---

## 14. Email Service

### Provider

Mailtrap (transactional email API), configured via `MAILTRAP_API_TOKEN`.

**Sender:** `noreply@heavymeta.art` / "Heavymeta Collective"

### Email Types (`email_service.py`)

| Email | Trigger | Recipients |
|-------|---------|-----------|
| Welcome | All new enrollments (free + coop) | New member |
| Launch Key | User generates launch credentials on `/launch` | Coop member |

The launch key email contains the user's Stellar secret key (lock key) for their Pintheon node — this is the only time a key is delivered outside the app.

---

## 15. Launch Credentials

The `/launch` page allows coop members to generate credentials for running a Pintheon node.

### Flow (`launch.py`)

```
User clicks "Generate Launch Credentials" on /launch
  → Fetch user + encrypted_token from DB
  → Decrypt user secret (Guardian + Banker)
  → Generate lock keypair (Keypair.random())
  → Convert to X25519 (Stellar25519KeyPair)
  → Build launch token:
      StellarSharedKeyTokenBuilder(
          senderKeyPair=BANKER_25519,
          receiverPub=lock_25519.public_key(),
          token_type=TokenType.SECRET,
          caveats={'network': NET},
          secret=user_keys.secret,
      )
  → Email lock key (secret) to user
  → Return serialized launch token (displayed in UI)
```

**Key insight:** The launch token is NOT delivered at enrollment. It's a separate, deliberate action. The user needs both the token (displayed in-app) and the key (emailed) to start their Pintheon node.

---

## 16. Adjacent Repos & Bindings

### hvym_stellar (`../hvym_stellar`)

Installed as editable: `uv pip install -e ../hvym_stellar`

**Key exports used by this app:**

| Class/Function | Used In | Purpose |
|----------------|---------|---------|
| `Stellar25519KeyPair` | config.py, enrollment.py, launch.py | Convert Ed25519 → X25519 for ECDH |
| `StellarSharedKey` | enrollment.py | Encrypt user secrets (Banker→Guardian) |
| `StellarSharedDecryption` | launch.py, main.py | Decrypt user secrets (Guardian + Banker pub) |
| `StellarSharedKeyTokenBuilder` | launch.py | Build launch tokens |
| `StellarSharedAccountTokenBuilder` | wallet_ops.py | Create denomination wallet tokens |
| `TokenType` | launch.py | Enum for token types (SECRET) |

### pintheon_contracts (`../pintheon_contracts`)

Bindings installed as editable: `uv pip install -e ../pintheon_contracts/bindings`

**Used via:** `bindings.hvym_roster.Client` in `stellar_ops.py`

```python
client = RosterClient(contract_id=CONTRACTS["hvym_roster"], rpc_url=RPC_URL)
tx = client.join(caller=pub, name=moniker, canon=data, source=pub, signer=kp)
tx.simulate()
tx.sign_and_submit()
```

---

## 17. Testing

### Test Files

| File | Coverage |
|------|----------|
| `test_auth.py` | Password hashing, login validation, rate limiting |
| `test_enrollment.py` | Free + paid enrollment flows, IPNS setup |
| `test_payments.py` | Payment record creation, status updates |
| `test_pricing.py` | XLM price fetch, caching, Stripe pricing |
| `test_stellar_ops.py` | Account funding, balance queries |
| `test_ipfs_client.py` | IPFS add/cat/pin/unpin, IPNS lifecycle |

### Running Tests

```bash
uv run pytest tests/                              # All tests
uv run pytest tests/test_auth.py -v               # Single file
uv run pytest tests/ --cov=. --cov-report=term    # With coverage
```

---

## 18. Key Patterns & Conventions

### Async Everywhere

All I/O is async: database queries (`aiosqlite`), HTTP requests (`httpx` for Kubo, Horizon SDK), Stripe API calls. NiceGUI page handlers are `async def`.

**Exception:** `stellar_ops.py` functions (`get_xlm_balance`, `send_xlm`, `fund_account`) are synchronous because the Stellar SDK's `Server` class is synchronous. These are called from async handlers but execute quickly.

### Fire-and-Forget Republish

When a profile change should update the public linktree, `ipfs_client.schedule_republish(user_id)` launches a background asyncio task. The UI responds immediately; IPNS publishing happens asynchronously.

### User Secret Decryption Pattern

Wherever a user's Stellar keypair is needed from the database:

```python
decryptor = StellarSharedDecryption(GUARDIAN_25519, BANKER_25519.public_key())
enc = user['encrypted_token']
if isinstance(enc, str):
    enc = enc.encode()
secret = decryptor.decrypt(enc, from_address=BANKER_KP.public_key)
if isinstance(secret, bytes):
    secret = secret.decode()
user_kp = Keypair.from_secret(secret)
```

This pattern is used in `launch.py` and the settings wallet send dialog.

### Denomination Wallet Tokens vs Raw Decryption

Denomination wallets use `StellarSharedAccountTokenBuilder` (token-based key derivation). The user's main wallet uses raw `StellarSharedDecryption`. These are different cryptographic paths — do not interchange them.

### IPFS Asset Lifecycle

Every IPFS-stored asset follows: **pin new → unpin old → update DB CID**. The `replace_asset()` helper encapsulates this. Never leave orphaned CIDs pinned.

### Color Column Convention

The 12 color columns in `profile_colors` follow the pattern:
- Light: `{role}_color` (e.g., `accent_color`)
- Dark: `dark_{role}_color` (e.g., `dark_accent_color`)

`db._COLOR_COLS` contains the full list, used for bulk read/write operations.

### Route Guards

Every authenticated page starts with:
```python
if not require_auth():
    return
```

Coop-only pages add:
```python
if not require_coop():
    return
```

These guards handle redirect and return `False` to short-circuit the page handler.
