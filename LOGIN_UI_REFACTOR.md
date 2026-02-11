# LOGIN_UI_REFACTOR.md — Dialog-Based Auth + Payment Flow

## 1. Problem

The current auth/signup/payment flow is split across four separate full-page
routes with inconsistent UX:

| Route | Purpose | UX Issue |
|-------|---------|----------|
| `/login` | Email + password | Separate page; "Join" link navigates away entirely |
| `/join` | Signup form + tier + payment toggle | Synchronous `requests.get()` to CoinGecko during render can block/hang the page |
| `/join/pay/xlm` | QR code + payment polling | Separate page; user loses signup context |
| `/join/success` | Stripe return + polling | Separate page; fragile session-dependent state |

**Known bug:** Navigating to `/join` can hang the app because `fetch_xlm_price()`
makes a synchronous HTTP call to CoinGecko during page construction, blocking
NiceGUI's event loop. The `try/except` catches failures but doesn't prevent the
10-second timeout from freezing the UI.

---

## 2. Target State

Replace the four separate pages with a single **auth dialog** that can be
opened from anywhere (landing page, header buttons, auth guards). The dialog
uses a **tabbed layout**:

```
┌──────────────────────────────────────────┐
│  HEAVYMETA COLLECTIVE                    │
│                                          │
│  ┌─────────┐ ┌─────────┐                │
│  │  LOGIN   │ │  JOIN    │  ← top tabs   │
│  └─────────┘ └─────────┘                │
│                                          │
│  ── LOGIN tab ──────────────────────     │
│  EMAIL       [__________________]        │
│  PASSWORD    [__________________]        │
│                                          │
│  [ LOGIN ]                               │
│                                          │
│  ── JOIN tab ───────────────────────     │
│  MONIKER     [__________________]        │
│  EMAIL       [__________________]        │
│  PASSWORD    [__________________]        │
│                                          │
│  MEMBERSHIP:  ○ FREE  ● COOP            │
│                                          │
│  ┌──────────┐ ┌──────────┐              │
│  │  XLM ◉   │ │  CARD    │  ← sub-tabs  │
│  └──────────┘ └──────────┘              │
│                                          │
│  PRICE: 333 XLM (~$XX.XX USD)           │
│                                          │
│  [ SIGN UP — PAY 333 XLM ]              │
│                                          │
└──────────────────────────────────────────┘
```

After XLM signup, the **same dialog** transitions to a QR payment view
(no page navigation):

```
┌──────────────────────────────────────────┐
│  COMPLETE YOUR PAYMENT                   │
│                                          │
│  Send exactly 333 XLM to:               │
│                                          │
│       ┌────────────┐                     │
│       │  QR CODE   │                     │
│       └────────────┘                     │
│                                          │
│  Address: GXXX...  [copy]               │
│  Amount:  333 XLM                        │
│  Memo:    hvym-abc123  [copy]           │
│                                          │
│  ◌ Waiting for payment...               │
│                                          │
└──────────────────────────────────────────┘
```

---

## 3. Design Decisions

### 3a. Dialog vs Page

**Dialog.** The auth flow is modal — the user either completes it or cancels.
A dialog keeps them in context (landing page, dashboard, etc.) and avoids
full-page reloads. NiceGUI's `ui.dialog()` supports this natively.

### 3b. Price Fetching

**Async + lazy.** Move `fetch_xlm_price()` to an async function and fetch
it only when the user selects the COOP tier or switches to the CARD tab —
never during page construction. This eliminates the blocking hang.

```python
# Current (blocks event loop):
def join():
    usd_equiv = get_xlm_usd_equivalent()  # synchronous requests.get()

# Proposed (non-blocking):
async def _load_prices():
    price = await async_fetch_xlm_price()
    xlm_label.text = f'PRICE: {XLM_COST} XLM (~${XLM_COST * price:.2f} USD)'
    card_label.text = f'PRICE: ${XLM_COST * price * 2:.2f} USD (2x crypto price)'
```

### 3c. Tabs vs Toggle

