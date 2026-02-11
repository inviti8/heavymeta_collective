# Heavymeta Collective — Login & Enrollment Flow

## Status: DESIGN FINALIZED — Ready for Implementation

---

## Table of Contents

1. [Overview](#overview)
2. [Member Tiers](#member-tiers)
3. [Banker & Guardian Key Architecture](#banker--guardian-key-architecture)
4. [Enrollment Flow](#enrollment-flow)
5. [Payment Flows (Paid Tier)](#payment-flows-paid-tier)
6. [Post-Payment Processing](#post-payment-processing)
7. [Login Flow (Returning Users)](#login-flow-returning-users)
8. [Launch Token & Key Section (In-App)](#launch-token--key-section-in-app)
9. [Pintheon Node Integration](#pintheon-node-integration)
10. [User Data Storage (SQLite)](#user-data-storage-sqlite)
11. [Email Delivery (Mailtrap)](#email-delivery-mailtrap)
12. [Tech Stack Summary](#tech-stack-summary)
13. [Decisions Log](#decisions-log)

---

## Overview

The Heavymeta Collective onboarding site serves as:

- **Enrollment portal** — free and paid membership tiers
- **Profile / Link-tree editor** — customizable public page per member
- **NFC card configurator** — paid members upload image for custom NFC card (future section)
- **Launch Token portal** — paid members generate their Pintheon node credentials (in-app section)

Authentication is **email + password** for all site interactions. Launch tokens and keys
for Pintheon node access are generated in a dedicated in-app section, separate from
enrollment.

---

## Member Tiers

Two tiers to accommodate both web2 expectations and crypto-native value:

| Feature | Free | Paid (Coop Member) |
|---------|------|--------------------|
| Link-tree page | Yes | Yes |
| Custom NFC card | No | Yes |
| Pintheon node credentials | No | Yes |
| Stellar abstracted account | No | Yes |
| Roster contract registration | No | Yes |
| Cost | $0 | 333 XLM (crypto) / ~2x USD (Stripe) |

### UI Behavior

- Free users see their link-tree editor and a persistent **"Join the Coop"** upgrade
  CTA that leads to the payment flow
- Paid members see the full app: link-tree, NFC card section, and Pintheon launch section

---

## Banker & Guardian Key Architecture

### Concept

The app holds two Stellar keypairs at the server level:

| Key | Role | Analogy |
|-----|------|---------|
| **Banker Key** | Funds new accounts, signs transactions | Treasury / Custodian |
| **Guardian Key** | Encrypts user secrets alongside Banker | Vault co-signer |

Together they form a **dual-key encryption scheme** using `hvym_stellar`'s shared key
cryptography (`StellarSharedKey`). Neither key alone can decrypt user secrets.

**Both keys are required at server startup. The app must fail to start if either is
missing.**

### How It Works

```
Banker (sender)  +  Guardian (receiver pub)
        ↓                    ↓
  StellarSharedKey(Banker_25519, Guardian_25519.pub)
        ↓
  ECDH shared secret = X25519(Banker_priv, Guardian_pub)
        ↓
  encrypt(user_stellar_secret)  →  encrypted_token (stored in DB)
```

To decrypt:
```
StellarSharedDecryption(Guardian_25519, Banker_25519.pub)
        ↓
  decrypt(encrypted_token)  →  user_stellar_secret
```

### Encryption Detail (hvym_stellar internals)

`StellarSharedKey.encrypt()` uses a signature-based hybrid scheme:
1. Generates fresh salt (32 bytes) + nonce (24 bytes)
2. Derives base key: `SHA256(salt + ECDH_shared_secret)`
3. Signs `salt||nonce` with sender's Ed25519 key → 64-byte signature
4. Derives box keys from signature halves
5. Encrypts with NaCl Box
6. Output: `base64(salt)|base64(nonce)|base64(signature)|hex(ciphertext)`

### Key Storage

**Development:** Split `.env` files (both in `.gitignore`)

```
# .env  (primary, always loaded)
BANKER_SECRET=SXXX...
BANKER_PUBLIC=GXXX...
GUARDIAN_SECRET=SXXX...
GUARDIAN_PUBLIC=GXXX...
```

**Production:** Environment variables injected via deployment platform (Render, Railway,
etc.) with encrypted GPG cold backups stored offline. Guardian key should ideally be
injected from a separate secret store or mount point.

### Startup Validation

```python
# config.py — fail fast if keys are missing
BANKER_SECRET = os.environ["BANKER_SECRET"]      # KeyError = crash
GUARDIAN_SECRET = os.environ["GUARDIAN_SECRET"]    # KeyError = crash

BANKER_KP = Keypair.from_secret(BANKER_SECRET)
GUARDIAN_KP = Keypair.from_secret(GUARDIAN_SECRET)
BANKER_25519 = Stellar25519KeyPair(BANKER_KP)
GUARDIAN_25519 = Stellar25519KeyPair(GUARDIAN_KP)
```

---

## Enrollment Flow

### /join Page — Full UI Wireframe

The join page has a single form with a tier selector and a payment method toggle.
When the user selects "Coop Member", the payment section appears with a switch to
choose between XLM and Stripe.

```
┌─────────────────────────────────────────────────────────────────┐
│  /join                                                          │
│                                                                 │
│  JOIN                                          Already          │
│                                                Registered?      │
│                                                Login >          │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  MONIKER                                                  │  │
│  │  [ Create a moniker                              ]        │  │
│  │                                                           │  │
│  │  EMAIL                                                    │  │
│  │  [ Enter your email                              ]        │  │
│  │                                                           │  │
│  │  PASSWORD                                                 │  │
│  │  [ Create a password                             ]        │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  MEMBERSHIP TIER                                          │  │
│  │                                                           │  │
│  │  ┌─────────────────────┐  ┌─────────────────────────────┐ │  │
│  │  │  ○  FREE            │  │  ○  COOP MEMBER             │ │  │
│  │  │     Link-tree       │  │     Full access + NFC card  │ │  │
│  │  │                     │  │     Pintheon node            │ │  │
│  │  └─────────────────────┘  └─────────────────────────────┘ │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ══════════════════════════════════════════════════════════════  │
│  (Payment section — ONLY visible when "Coop Member" selected)   │
│  ══════════════════════════════════════════════════════════════  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  PAYMENT METHOD                                           │  │
│  │                                                           │  │
│  │          ┌──────────┐                                     │  │
│  │    XLM   │ ○──────  │  CARD                               │  │
│  │          └──────────┘                                     │  │
│  │    (toggle switch — XLM default, left position)           │  │
│  │                                                           │  │
│  │  ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄  │  │
│  │                                                           │  │
│  │  ─── When XLM selected (default): ───────────────────     │  │
│  │                                                           │  │
│  │  PRICE: 333 XLM  (~$XXX.XX USD)                          │  │
│  │                                                           │  │
│  │  [ SIGN UP — PAY 333 XLM ]                               │  │
│  │                                                           │  │
│  │  → on click: validate form, create account,               │  │
│  │    navigate to /join/pay/xlm (QR code + polling page)     │  │
│  │                                                           │  │
│  │  ─── When CARD selected: ────────────────────────────     │  │
│  │                                                           │  │
│  │  PRICE: $XXX.XX USD  (2x crypto price)                   │  │
│  │  "Join the future. Pay less with crypto."                 │  │
│  │                                                           │  │
│  │  [ SIGN UP — PAY $XXX.XX ]                               │  │
│  │                                                           │  │
│  │  → on click: validate form, create pending account,       │  │
│  │    redirect to Stripe Checkout                            │  │
│  │                                                           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ── When FREE selected, no payment section: ─────────────────   │
│                                                                 │
│  [ SIGN UP — FREE ]                                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### NiceGUI Implementation Notes

```python
# Toggle switch component
payment_method = ui.switch('XLM').classes('...')
# switch.value = True → XLM, False → Card

# Reactive payment section — show/hide based on tier + toggle
tier = ui.radio(['free', 'coop'], value='free')

# When tier == 'coop', show payment section
# When payment_method.value == True → XLM panel
# When payment_method.value == False → Stripe panel
# Use ui.bind_visibility or @ui.refreshable for reactivity
```

### Form Validation (all tiers)

- **Moniker:** Max 100 chars, uniqueness check against DB
- **Email:** Format + deliverability via `email-validator`
- **Password:** Min 8 chars, hashed with argon2 before storage
- Validation runs on submit, errors shown inline

### Free Tier Processing

1. Validate form fields
2. Check moniker + email uniqueness
3. Hash password with argon2
4. Store user record in SQLite with `member_type = 'free'`
5. No Stellar account created, no payment
6. Send welcome email via Mailtrap
7. Auto-login, redirect to `/profile/edit`

### Paid Tier Processing

Same form validation, then route to payment flow based on toggle state.

---

## Payment Flows (Paid Tier)

### Current State: Nothing Exists

There is **no Stripe or Stellar payment code** in the repo. The current codebase is:
- `main.py` — NiceGUI page skeletons (landing, join, login, profile edit)
- `components.py` — form fields, styling helpers
- `requirements.txt` — NiceGUI + basic deps only
- No `stripe` package, no Stellar SDK, no payment logic

Everything in this section must be built from scratch.

### Dynamic Pricing

Stripe price is **literally 2x the XLM market value**. This requires a live XLM/USD
price feed.

```python
# payments/pricing.py

import requests
from functools import lru_cache
import time

XLM_COST = 333  # Fixed XLM amount for crypto natives
_price_cache = {'price': None, 'timestamp': 0}
CACHE_TTL = 300  # 5 minutes

def fetch_xlm_price():
    """Fetch current XLM/USD price. Cached for 5 minutes."""
    now = time.time()
    if _price_cache['price'] and (now - _price_cache['timestamp']) < CACHE_TTL:
        return _price_cache['price']

    resp = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": "stellar", "vs_currencies": "usd"}
    )
    price = resp.json()["stellar"]["usd"]
    _price_cache['price'] = price
    _price_cache['timestamp'] = now
    return price

def get_xlm_usd_equivalent():
    """Returns the USD equivalent of 333 XLM."""
    return round(XLM_COST * fetch_xlm_price(), 2)

def get_stripe_price_cents():
    """Returns Stripe price in USD cents (2x the XLM cost in USD)."""
    xlm_usd = fetch_xlm_price()
    stripe_usd = XLM_COST * xlm_usd * 2
    return int(stripe_usd * 100)

def get_stripe_price_display():
    """Returns formatted Stripe price string, e.g. '$253.08'."""
    cents = get_stripe_price_cents()
    return f"${cents / 100:.2f}"
```

### XLM Payment Flow — /join/pay/xlm

After form validation + account creation, the user navigates to a dedicated payment
page that shows the QR code and polls for payment.

```
┌──────────────────────────────────────────────────────────────┐
│  /join/pay/xlm                                               │
│                                                              │
│  COMPLETE YOUR PAYMENT                                       │
│                                                              │
│  Send exactly 333 XLM to:                                    │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │                                                        │  │
│  │          ┌──────────────────────┐                      │  │
│  │          │                      │                      │  │
│  │          │     [ QR CODE ]      │                      │  │
│  │          │   (Stellar pay URI)  │                      │  │
│  │          │                      │                      │  │
│  │          └──────────────────────┘                      │  │
│  │                                                        │  │
│  │  Address: GXXX...XXXX              [ COPY ]            │  │
│  │  Amount:  333 XLM                                      │  │
│  │  Memo:    hvym-collective-a1b2c3d4  [ COPY ]           │  │
│  │                                                        │  │
│  │  ⏳ Waiting for payment...                              │  │
│  │  (checking every 5 seconds)                            │  │
│  │                                                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  ─── On payment detected: ─────────────────────────────────  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Payment confirmed!                                    │  │
│  │  Tx: [link to stellar.expert]                          │  │
│  │                                                        │  │
│  │  [ CONTINUE TO YOUR PROFILE → ]                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

#### Stellar Payment Backend

```python
# payments/stellar_pay.py

from stellar_sdk import Server
from config import BANKER_PUB, HORIZON_URL, BLOCK_EXPLORER, NET
import uuid

XLM_COST = "333"
server = Server(horizon_url=HORIZON_URL)

def create_stellar_payment_request():
    """Generate payment details for XLM payment."""
    order_id = str(uuid.uuid4())[:8]
    memo = f"hvym-collective-{order_id}"

    stellar_uri = (
        f"web+stellar:pay"
        f"?destination={BANKER_PUB}"
        f"&amount={XLM_COST}"
        f"&asset_code=XLM"
        f"&memo={memo}"
    )

    # Generate QR code (same style as Anvil app)
    qr_data_uri = generate_stellar_qr(stellar_uri)

    return {
        'order_id': order_id,
        'memo': memo,
        'uri': stellar_uri,
        'qr': qr_data_uri,
        'address': BANKER_PUB,
        'amount': XLM_COST,
    }

def check_payment(expected_memo):
    """Check if a payment with the expected memo has been received."""
    ops = server.operations().for_account(BANKER_PUB).limit(10).order(desc=True).call()
    for op in ops["_embedded"]["records"]:
        tx = server.transactions().transaction(op["transaction_hash"]).call()
        if tx.get("memo") == expected_memo:
            return {
                'paid': True,
                'hash': tx["hash"],
                'url': f'{BLOCK_EXPLORER}/tx/{tx["hash"]}'
            }
    return {'paid': False}
```

#### Polling in NiceGUI

```python
# In the /join/pay/xlm page handler
import asyncio

async def poll_for_payment(memo, status_label, success_container):
    """Poll every 5 seconds until payment is detected."""
    while True:
        result = check_payment(memo)
        if result['paid']:
            status_label.set_text('Payment confirmed!')
            # Trigger post-payment processing
            await process_paid_enrollment(...)
            success_container.set_visibility(True)
            return
        await asyncio.sleep(5)

# Start polling as a background task when page loads
ui.timer(5.0, lambda: check_and_update())
```

### Stripe Payment Flow

#### Backend — Checkout Session + Webhook

```python
# payments/stripe_pay.py

import stripe
from config import STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
from payments.pricing import get_stripe_price_cents, fetch_xlm_price

stripe.api_key = STRIPE_SECRET_KEY

def create_checkout_session(order_id, email, moniker, user_id):
    """Create a Stripe Checkout session with dynamic 2x pricing."""
    price_cents = get_stripe_price_cents()
    xlm_price = fetch_xlm_price()

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'unit_amount': price_cents,
                'product_data': {
                    'name': 'Heavymeta Collective — Coop Membership',
                    'description': 'Full access membership with NFC card and Pintheon node',
                },
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url=f'/join/success?session_id={{CHECKOUT_SESSION_ID}}',
        cancel_url='/join',
        customer_email=email,
        metadata={
            'order_id': order_id,
            'user_id': user_id,
            'moniker': moniker,
            'xlm_price_usd': str(xlm_price),
        },
    )
    return session

def handle_webhook(payload, sig_header):
    """Handle Stripe webhook for checkout.session.completed."""
    event = stripe.Webhook.construct_event(
        payload, sig_header, STRIPE_WEBHOOK_SECRET
    )

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session['metadata']['user_id']
        order_id = session['metadata']['order_id']
        # Complete the enrollment
        finalize_paid_enrollment(
            user_id=user_id,
            order_id=order_id,
            payment_method='stripe',
            tx_hash=session['payment_intent'],
        )

    return {'status': 'ok'}
```

#### Webhook Route (FastAPI integration)

NiceGUI runs on FastAPI under the hood. We add the webhook route directly:

```python
# In main.py or a separate routes file
from fastapi import Request, HTTPException

@app.post('/api/stripe/webhook')
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    try:
        return handle_webhook(payload, sig_header)
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail='Invalid signature')
```

#### Stripe Flow Sequence

```
User clicks "SIGN UP — PAY $XXX.XX"
        │
        ▼
Server: validate form → create user (member_type='coop', status='pending')
        │
        ▼
Server: create_checkout_session() → returns session.url
        │
        ▼
Client: redirect to Stripe hosted checkout (session.url)
        │
        ▼
User completes payment on Stripe
        │
        ├── Stripe sends webhook → /api/stripe/webhook
        │   Server: finalize_paid_enrollment()
        │   (generate Stellar keypair, fund, encrypt, roster, email)
        │
        ▼
User redirected to /join/success?session_id=...
        │
        ▼
Server: verify session is paid, show success UI
        │
        ▼
Auto-login → redirect to /profile/edit
```

### /join/success — Payment Success Page

Shared success page for both payment methods:

```
┌──────────────────────────────────────────────────────────┐
│  /join/success                                           │
│                                                          │
│  WELCOME TO THE COLLECTIVE                               │
│                                                          │
│  Your membership is confirmed.                           │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Node Address: GXXX...XXXX                         │  │
│  │  Network: testnet                                  │  │
│  │  Funded: 22 XLM                                    │  │
│  │  Payment: [tx link]  (Stellar only)                │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  A welcome email has been sent to your inbox.            │
│                                                          │
│  [ GO TO YOUR PROFILE → ]                                │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## Post-Payment Processing

Once payment is confirmed (either Stellar or Stripe), the server creates the user's
Stellar infrastructure. **Launch token and key are NOT delivered here** — they are
generated later in the in-app Launch section.

```python
def process_paid_enrollment(email, moniker, password_hash, order_id, payment_method, tx_hash):
    """Called after payment confirmation for paid tier members."""

    # 1. Generate user's Stellar keypair (abstracted account)
    user_keys = Keypair.random()
    user_25519 = Stellar25519KeyPair(user_keys)

    # 2. Fund user account from Banker (22 XLM)
    #    This covers Pintheon node startup costs:
    #    - Stellar account activation (~2 XLM minimum)
    #    - join_collective() transaction
    #    - deploy_node_token() transaction
    #    - Initial pinning and file operations
    fund_account(user_keys.public_key, fund_amount="22")

    # 3. Encrypt user secret for server-side storage
    #    Using Banker + Guardian dual-key scheme
    encryptor = StellarSharedKey(BANKER_25519, GUARDIAN_25519.public_key())
    encrypted_secret = encryptor.encrypt(user_keys.secret.encode())

    # 4. Store user record
    user_id = str(uuid.uuid4())
    store_user(
        user_id=user_id,
        email=email,
        moniker=moniker,
        member_type='coop',
        password_hash=password_hash,
        stellar_address=user_keys.public_key,
        shared_pub=user_25519.public_key(),
        encrypted_token=encrypted_secret,
    )

    # 5. Store payment record
    store_payment(
        user_id=user_id,
        method=payment_method,  # 'stellar' or 'stripe'
        amount=str(XLM_COST) if payment_method == 'stellar' else str(stripe_amount),
        memo=order_id,
        tx_hash=tx_hash,
        status='completed',
    )

    # 6. Register on hvym-roster contract
    register_on_roster(user_keys, moniker)

    # 7. Send welcome email via Mailtrap
    send_welcome_email(email, moniker, user_keys.public_key)

    return user_id
```

### What happens at enrollment (paid):
- Stellar keypair generated and funded (22 XLM from Banker)
- Secret encrypted with Banker+Guardian and stored in SQLite
- User registered on hvym-roster contract
- Welcome email sent (NO launch key/token yet)
- User redirected to `/profile/edit`

### What does NOT happen at enrollment:
- Launch token generation (deferred to in-app section)
- Launch key email delivery (deferred to in-app section)
- NFC card customization (separate app section, future task)

---

## Login Flow (Returning Users)

Email + password authentication for all site interactions.

```
┌──────────────────────────────────────────┐
│  /login                                  │
│                                          │
│  1. User enters email + password         │
│  2. Server verifies against argon2 hash  │
│  3. On success:                          │
│     • Set session via app.storage.user   │
│     • Redirect to /profile/edit          │
│  4. On failure:                          │
│     • Show error, allow retry            │
│     • Rate limit after N attempts        │
└──────────────────────────────────────────┘
```

### Session Management

NiceGUI's built-in `app.storage.user` (cookie-backed, server-side storage):

```python
from nicegui import app

# On login success:
app.storage.user['authenticated'] = True
app.storage.user['user_id'] = user_id
app.storage.user['moniker'] = moniker
app.storage.user['member_type'] = member_type  # 'free' or 'coop'

# Route guard:
def require_auth():
    if not app.storage.user.get('authenticated'):
        ui.navigate.to('/login')
        return False
    return True

def require_coop():
    """Guard for paid-only sections."""
    if not require_auth():
        return False
    if app.storage.user.get('member_type') != 'coop':
        ui.navigate.to('/upgrade')
        return False
    return True
```

### Password Hashing

```python
from passlib.hash import argon2

# On signup:
password_hash = argon2.hash(password)

# On login:
if argon2.verify(password, stored_hash):
    # success
```

---

## Launch Token & Key Section (In-App)

This is a **dedicated section within the app** for paid Coop members. It is NOT part of
the enrollment flow. Users access it after logging in.

### Purpose

Provides the credentials needed to launch a Pintheon node:
- **Launch Token** — contains the user's encrypted Stellar account secret
- **Launch Key** — the decryption key, delivered via email

### Route: `/launch`

```
┌───────────────────────────────────────────────────────────┐
│  /launch  (requires coop membership)                      │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  YOUR PINTHEON NODE CREDENTIALS                     │  │
│  │                                                     │  │
│  │  Status: [ Not Generated / Generated / Active ]     │  │
│  │                                                     │  │
│  │  [ GENERATE LAUNCH CREDENTIALS ]                    │  │
│  │                                                     │  │
│  │  On click:                                          │  │
│  │  1. Server generates lock keypair                   │  │
│  │  2. Builds launch token (Banker → lock key)         │  │
│  │  3. Emails launch key to user's email               │  │
│  │  4. Displays launch token in UI                     │  │
│  │                                                     │  │
│  │  ┌───────────────────────────────────────────────┐  │  │
│  │  │  LAUNCH TOKEN (copy this):                    │  │  │
│  │  │  [========= long token string ==========]     │  │  │
│  │  │  [ COPY TO CLIPBOARD ]                        │  │  │
│  │  │                                               │  │  │
│  │  │  Launch Key has been sent to your email.      │  │  │
│  │  │  You will need BOTH to launch your node.      │  │  │
│  │  └───────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  Node Address: GXXX...                                    │
│  Network: testnet                                         │
│  Funded: 22 XLM                                           │
│  Explorer: [link to stellar.expert]                       │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

### Token Generation Logic

```python
def generate_launch_credentials(user_id):
    """Generate launch token + key for a paid member. Called from /launch."""

    # 1. Retrieve user's encrypted secret from DB
    user = get_user(user_id)

    # 2. Decrypt user's Stellar secret using Banker+Guardian
    decryptor = StellarSharedDecryption(GUARDIAN_25519, BANKER_25519.public_key())
    user_secret = decryptor.decrypt(user.encrypted_token)
    user_keys = Keypair.from_secret(user_secret.decode())

    # 3. Generate lock keypair (launch key)
    lock_keys = Keypair.random()
    lock_25519 = Stellar25519KeyPair(lock_keys)

    # 4. Build launch token
    #    Sender: Banker, Receiver: lock key's public
    #    Secret: user's Stellar secret
    caveats = {'network': NET}
    token = StellarSharedKeyTokenBuilder(
        senderKeyPair=BANKER_25519,
        receiverPub=lock_25519.public_key(),
        token_type=TokenType.SECRET,
        caveats=caveats,
        secret=user_keys.secret
    )
    launch_token = token.serialize()

    # 5. Email launch key
    send_launch_key_email(user.email, lock_keys.secret, user_keys.public_key)

    return launch_token
```

### How the user uses these in Pintheon

The Pintheon node's `/new_node` endpoint receives both the launch token and launch key.
It verifies using `StellarSharedKeyTokenVerifier`:

```python
# Inside Pintheon (pintheonMachine/__init__.py)
def launch_token_verifier(self, launch_key, launch_token):
    lock_keys = Keypair.from_secret(launch_key.strip())
    lock_kp = Stellar25519KeyPair(lock_keys)
    caveats = {'network': 'testnet'}
    return StellarSharedKeyTokenVerifier(
        lock_kp, launch_token.strip(),
        token_type=TokenType.SECRET, caveats=caveats
    )
# If valid → extracts the Stellar seed → node is initialized
```

---

## Pintheon Node Integration

### What the 22 XLM funds

The Stellar account funded at enrollment is consumed by the Pintheon node during setup:

| Operation | Contract | Approximate Cost |
|-----------|----------|------------------|
| Account activation | Stellar native | ~2 XLM minimum balance |
| `join_collective()` | hvym_collective | Transaction fee + join_fee stroops |
| `deploy_node_token()` | hvym_collective | Transaction fee |
| Pin service operations | hvym_pin_service | `(offer_price * pin_qty) + pin_fee` |
| File publishing | hvym_collective | Transaction fee per publish |
| Ongoing operations | Various | Transaction fees |

### Pintheon Node Launch Sequence

After the user provides launch token + key to their Pintheon node:

1. **Token verification** — `StellarSharedKeyTokenVerifier` validates and extracts seed
2. **Keypair reconstruction** — `Keypair.from_secret(extracted_seed)`
3. **Balance check** — Requires >= 22 XLM
4. **`join_collective()`** — Registers node in the HVYM Collective contract
5. **`deploy_node_token()`** — Deploys a unique node token contract on Soroban
6. **Node established** — Transitions to `idle` state, ready for IPFS + token operations

### Contract Addresses (Testnet)

```python
CONTRACTS = {
    "hvym_roster":    "CC4AWAEY5UMWYGI5WZIFG4EQZVVQMPZFFBVX4JOLISLDWZ5G4H4EDTAJ",
    "hvym_collective":"CAYD2PS5KR4VSEQPQZEUDF3KHT2NDWTGVXAHPPMLLS4HHM5ARUNALFUU",
    "opus_token":     "CB3MM62JMDTNVJVOXORUOOPBFAWVTREJLA5VN4YME4MBNCHGBHQPQH7G",
    "hvym_pin_service":"CCEDYFIHUCJFITWEOT7BWUO2HBQQ72L244ZXQ4YNOC6FYRDN3MKDQFK7",
}
```

### Roster Registration (at enrollment)

At enrollment time, we register the user on the **hvym-roster** contract. This is the
Collective's membership ledger, separate from the Pintheon collective contract the node
joins later.

```python
from hvym_roster.bindings import Client as RosterClient

def register_on_roster(user_keys, moniker):
    client = RosterClient(
        contract_id=CONTRACTS["hvym_roster"],
        rpc_url=RPC_URL,
    )
    canon_data = json.dumps({"type": "coop_member"}).encode()
    tx = client.join(
        caller=user_keys.public_key,
        name=moniker.encode(),
        canon=canon_data,
        source=user_keys.public_key,
        signer=user_keys,
    )
    tx.simulate()
    return tx.sign_and_submit()
```

---

## User Data Storage (SQLite)

### Schema

```sql
CREATE TABLE users (
    id              TEXT PRIMARY KEY,        -- UUID
    email           TEXT UNIQUE NOT NULL,
    moniker         TEXT UNIQUE NOT NULL,
    member_type     TEXT NOT NULL,           -- 'free' or 'coop'
    password_hash   TEXT NOT NULL,           -- argon2
    stellar_address TEXT,                    -- Public key (NULL for free tier)
    shared_pub      TEXT,                    -- X25519 public key (NULL for free tier)
    encrypted_token TEXT,                    -- Banker+Guardian encrypted secret (NULL for free)
    nfc_image_cid   TEXT,                    -- IPFS CID for NFC card image (future)
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    network         TEXT DEFAULT 'testnet'
);

CREATE TABLE link_tree (
    id          TEXT PRIMARY KEY,            -- UUID
    user_id     TEXT REFERENCES users(id),
    label       TEXT NOT NULL,
    url         TEXT NOT NULL,
    icon_url    TEXT,
    sort_order  INTEGER DEFAULT 0
);

CREATE TABLE payments (
    id              TEXT PRIMARY KEY,        -- UUID
    user_id         TEXT REFERENCES users(id),
    method          TEXT NOT NULL,           -- 'stellar' or 'stripe'
    amount          TEXT NOT NULL,           -- XLM amount or USD cents
    xlm_price_usd   REAL,                   -- XLM/USD rate at time of payment
    memo            TEXT,                    -- Stellar memo or Stripe session ID
    tx_hash         TEXT,                    -- Stellar tx hash or Stripe payment intent ID
    status          TEXT DEFAULT 'pending',  -- 'pending', 'completed', 'failed'
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Notes

- Free tier users have NULL Stellar fields — populated on upgrade to paid
- `encrypted_token` is the Banker+Guardian encrypted Stellar secret — safe to store in
  plaintext DB because decryption requires both private keys
- `xlm_price_usd` in payments table records the rate at checkout for audit trail
- SQLite for MVP; swap to PostgreSQL later if needed with minimal changes

---

## Email Delivery (Mailtrap)

Using [Mailtrap Python SDK](https://github.com/mailtrap/mailtrap-python).

### Welcome Email (all tiers)

```python
import mailtrap as mt

def send_welcome_email(email, moniker):
    mail = mt.Mail(
        sender=mt.Address(email="noreply@heavymeta.art", name="Heavymeta Collective"),
        to=[mt.Address(email=email)],
        subject="Welcome to Heavymeta Collective",
        html=f"""
        <h1>Welcome, {moniker}!</h1>
        <p>You're now part of the Heavymeta Collective.</p>
        <p>Log in to customize your profile and link-tree.</p>
        """,
    )
    client = mt.MailtrapClient(token=MAILTRAP_API_TOKEN)
    client.send(mail)
```

### Launch Key Email (paid, from /launch section)

```python
def send_launch_key_email(email, launch_key_secret, stellar_address):
    acct_url = f"https://stellar.expert/explorer/{NET}/account/{stellar_address}"
    mail = mt.Mail(
        sender=mt.Address(email="noreply@heavymeta.art", name="Heavymeta Collective"),
        to=[mt.Address(email=email)],
        subject="Your Pintheon Launch Key",
        html=f"""
        <h1>Your Launch Key</h1>
        <p><strong>Save this securely. You need it + your Launch Token to start your
        Pintheon node.</strong></p>
        <code>{launch_key_secret}</code>
        <h3>Node Address</h3>
        <p>{stellar_address}</p>
        <a href="{acct_url}">{acct_url}</a>
        """,
    )
    client = mt.MailtrapClient(token=MAILTRAP_API_TOKEN)
    client.send(mail)
```

**API Token:** Stored in `.env` as `MAILTRAP_API_TOKEN`.

---

## Tech Stack Summary

### Current
- **Framework:** NiceGUI (Python) + FastAPI
- **Server:** Uvicorn
- **Package Manager:** `uv` (all dev, testing, and CI flows use `uv`)

### Development Environment — uv

All Python dependency management and virtual environment operations use
[uv](https://docs.astral.sh/uv/). **Do not use `pip`, `pip install`, or
`python -m venv` directly.**

#### Setup

```bash
# Create venv + install deps (from project root)
uv venv
uv pip install -r requirements.txt

# Or with pyproject.toml (preferred if we migrate):
uv sync
```

#### Adding Dependencies

```bash
# Add a package
uv pip install stripe

# Freeze current env to requirements.txt
uv pip freeze > requirements.txt

# Install from requirements.txt
uv pip install -r requirements.txt
```

#### Running the App

```bash
# Activate venv and run
# Windows:
.venv\Scripts\activate && python main.py

# Or run directly via uv:
uv run python main.py
```

#### Running Tests

```bash
# Run tests via uv
uv run pytest tests/

# Run a specific test
uv run pytest tests/test_auth.py -v

# Run with coverage
uv run pytest tests/ --cov=. --cov-report=term-missing
```

#### Local Dependencies (adjacent repos)

```bash
# Install hvym_stellar from adjacent repo in editable mode
uv pip install -e ../hvym_stellar

# Install pintheon_contracts bindings
uv pip install -e ../pintheon_contracts/bindings
```

#### CI / Deployment

All CI pipelines and deployment scripts must use `uv` for consistency:

```bash
# CI setup
pip install uv
uv venv
uv pip install -r requirements.txt
uv run pytest tests/
```

### Dependencies to Add

```bash
# All at once:
uv pip install stellar-sdk stripe mailtrap "passlib[argon2]" "qrcode[pil]" \
    aiosqlite email-validator requests python-dotenv pytest pytest-asyncio

# Adjacent repos (editable):
uv pip install -e ../hvym_stellar
uv pip install -e ../pintheon_contracts/bindings

# Freeze:
uv pip freeze > requirements.txt
```

| Component | Package | Purpose |
|-----------|---------|---------|
| Stellar SDK | `stellar-sdk` | Keypair generation, transactions, Horizon |
| hvym_stellar | `../hvym_stellar` (editable) | Shared key encryption, tokens, X25519 |
| hvym_roster bindings | `../pintheon_contracts/bindings` (editable) | Roster contract interaction |
| Stripe | `stripe` | Card payment processing |
| Mailtrap | `mailtrap` | Transactional email |
| Password hashing | `passlib[argon2]` | Secure password storage |
| QR codes | `qrcode[pil]` | Stellar payment QR generation |
| Database | `aiosqlite` | Async SQLite for NiceGUI |
| Email validation | `email-validator` | Validate email addresses |
| HTTP client | `requests` | XLM price feed (CoinGecko) |
| Env management | `python-dotenv` | Load `.env` secrets |
| Testing | `pytest`, `pytest-asyncio` | Test framework |

### File Structure

```
heavymeta_collective/
├── main.py                  # Routes and UI pages
├── components.py            # Reusable UI components
├── auth.py                  # Authentication, session management, password hashing
├── enrollment.py            # Enrollment processing (free + paid)
├── launch.py                # Launch token/key generation (in-app section)
├── payments/
│   ├── __init__.py
│   ├── stellar_pay.py       # Crypto payment flow (QR, polling)
│   ├── stripe_pay.py        # Stripe checkout + webhook
│   └── pricing.py           # XLM price feed, dynamic pricing
├── stellar_ops.py           # Banker operations, account funding, roster registration
├── email_service.py         # Mailtrap email delivery
├── db.py                    # SQLite schema, queries, migrations
├── config.py                # App configuration, constants, key loading
├── tests/                   # Test suite (run via: uv run pytest tests/)
│   ├── __init__.py
│   ├── test_auth.py
│   ├── test_enrollment.py
│   ├── test_payments.py
│   ├── test_pricing.py
│   ├── test_stellar_ops.py
│   └── conftest.py          # Shared fixtures
├── static/
│   ├── placeholder.png
│   └── stellar_logo.png
├── data/                    # SQLite database files (gitignored)
├── .env                     # Secrets (gitignored)
├── .env.example             # Template for required env vars
├── requirements.txt         # Frozen via: uv pip freeze > requirements.txt
└── LOGIN_FLOW.md            # This document
```

### Environment Variables (`.env`)

```env
# Stellar Network — 'testnet' or 'mainnet'
STELLAR_NETWORK=testnet

# Banker (Custodian) — required at startup
BANKER_SECRET=SXXX...
BANKER_PUBLIC=GXXX...

# Guardian — required at startup
GUARDIAN_SECRET=SXXX...
GUARDIAN_PUBLIC=GXXX...

# Stripe
STRIPE_SECRET_KEY=sk_test_XXX
STRIPE_PUBLISHABLE_KEY=pk_test_XXX
STRIPE_WEBHOOK_SECRET=whsec_XXX

# Mailtrap
MAILTRAP_API_TOKEN=XXX

# App
APP_SECRET_KEY=<random-secret-for-nicegui-sessions>
DATABASE_PATH=./data/collective.db
```

### Local Development Setup

Testnet Stellar accounts and Stripe test-mode keys for local development.
**These are testnet/test-mode only — no real funds or charges.**

#### 1. Create `.env` file

```bash
cp .env.example .env
```

Populate with the local dev values:

```env
STELLAR_NETWORK=testnet

# Banker — testnet funded account
BANKER_SECRET=SXXX...
BANKER_PUBLIC=GXXX...

# Guardian — testnet funded account
GUARDIAN_SECRET=SXXX...
GUARDIAN_PUBLIC=GXXX...

# Stripe (test mode)
STRIPE_PUBLISHABLE_KEY=pk_test_XXX
STRIPE_SECRET_KEY=sk_test_XXX
STRIPE_WEBHOOK_SECRET=whsec_XXX  # Generated by Stripe CLI (see below)

# Mailtrap
MAILTRAP_API_TOKEN=XXX

# App
APP_SECRET_KEY=local-dev-secret-change-in-production
DATABASE_PATH=./data/collective.db
```

#### 2. Install dependencies

```bash
uv venv
uv pip install -r requirements.txt
uv pip install -e ../hvym_stellar
```

#### 3. Stripe CLI for local webhooks

Stripe webhooks can't reach localhost directly. The Stripe CLI tunnels them.
`stripe.exe` is included in the repo root (gitignored).

```bash
# Login (one-time):
.\stripe.exe login

# Forward webhooks to local server:
.\stripe.exe listen --forward-to localhost:8080/api/stripe/webhook

# This prints a webhook signing secret (whsec_...) — add it to .env
# Test card number: 4242 4242 4242 4242 (any future exp, any CVC)
```

#### 4. Fund testnet accounts (if needed)

Testnet accounts can be funded via the Stellar Friendbot:

```bash
curl "https://friendbot.stellar.org/?addr=GXXX..."
curl "https://friendbot.stellar.org/?addr=GXXX..."
```

#### 5. Run the app

```bash
uv run python main.py
# App available at http://localhost:8080
```

### Network Configuration (Testnet-first, Mainnet-ready)

```python
# config.py
NET = os.getenv("STELLAR_NETWORK", "testnet")

NETWORK_CONFIG = {
    "testnet": {
        "horizon_url": "https://horizon-testnet.stellar.org",
        "rpc_url": "https://soroban-testnet.stellar.org",
        "passphrase": Network.TESTNET_NETWORK_PASSPHRASE,
        "explorer": "https://stellar.expert/explorer/testnet",
    },
    "mainnet": {
        "horizon_url": "https://horizon.stellar.org",
        "rpc_url": "https://soroban.stellar.org",
        "passphrase": Network.PUBLIC_NETWORK_PASSPHRASE,
        "explorer": "https://stellar.expert/explorer/public",
    },
}

HORIZON_URL = NETWORK_CONFIG[NET]["horizon_url"]
RPC_URL = NETWORK_CONFIG[NET]["rpc_url"]
NET_PW = NETWORK_CONFIG[NET]["passphrase"]
BLOCK_EXPLORER = NETWORK_CONFIG[NET]["explorer"]
```

Switching to mainnet requires only changing `STELLAR_NETWORK=mainnet` in `.env` and
updating contract addresses if they differ.

---

## Decisions Log

| # | Question | Decision |
|---|----------|----------|
| 1 | Stripe pricing | Literally 2x XLM market price, dynamic via CoinGecko price feed |
| 2 | Member types | Free (link-tree only) + Paid Coop (full access, NFC card, Pintheon) |
| 3 | Auth method | Email + password for site. Launch token/key in separate in-app section |
| 4 | NFC card flow | Separate app section, addressed in future tasks |
| 5 | 22 XLM purpose | Funds Pintheon node startup: join_collective, deploy_node_token, operations |
| 6 | Database | SQLite for MVP |
| 7 | Guardian key | Required at startup, app fails if missing |
| 8 | Network | Testnet first, single env var switch to mainnet when ready |
| 9 | Payment UI | Toggle switch on /join — XLM (default, left) vs Card (right) |
| 10 | Stripe status | **No Stripe code exists.** Must be built from scratch (checkout + webhook) |
| 11 | Payment UX | XLM → dedicated /join/pay/xlm page with QR + polling. Stripe → redirect to hosted checkout, webhook completes enrollment |
| 12 | Package manager | `uv` for all venv, dependency, testing, and CI flows. No raw pip/venv. |
| 13 | Testnet keys | Banker=SCHSS...AZT, Guardian=SDXOT...UOU (both funded testnet accounts) |
| 14 | Stripe account | Test mode configured. Stripe CLI required for local webhook forwarding. |
