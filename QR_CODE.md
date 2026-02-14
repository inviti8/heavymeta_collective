# QR Card Mode — Planning Doc

## Overview

QR Card Mode adds a second card type to the card editor (`/card/editor`). While NFC cards
have fully custom front + back artwork, QR cards have a **server-generated front**
(user color background + linktree QR code) and a **user-uploaded back** image.

- Single slot per user (upsert, not multi-card like NFC)
- Same payment/checkout flow pattern, but separate tier entitlements
- Minimum order quantity: 50 cards

---

## Data Model

### `qr_cards` Table
```sql
CREATE TABLE IF NOT EXISTS qr_cards (
    user_id         TEXT PRIMARY KEY REFERENCES users(id),
    front_image_cid TEXT,
    back_image_cid  TEXT,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```
`user_id` as PK enforces single-slot.

### `card_orders` Extensions
- `card_type TEXT DEFAULT 'nfc'` — `'nfc'` or `'qr'`
- `quantity INTEGER DEFAULT 1` — for QR cards (min 50)

---

## Tier Entitlements

| Tier           | `qr_cards_included` | `qr_card_price_usd` |
|----------------|---------------------|----------------------|
| free           | 0                   | $4.99                |
| spark          | 50                  | $2.99                |
| forge          | 50                  | $2.49                |
| founding_forge | 100                 | $1.99                |
| anvil          | 200                 | $1.49                |

---

## QR Card Front Generation (`qr_gen.py`)

### `generate_qr_card_front(qr_png_bytes, bg_hex, card_width=856, card_height=540)`
1. Create 856x540 RGBA image filled with `bg_hex`
2. Open `qr_png_bytes` as PIL Image
3. Scale QR to 80% of card height, maintain aspect ratio
4. Paste centered on background
5. Return PNG bytes

### `regenerate_qr_card_front(user_id)` (async)
1. Load style via `_load_qr_style(user_id)` (colors, avatar, dark mode)
2. Build profile URL from moniker slug
3. Generate QR via `generate_user_qr(url, avatar_path, fg, bg)`
4. Generate composite via `generate_qr_card_front(qr_bytes, bg)`
5. Pin to IPFS via `replace_asset`, upsert to `qr_cards.front_image_cid`
6. Cleanup temp avatar file

Front auto-regenerates when user changes:
- Avatar (via profile edit `process_avatar_upload`)
- Colors/dark mode (via settings `save_settings`)

---

## Editor UI (`card_scene.js`)

- **Toggle button** — upper-left corner, pill shape, z-6000. Shows `NFC` or `QR`.
  Clicks hidden `#card-mode-trigger` to round-trip through Python.
- **Mode-aware upload** — in hold handler, blocks front-face upload when
  `cardMode === 'qr'` (front is server-generated). Back face upload works in both modes.
- **Texture switching** — `window.setCardMode(mode)` exposed for Python to call.
  Updates label + swaps cached textures.
- **Data attributes** on `#card-scene`: `data-card-mode`, `data-qr-front-texture`,
  `data-qr-back-texture`.

---

## Card Editor Integration (`main.py`)

### Mode Toggle
- Hidden button `#card-mode-trigger` toggles `current_mode` between 'nfc'/'qr'
- Persisted in `app.storage.user['card_editor_mode']`
- Calls `window.setCardMode()` and `window.updateCardTexture()` to swap textures

### Upload Branching
- `current_mode == 'qr'` and `face == 'front'` → return early (no-op)
- `current_mode == 'qr'` and `face == 'back'` → save to `qr_cards` via `upsert_qr_card`
- `current_mode == 'nfc'` → existing NFC logic

### Checkout Branching
- `current_mode == 'qr'` → validate QR front+back exist, check entitlement, route to
  `_open_qr_card_checkout_dialog()`
- `current_mode == 'nfc'` → existing NFC checkout logic

---

## QR Card Checkout Dialog

`_open_qr_card_checkout_dialog(user_id, qr_price_usd, remaining_entitled)`

- Quantity field (min 50, step 10, default 50)
- Dynamic price: `billable = max(0, qty - remaining_entitled)`, `total = billable * price`
- If `billable == 0` → entitled label, pay button says "ORDER (FREE)"
- CARD/XLM tabs (same pattern as NFC card payment)
- On payment (or entitled skip) → `_open_qr_shipping_dialog()`

---

## QR Card Shipping Dialog

`_open_qr_shipping_dialog(user_id, payment_method, amount_usd, quantity, tx_hash=None)`

- Label: "Where should we send your {quantity} QR cards?"
- `create_card_order(card_id=user_id, card_type='qr', quantity=quantity, ...)`
- Vendor email via `send_qr_card_order_email()`

---

## Payment Methods

### Stripe (`payments/stripe_pay.py`)
- `create_qr_card_checkout_session(email, amount_usd, quantity, user_id)`
- Product: `"Heavymeta Collective — QR Business Cards ({quantity} pcs)"`
- Success URL: `/qr-card/order/success?session_id={CHECKOUT_SESSION_ID}`
- Metadata: `purchase_type: 'qr_card'`, `user_id`, `quantity`
- Webhook returns `purchase_type == 'qr_card'` — no finalization (shipping not yet collected)

### XLM
- Same stellar payment request pattern as NFC
- On payment confirmation → QR shipping dialog with quantity

### Entitlement
- Cards covered by tier → skip payment, go directly to shipping

---

## Vendor Email (`email_service.py`)

`send_qr_card_order_email(order, user, qr_card, gateway_base)`

- Subject: `"QR Card Order — {order_id} — {moniker} — {quantity} pcs"`
- Body includes quantity, card type "QR Business Card", front/back IPFS links
- CC: `orders@heavymeta.art`

---

## Files Modified

| # | File | Change |
|---|------|--------|
| 1 | `db.py` | `qr_cards` table, `card_orders` columns, CRUD functions |
| 2 | `static/tiers.json` | `qr_cards_included`, `qr_card_price_usd` per tier |
| 3 | `qr_gen.py` | `generate_qr_card_front()`, `regenerate_qr_card_front()` |
| 4 | `static/js/card_scene.js` | Toggle button, mode-aware upload, texture switching |
| 5 | `main.py` | QR mode integration, dialogs, Stripe success, auto-regen hooks |
| 6 | `email_service.py` | `send_qr_card_order_email()` |
| 7 | `payments/stripe_pay.py` | `create_qr_card_checkout_session()`, webhook branch |
| 8 | `QR_CODE.md` | This planning doc |