**Quasar tabs (`ui.tabs` + `ui.tab_panels`).** Replace the XLM/Card toggle
switch with proper Quasar tabs. This gives clear visual separation, lets each
tab hold its own content panel, and scales if we add more payment methods
(e.g., SOL, USDC) later.

### 3d. XLM Payment: In-Dialog

After the user submits the XLM signup form, the dialog content transitions
to the QR payment view. The dialog stays open, polling continues in the
background. On payment confirmation, the dialog auto-closes and the user
is redirected to `/profile/edit`.

### 3e. Stripe Payment: External Redirect

Stripe Checkout requires a full browser redirect (Stripe-hosted page).
The dialog closes, browser navigates to Stripe. On return,
`/join/success` still handles the webhook polling — but we can simplify
it since the user record already exists.

### 3f. Auth Guard Integration

Currently `require_auth()` does `ui.navigate.to('/login')`. After refactor,
it should open the auth dialog instead. This is a stretch goal — phase 2.

---

## 4. Component Architecture

### New File: `auth_dialog.py`

Single exported function:

```python
def open_auth_dialog(initial_tab='login'):
    """Open the auth dialog. Tabs: LOGIN | JOIN.
    JOIN tab has sub-tabs for payment method when COOP tier is selected.
    """
```

This replaces:
- `/login` page handler (`main.py:332-372`)
- `/join` page handler (`main.py:76-215`)
- `/join/pay/xlm` page handler (`main.py:220-292`)

### Kept Separately

- `/join/success` — Stripe return page (browser redirect, can't be a dialog)
- Stripe webhook handler — FastAPI route, unchanged
- `enrollment.py` — Business logic, unchanged
- `payments/` — Payment logic, unchanged (except async price fetch)

---

## 5. File Changes

| File | Change | Description |
|------|--------|-------------|
| `auth_dialog.py` | **NEW** | Auth dialog with LOGIN/JOIN tabs, payment sub-tabs, XLM QR flow |
| `payments/pricing.py` | **MODIFY** | Add `async_fetch_xlm_price()` using `httpx` instead of `requests` |
| `main.py` | **MODIFY** | Remove `/login` and `/join` page handlers; remove `/join/pay/xlm`; update header/landing buttons to call `open_auth_dialog()` |
| `components.py` | **MODIFY** | Update `style_page()` header buttons (Join/Login) to open dialog instead of navigating |
| `auth.py` | **MODIFY** | (Phase 2) Update `require_auth()` to open dialog instead of redirect |

---

## 6. Dialog Internal State Machine

```
LOGIN tab:
  → email + password
  → [LOGIN] button
  → on success: close dialog, set_session(), navigate to /profile/edit
  → on failure: show error inline

JOIN tab:
  → moniker + email + password + tier radio
  → if tier == 'free':
      → [SIGN UP — FREE] button
      → on success: close dialog, set_session(), navigate to /profile/edit

  → if tier == 'coop':
      → show payment sub-tabs: XLM | CARD
      → XLM tab:
          → shows price (async-loaded)
          → [SIGN UP — PAY 333 XLM] button
          → on click: validate form → create payment request → transition to QR view
          → QR view polls for payment
          → on payment confirmed: process enrollment → close dialog → navigate

      → CARD tab:
          → shows price (async-loaded, 2x XLM)
          → [SIGN UP — PAY $XX.XX] button
          → on click: validate form → create pending user → create Stripe session
          → close dialog → redirect to Stripe
          → Stripe returns to /join/success (existing page, unchanged)
```

---

## 7. Async Price Fetch

### `payments/pricing.py` — Add async variant

```python
import httpx

async def async_fetch_xlm_price():
    """Non-blocking XLM price fetch. Uses same cache as sync version."""
    now = time.time()
    if _price_cache['price'] and (now - _price_cache['timestamp']) < CACHE_TTL:
        return _price_cache['price']

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "stellar", "vs_currencies": "usd"},
            )
            resp.raise_for_status()
            price = resp.json()["stellar"]["usd"]
    except Exception:
        if _price_cache['price']:
            return _price_cache['price']
        return FALLBACK_PRICE

    _price_cache['price'] = price
    _price_cache['timestamp'] = now
    return price


async def async_get_xlm_usd_equivalent():
    return round(XLM_COST * await async_fetch_xlm_price(), 2)


async def async_get_stripe_price_cents():
    xlm_usd = await async_fetch_xlm_price()
    stripe_usd = XLM_COST * xlm_usd * 2
    return int(stripe_usd * 100)


async def async_get_stripe_price_display():
    cents = await async_get_stripe_price_cents()
    return f"${cents / 100:.2f}"
```

The synchronous versions remain for the Stripe webhook path (which runs
in a FastAPI background thread, not the NiceGUI event loop).

---

## 8. `auth_dialog.py` — Pseudocode

```python
from nicegui import ui, app
from auth import validate_signup_form, login_user, set_session, hash_password
from enrollment import process_free_enrollment, process_paid_enrollment
from payments.stellar_pay import create_stellar_payment_request, check_payment
from payments.stripe_pay import create_checkout_session
from payments.pricing import XLM_COST, async_fetch_xlm_price
import db


def open_auth_dialog(initial_tab='login'):
    with ui.dialog().props('persistent maximized') as dialog, \
         ui.card().classes('w-full max-w-md mx-auto p-6 gap-4'):

        # ── Top tabs: LOGIN | JOIN ──
        with ui.tabs().classes('w-full') as tabs:
            login_tab = ui.tab('LOGIN')
            join_tab = ui.tab('JOIN')
        tabs.value = initial_tab.upper()

        with ui.tab_panels(tabs).classes('w-full'):

            # ══════════ LOGIN PANEL ══════════
            with ui.tab_panel(login_tab):
                email_login = ui.input('EMAIL').props('outlined').classes('w-full')
                pw_login = ui.input('PASSWORD').props('outlined type=password').classes('w-full')
                login_error = ui.label('').classes('text-red-500 text-sm')
                login_error.set_visibility(False)

                async def handle_login():
                    login_error.set_visibility(False)
                    if not email_login.value or not pw_login.value:
                        login_error.text = 'Please enter your email and password.'
                        login_error.set_visibility(True)
                        return
                    user, rate_error = await login_user(
                        email_login.value.strip(), pw_login.value
                    )
                    if rate_error:
                        login_error.text = rate_error
                        login_error.set_visibility(True)
                    elif user:
                        set_session(user)
                        dialog.close()
                        ui.navigate.to('/profile/edit')
                    else:
                        login_error.text = 'Invalid email or password.'
                        login_error.set_visibility(True)

                ui.button('LOGIN', on_click=handle_login).classes('w-full mt-4')

            # ══════════ JOIN PANEL ══════════
            with ui.tab_panel(join_tab):
                moniker = ui.input('MONIKER').props('outlined').classes('w-full')
                email_join = ui.input('EMAIL').props('outlined').classes('w-full')
                pw_join = ui.input('PASSWORD').props('outlined type=password').classes('w-full')

                tier = ui.radio(
                    {'free': 'FREE — Link-tree only',
                     'coop': 'COOP MEMBER — Full access'},
                    value='free',
                ).classes('w-full')

                join_error = ui.label('').classes('text-red-500 text-sm')
                join_error.set_visibility(False)

                # ── Payment sub-tabs (visible only for coop) ──
                with ui.column().classes('w-full gap-4') as payment_section:
                    ui.separator()
                    with ui.tabs().classes('w-full') as pay_tabs:
                        xlm_tab = ui.tab('XLM')
                        card_tab = ui.tab('CARD')

                    with ui.tab_panels(pay_tabs).classes('w-full'):
                        with ui.tab_panel(xlm_tab):
                            xlm_price_label = ui.label(
                                f'PRICE: {XLM_COST} XLM'
                            ).classes('text-lg font-bold')

                        with ui.tab_panel(card_tab):
                            card_price_label = ui.label(
                                'PRICE: calculating...'
                            ).classes('text-lg font-bold')
                            ui.label(
                                'Join the future. Pay less with crypto.'
                            ).classes('text-sm opacity-70 italic')

                payment_section.bind_visibility_from(
                    tier, 'value', backward=lambda v: v == 'coop'
                )

                # Load prices async when coop selected
                async def load_prices():
                    price = await async_fetch_xlm_price()
                    usd = round(XLM_COST * price, 2)
                    xlm_price_label.text = f'PRICE: {XLM_COST} XLM (~${usd} USD)'
                    stripe_usd = round(XLM_COST * price * 2, 2)
                    card_price_label.text = f'PRICE: ${stripe_usd} USD (2x crypto price)'

                tier.on_value_change(
                    lambda e: load_prices() if e.value == 'coop' else None
                )

                # ── Signup button (text updates with tier/tab) ──
                signup_btn = ui.button(
                    'SIGN UP — FREE', on_click=lambda: handle_signup()
                ).classes('w-full mt-4')

                # ... handle_signup() routes to XLM QR view or Stripe redirect

        # ── Close button ──
        with ui.row().classes('w-full justify-end'):
            ui.button(icon='close', on_click=dialog.close).props('flat round')

    dialog.open()
    return dialog
```

---

## 9. XLM QR View (In-Dialog Transition)

When the user clicks "SIGN UP — PAY 333 XLM":

1. Validate signup form
2. `create_stellar_payment_request()` → get QR, memo, address
3. Store pending signup in `app.storage.user`
4. **Replace dialog content** with QR payment view (using `.clear()` + rebuild)
5. Start polling timer `ui.timer(5.0, check_and_update)`
6. On payment confirmed → `process_paid_enrollment()` → close dialog → navigate

```python
async def show_xlm_payment(dialog_card, pending):
    """Transition dialog content to QR payment view."""
    dialog_card.clear()
    with dialog_card:
        ui.label('COMPLETE YOUR PAYMENT').classes('text-2xl font-bold')
        ui.label(f'Send exactly {pending["amount"]} XLM to:')

        ui.image(pending['qr']).classes('w-64 h-64 mx-auto')

        # Address, amount, memo with copy buttons ...

        status_label = ui.label('Waiting for payment...').classes('opacity-70')
        spinner = ui.spinner('dots', size='lg')

        async def check_and_update():
            result = check_payment(pending['memo'])
            if result['paid']:
                timer.deactivate()
                spinner.set_visibility(False)
                status_label.text = 'Payment confirmed!'
                # ... process enrollment, close dialog, navigate

        timer = ui.timer(5.0, check_and_update)
```

---

## 10. Integration Points

### Landing Page (`main.py`)

```python
@ui.page('/')
def landing():
    style_page('HEAVYMETA COLLECTIVE')
    # ...
    ui.button('JOIN', on_click=lambda: open_auth_dialog('join'))
```

### Header Buttons (`components.py:style_page`)

```python
# Current:
ui.button('Join', on_click=lambda: ui.navigate.to('/join'))
ui.button('Login', on_click=lambda: ui.navigate.to('/login'))

# Proposed:
ui.button('Join', on_click=lambda: open_auth_dialog('join'))
ui.button('Login', on_click=lambda: open_auth_dialog('login'))
```

### Login Page — Kept as Redirect

Keep `/login` as a minimal route that opens the dialog:

```python
@ui.page('/login')
def login():
    style_page('HEAVYMETA')
    open_auth_dialog('login')
```

This preserves deep-link behavior for `require_auth()` redirects and
browser bookmarks.

Similarly for `/join`:

```python
@ui.page('/join')
def join():
    style_page('HEAVYMETA')
    open_auth_dialog('join')
```

---

## 11. Migration Path

### Phase 1 (This PR)
- Create `auth_dialog.py` with tabbed dialog
- Add `async_fetch_xlm_price()` to `payments/pricing.py`
- Replace `/login` and `/join` page content with `open_auth_dialog()` calls
- Move XLM QR payment flow into dialog (remove `/join/pay/xlm`)
- Keep `/join/success` for Stripe returns
- Fix the blocking price-fetch hang

### Phase 2 (Future)
- Update `require_auth()` to open dialog instead of redirect
- Add "Forgot Password" tab/link
- Add social login options (Stellar wallet connect?)

---

## 12. Implementation Sequence

1. **`payments/pricing.py`** — Add async price fetch functions
2. **`auth_dialog.py`** — Create dialog with LOGIN/JOIN tabs + payment sub-tabs
3. **`auth_dialog.py`** — Add XLM QR payment view transition
4. **`main.py`** — Replace `/login`, `/join`, `/join/pay/xlm` with dialog openers
5. **`components.py`** — Update header Join/Login buttons to open dialog
6. **Test** — Login flow, free signup, XLM coop signup, Stripe coop signup

---

## 13. Current Flow Trace (Post-Refactor) — Bug Analysis

### 13a. Login Flow

```
User clicks Login (header or /login deep link)
  → open_auth_dialog('login')
  → LOGIN tab active
  → User enters email + password → clicks LOGIN
  → handle_login()
    → login_user(email, password)     [auth.py:53]
      → _check_rate_limit(email)
      → db.get_user_by_email(email)
      → verify_password(password, user['password_hash'])
      → returns (user_dict, None) on success
    → set_session(user)               [auth.py:70]
      → app.storage.user['authenticated'] = True
      → app.storage.user['user_id'] = user['id']
      → app.storage.user['moniker'] = user['moniker']
      → app.storage.user['member_type'] = user['member_type']  ← reads from DB
      → app.storage.user['email'] = user['email']
    → dialog.close()
    → ui.navigate.to('/profile/edit')
```

**Status:** Working. Session reflects DB state at login time.

---

### 13b. Free Signup Flow

```
User clicks Join → open_auth_dialog('join')
  → JOIN tab active
  → User fills moniker, email, password → selects FREE → clicks SIGN UP — FREE
  → handle_signup()
    → validate_signup_form(moniker, email, password)     [auth.py:98]
      → check moniker non-empty, ≤100 chars
      → db.check_moniker_available(moniker)              [db.py:121]
      → validate email format + db.check_email_available
      → check password ≥ 8 chars
    → process_free_enrollment(moniker, email, password)  [enrollment.py:43]
      → hash_password(password)
      → db.create_user(user_id=uuid, email, moniker, member_type='free', pw_hash)
      → send_welcome_email (fire-and-forget)
      → _setup_ipns (fire-and-forget)
      → returns user_id
    → db.get_user_by_id(user_id)
    → set_session(user)
    → dialog.close()
    → ui.navigate.to('/profile/edit')
```

**Status:** Working. User created and session set atomically.

---

### 13c. XLM Coop Signup Flow

```
User clicks Join → open_auth_dialog('join')
  → JOIN tab → fills form → selects COOP → clicks CONTINUE TO PAYMENT
  → handle_signup()
    → validate_signup_form(...)         — form validated
    → hash_password(pw_join.value)
    → form_data = {moniker, email, password_hash}
    → dialog.close()
    → _open_payment_dialog(form_data)   [auth_dialog.py:143]

Payment dialog opens → XLM tab (default)
  → async load_prices() fires via ui.timer(0.1, once=True)
    → async_fetch_xlm_price()           — non-blocking httpx
    → updates price labels
  → User clicks SIGN UP — PAY 333 XLM
  → handle_pay()
    → create_stellar_payment_request()  [stellar_pay.py:23]
      → generates order_id, memo, QR
    → pending = {form_data + payment details}
    → app.storage.user['pending_signup'] = pending
    → _show_xlm_payment(pay_card, pending, pay_dialog)

QR view replaces dialog content
  → ui.timer(5.0, check_and_update)    — polls every 5s
  → check_and_update()
    → check_payment(memo)              [stellar_pay.py:47]
      → queries Horizon for matching tx
    → if paid:
      → timer.deactivate()
      → fetch_xlm_price()              — sync, hits warm cache
      → process_paid_enrollment(...)   [enrollment.py:66]
        → Keypair.random()
        → fund_account(22 XLM)
        → encrypt user secret
        → db.create_user(member_type='coop', stellar_address, ...)
        → db.create_payment(status='completed')
        → register_on_roster (fire-and-forget)
        → send_welcome_email (fire-and-forget)
        → _setup_ipns (fire-and-forget)
        → returns (user_id, stellar_address)
      → db.get_user_by_id(user_id)
      → set_session(user)              — member_type='coop' ✓
      → del app.storage.user['pending_signup']
      → pay_dialog.close()
      → ui.navigate.to('/profile/edit')
```

**Status:** Working. User is only created in DB after payment is confirmed
on-chain. No premature DB writes.

---

### 13d. Stripe Coop Signup Flow ← BUG 1 + BUG 2

```
User clicks Join → open_auth_dialog('join')
  → JOIN tab → fills form (moniker="test3") → selects COOP
  → clicks CONTINUE TO PAYMENT
  → handle_signup()
    → validate_signup_form(...)         — passes (moniker "test3" is available)
    → form_data = {moniker="test3", email, password_hash}
    → dialog.close()
    → _open_payment_dialog(form_data)

Payment dialog opens → User clicks CARD tab → clicks SIGN UP — PAY $XX.XX
  → handle_pay()                        [auth_dialog.py:202]
    ┌─────────────────────────────────────────────────────────────┐
    │ ★ BUG 1: PREMATURE USER CREATION                          │
    │                                                             │
    │ db.create_user(                    [auth_dialog.py:221]     │
    │     email="...",                                            │
    │     moniker="test3",                                        │
    │     member_type='free',   ← created as FREE                │
    │     password_hash=...,                                      │
    │ )                                                           │
    │                                                             │
    │ User "test3" now EXISTS in DB with member_type='free'.     │
    │ This happens BEFORE Stripe checkout even loads.            │
    │                                                             │
    │ If user abandons Stripe checkout, closes browser, or       │
    │ Stripe errors → "test3" is permanently stuck in DB.        │
    │ Retry with same moniker → "That moniker is already taken." │
    └─────────────────────────────────────────────────────────────┘

    → order_id = f"stripe-{user_id[:8]}"
    → create_checkout_session(...)      [stripe_pay.py:8]
      → get_stripe_price_cents()        — sync, hits cache
      → fetch_xlm_price()              — sync, hits cache
      → stripe.checkout.Session.create(
          success_url = '/join/success?session_id=...',
          cancel_url  = '/join',
          metadata    = {order_id, user_id, moniker, xlm_price_usd}
        )

    ┌─────────────────────────────────────────────────────────────┐
    │ ★ BUG 2a: SESSION NOT SET BEFORE REDIRECT                 │
    │                                                             │
    │ At this point, user_id is a local variable only.           │
    │ It is NEVER stored in app.storage.user.                    │
    │                                                             │
    │ pay_dialog.close()                                          │
    │ ui.run_javascript("window.location.href='stripe_url'")     │
    │                                                             │
    │ Browser navigates to Stripe. app.storage.user has NO       │
    │ user_id, NO authenticated flag. Just empty session.        │
    └─────────────────────────────────────────────────────────────┘

--- User completes payment on Stripe ---

  Stripe redirects browser to: /join/success?session_id=cs_xxx

  /join/success handler                 [main.py:88]
    → app.storage.user.get('authenticated') → False (never set)
    → user_id = app.storage.user.get('user_id') → None (never set!)

    ┌─────────────────────────────────────────────────────────────┐
    │ ★ BUG 2b: SUCCESS PAGE HAS NO USER ID                     │
    │                                                             │
    │ Polling timer starts with user_id = None                   │
    │ → check_enrollment() fires:                                │
    │   → "if not user_id:" → True                               │
    │   → status_label = "Session expired. Please log in."       │
    │   → timer.deactivate()                                     │
    │                                                             │
    │ Page is now dead. User sees "Session expired."             │
    │ User must manually navigate to /login.                     │
    └─────────────────────────────────────────────────────────────┘

--- Meanwhile, Stripe fires webhook ---

  POST /api/stripe/webhook              [main.py:32]
    → handle_webhook(payload, sig)      [stripe_pay.py:39]
      → validates signature
      → event type = 'checkout.session.completed'
      → returns {completed: True, user_id, order_id, ...}
    → finalize_pending_enrollment(...)  [enrollment.py:127]
      → db.get_user_by_id(user_id)     — finds the 'free' user from Bug 1
      → Keypair.random()
      → fund_account(22 XLM)           ← can FAIL on testnet!
      → encrypt secret
      → db.update_user(user_id, member_type='coop', stellar_address, ...)
      → db.create_payment(status='completed')
      → register_on_roster (fire-and-forget)
      → send_welcome_email (fire-and-forget)
      → _setup_ipns (fire-and-forget)

    If fund_account fails → entire function raises → webhook returns 500
    → Stripe retries, but user stays 'free' until retry succeeds.

--- User manually logs in ---

    ┌─────────────────────────────────────────────────────────────┐
    │ ★ BUG 2c: RACE CONDITION ON LOGIN                         │
    │                                                             │
    │ User sees "Session expired", goes to /login, enters creds. │
    │                                                             │
    │ login_user(email, password) → db.get_user_by_email(email)  │
    │ set_session(user) → member_type = user['member_type']      │
    │                                                             │
    │ IF webhook has NOT completed yet:                           │
    │   → member_type = 'free' in DB → session says 'free' ✗    │
    │   → User sees FREE tier on dashboard                       │
    │   → Webhook may complete later, but session is cached      │
    │                                                             │
    │ IF webhook completed successfully:                          │
    │   → member_type = 'coop' in DB → session says 'coop' ✓    │
    │                                                             │
    │ IF fund_account failed in webhook:                          │
    │   → member_type = 'free' still → session says 'free' ✗    │
    │   → Stripe retries webhook later, but user is stuck        │
    └─────────────────────────────────────────────────────────────┘
```

---

### 13e. Bug Summary

| # | Bug | Root Cause | File:Line | Severity |
|---|-----|------------|-----------|----------|
| 1 | **Moniker locked on failed Stripe attempt** | `db.create_user()` is called BEFORE Stripe checkout completes. If user abandons or payment fails, the moniker/email is permanently consumed. | `auth_dialog.py:221` | **High** — blocks retry |
| 2a | **Session not set before Stripe redirect** | `user_id` from `db.create_user()` is stored in a local variable but never written to `app.storage.user` before the browser redirects to Stripe. | `auth_dialog.py:234` | **High** — breaks /join/success |
| 2b | **Success page has no user_id to poll** | `/join/success` reads `app.storage.user.get('user_id')` which is None. Timer immediately shows "Session expired." and stops. | `main.py:97` | **High** — success page is dead |
| 2c | **Race: login before webhook completes** | User manually logs in before Stripe webhook fires `finalize_pending_enrollment`. Session caches `member_type='free'` from DB. Even after webhook upgrades DB, session is stale. | `auth.py:74` | **Medium** — timing dependent |

---

### 13f. Proposed Fixes

**Bug 1 — Defer user creation:**
Don't call `db.create_user()` before Stripe checkout. Instead, store
`form_data` in `app.storage.user['pending_stripe']` and let the webhook
create the user (or create it on `/join/success` after payment is confirmed).
Alternatively, use an idempotent upsert so retries work.

**Bug 2a/2b — Store user_id in session before redirect:**
If we keep the current "create user first" approach, we MUST do:
```python
app.storage.user['user_id'] = user_id
```
before the Stripe redirect. This lets `/join/success` poll correctly.

**Bug 2c — Refresh session from DB:**
On `/join/success`, after detecting the user is now 'coop', call
`set_session(dict(user))` (already done). The real fix is ensuring
2a/2b work so the user never has to manually log in.

**Recommended combined fix:**
1. Do NOT create user in `handle_pay()` for Stripe.
2. Store `form_data` in `app.storage.user['pending_stripe']`.
3. Redirect to Stripe.
4. Webhook calls `finalize_pending_enrollment` which now must also
   **create** the user (not just upgrade), using the metadata passed
   through Stripe's `metadata` field (already has moniker, user_id).
5. `/join/success` polls with a session-stored identifier (email or
   a pending-signup token) instead of user_id.
6. On successful poll, `set_session()` and redirect to dashboard.
