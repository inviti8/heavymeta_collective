# WALLETS.md — Denomination Wallet System

## Concept

The user's **main Stellar wallet** (created at enrollment, encrypted with Banker+Guardian dual-key) stays **private** — never exposed in the linktree or public profile. Instead, the user creates **denomination wallets**: ephemeral, unfunded Stellar keypairs with a preset XLM value. Each denom wallet generates a `web+stellar:pay` URI and a branded QR code. When a denom wallet receives payment, funds are immediately forwarded to the hidden main wallet via **account merge**, the spent wallet is discarded, and a fresh one is auto-generated.

This creates a **disposable payment address** system — a kind of digital fiat layer on Stellar.

---

## Denominations

Preset values based on Fibonacci sequence up to 21:

| Denom | XLM |
|-------|-----|
| 1     | 1   |
| 2     | 2   |
| 3     | 3   |
| 5     | 5   |
| 8     | 8   |
| 13    | 13  |
| 21    | 21  |

User picks from these presets when adding a new denom wallet. Multiple wallets of the same denomination are allowed (e.g., three separate "5 XLM" wallets).

---

## Stellar Mechanics

### Unfunded Accounts
A denom wallet is a `Keypair.random()` — just a public/secret key pair. It doesn't exist on the Stellar ledger until someone sends XLM to it (a `create_account` operation). This means:
- Zero cost to generate
- No on-chain footprint until paid
- Truly "phantom" until activated by payment

### Payment Flow
1. Payer scans QR → wallet app opens `web+stellar:pay` URI
2. Payer sends `{denomination}` XLM to the denom wallet address
3. This creates the account on-ledger with the sent amount as starting balance
4. Our watcher detects the incoming payment
5. Server decrypts the denom wallet secret (Banker+Guardian)
6. Server submits an **`AccountMerge`** operation: denom wallet → **Banker**
7. AccountMerge closes the denom wallet and transfers ALL XLM (minus 0.00001 fee) to Banker
8. Banker deducts a **collective fee** and sends the remainder to the user's main wallet
9. Denom wallet marked `spent`, new one auto-generated with same denomination

### Two-Step Settlement: Merge → Fee → Pay User
```
Denom Wallet ──AccountMerge──► Banker ──Payment──► User Main Wallet
                                  │
                                  └── Fee retained by Collective
```

This gives the Collective a revenue channel on every denomination payment. The Banker is already a funded, always-online account — it can execute the payout immediately in the same watcher cycle.

**Both operations can be submitted atomically** as a single Stellar transaction if we source the payout from the Banker in the same block, but since they involve different source accounts (denom wallet signs the merge, Banker signs the payment), they're two separate transactions submitted back-to-back.

### Why AccountMerge (to Banker)?
- Stellar minimum balance is 1 XLM per account
- A normal `payment` operation can't send the full balance (must keep ≥ 1 XLM)
- `AccountMerge` closes the account entirely, sending 100% of remaining funds to Banker
- Even for the 1 XLM denomination, Banker receives ~0.99999 XLM
- Merging to Banker (not directly to user) lets the Collective collect fees transparently

### Fee Structure

| Denomination | Fee (XLM) | User Receives |
|-------------|-----------|---------------|
| 1           | 0.03      | ~0.97         |
| 2           | 0.06      | ~1.94         |
| 3           | 0.09      | ~2.91         |
| 5           | 0.15      | ~4.85         |
| 8           | 0.24      | ~7.76         |
| 13          | 0.39      | ~12.61        |
| 21          | 0.63      | ~20.37        |

Starting fee: **3%**. Configurable via `DENOM_FEE_PERCENT` in `config.py`. The "~" accounts for the tiny 0.00001 XLM network fees on both transactions.

### Overpayment
If someone sends MORE than the denomination (e.g., 10 XLM to a 5 XLM denom wallet), the full amount is merged to Banker. Fee is calculated on the actual received amount (not the denomination). Remainder sent to user. The denom wallet is still discarded and replaced.

---

## Secret Storage: Shared Account Token vs Raw Encryption

Two options for storing denom wallet secrets. Both use the same Banker+Guardian ECDH key derivation under the hood.

### Option A: Raw Encryption (current enrollment pattern)

```python
# Create
kp = Keypair.random()
encryptor = StellarSharedKey(BANKER_25519, GUARDIAN_25519.public_key())
encrypted_secret = encryptor.encrypt(kp.secret.encode())
# → store encrypted_secret blob in DB

# Recover
decryptor = StellarSharedDecryption(GUARDIAN_25519, BANKER_25519.public_key())
secret = decryptor.decrypt(encrypted_secret, from_address=BANKER_KP.public_key)
```

- Simple, minimal overhead
- Same pattern already used for main wallet secrets in `enrollment.py`
- Metadata (denomination, user_id) lives only in DB columns
- No built-in expiration or tamper detection

### Option B: StellarSharedAccountTokenBuilder

```python
# Create
token = StellarSharedAccountTokenBuilder(
    senderKeyPair=BANKER_25519,
    receiverPub=GUARDIAN_25519.public_key(),
    caveats={'denomination': 5, 'user_id': user_id},
    expires_in=86400 * 90,  # 90-day expiry for stale wallets
)
address = token.shared_public_key
serialized = token.serialize()
# → store serialized token in DB

# Recover
kp = StellarSharedAccountTokenBuilder.extract_shared_keypair(
    serialized, GUARDIAN_25519
)
```

- **Self-describing**: denomination, user_id, creation time embedded in verifiable caveats
- **Expiration**: stale/abandoned denom wallets auto-expire — watcher skips them
- **Tamper-evident**: SHA256 checksum detects DB corruption or tampering
- **Consistent**: same token infrastructure used for launch tokens
- Slightly larger storage (~2KB vs ~200B per wallet)

### Recommendation

**Option B** fits the "phantom fiat" concept better. These denom wallets are financial instruments — the extra integrity guarantees (tamper detection, expiration, self-describing metadata) are worth the small storage overhead. The watcher can verify token validity before attempting a merge, catching corrupted state early rather than failing on-chain.

If we go with Option B, the DB schema simplifies — `encrypted_secret` becomes `token` and we can drop the `denomination` column (it's in the caveats), though keeping it as a denormalized index column is practical for queries.

---

## Database Schema

### New table: `denom_wallets`

```sql
CREATE TABLE IF NOT EXISTS denom_wallets (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id),
    denomination    INTEGER NOT NULL,       -- XLM amount (denormalized from token caveats for queries)
    stellar_address TEXT NOT NULL,           -- Public key (from token.shared_public_key)
    token           TEXT NOT NULL,           -- Serialized StellarSharedAccountToken (Banker→Guardian)
    qr_cid          TEXT,                   -- IPFS CID of branded QR image
    status          TEXT DEFAULT 'active',  -- 'active' | 'spent' | 'discarded'
    sort_order      INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    spent_at        TIMESTAMP,
    merge_hash      TEXT,                   -- AccountMerge tx hash (denom → Banker)
    payout_hash     TEXT,                   -- Payment tx hash (Banker → user)
    fee_xlm         REAL                    -- Fee retained by Collective
);
```

### New DB functions (db.py)

| Function | Purpose |
|----------|---------|
| `create_denom_wallet(user_id, denomination, stellar_address, token)` | Insert new denom wallet |
| `get_denom_wallets(user_id, status='active')` | List user's active denom wallets |
| `get_all_active_denom_wallets()` | All active wallets across all users (for watcher) |
| `mark_denom_spent(wallet_id, merge_hash, payout_hash, fee_xlm)` | Set status='spent', record hashes + fee + timestamp |
| `discard_denom_wallet(wallet_id)` | Set status='discarded' (manual removal) |
| `update_denom_qr(wallet_id, qr_cid)` | Store QR CID after generation |

---

## QR Code Generation

### Branded QR with Denomination Badge

Extend `qr_gen.py` with a new function:

```python
def generate_denom_qr(url: str, avatar_path: str, denomination: int,
                      fg_hex: str = '#8c52ff',
                      bg_hex: str = '#ffffff') -> bytes:
```

**Layout:**
1. Generate standard branded QR (avatar embedded in center, user colors)
2. Overlay a **denomination badge** in the bottom-right corner:
   - Circular badge with primary color background
   - White bold text: the denomination number (e.g., "5")
   - Badge size proportional to QR (~15% of QR width)
3. Return PNG bytes

Uses PIL `ImageDraw` to composite the badge onto the QR image after generation.

### Pay URL Format

```
web+stellar:pay?destination={denom_address}&amount={denomination}&asset_code=XLM
```

No memo needed — each denom wallet IS the identifier. We detect payment by watching the address itself.

---

## Payment Watcher

### Background task: `denom_watcher.py`

A background async task that polls active denom wallets for incoming payments.

```python
async def watch_denom_wallets():
    """Poll all active denom wallets for incoming payments. Runs on interval."""
    active = await db.get_all_active_denom_wallets()
    for wallet in active:
        try:
            account = server.accounts().account_id(wallet['stellar_address']).call()
            # Account exists = someone funded it = payment received
            await process_denom_payment(wallet)
        except NotFoundError:
            # Account doesn't exist yet — no payment received
            continue
```

### Processing a payment

```python
async def process_denom_payment(wallet):
    """Merge denom wallet → Banker, deduct fee, pay user, regenerate."""
    # 1. Extract keypair from shared account token
    denom_kp = StellarSharedAccountTokenBuilder.extract_shared_keypair(
        wallet['token'], GUARDIAN_25519
    )

    # 2. Read actual balance (may differ from denomination if overpaid)
    denom_account = server.accounts().account_id(denom_kp.public_key).call()
    balance = get_native_balance(denom_account)  # float, e.g. 5.0

    # 3. AccountMerge: denom → Banker
    account = server.load_account(denom_kp.public_key)
    merge_tx = (
        TransactionBuilder(account, network_passphrase=PASSPHRASE, base_fee=100)
        .append_account_merge_op(destination=BANKER_PUB)
        .set_timeout(30)
        .build()
    )
    merge_tx.sign(denom_kp)
    merge_result = server.submit_transaction(merge_tx)

    # 4. Calculate fee and payout
    fee_pct = DENOM_FEE_PERCENT / 100  # e.g. 0.03
    gross = balance - 0.00001          # minus merge tx fee
    fee = round(gross * fee_pct, 7)
    payout = round(gross - fee, 7)

    # 5. Banker pays user's main wallet
    user = await db.get_user(wallet['user_id'])
    banker_account = server.load_account(BANKER_PUB)
    pay_tx = (
        TransactionBuilder(banker_account, network_passphrase=PASSPHRASE, base_fee=100)
        .append_payment_op(
            destination=user['stellar_address'],
            asset=Asset.native(),
            amount=str(payout),
        )
        .set_timeout(30)
        .build()
    )
    pay_tx.sign(BANKER_KP)
    pay_result = server.submit_transaction(pay_tx)

    # 6. Record both tx hashes, mark spent
    await db.mark_denom_spent(
        wallet['id'],
        merge_hash=merge_result['hash'],
        payout_hash=pay_result['hash'],
        fee_xlm=fee,
    )

    # 7. Auto-generate replacement with same denomination
    await create_denom_wallet_for_user(wallet['user_id'], wallet['denomination'])

    # 8. Republish linktree (updated wallet list)
    ipfs_client.schedule_republish(wallet['user_id'])
```

### Startup integration (main.py)

Register the watcher as a periodic NiceGUI timer or background task:

```python
ui.timer(30.0, lambda: asyncio.ensure_future(watch_denom_wallets()))
```

Poll every 30 seconds. Only checks accounts that are `status='active'`. Lightweight — a single Horizon API call per active wallet (returns 404 fast for unfunded accounts).

---

## UI — Dashboard Wallet Section

### Location
`/profile/edit` page, in the existing WALLETS section (currently read-only). Coop members only.

### Layout

```
WALLETS
┌─────────────────────────────────────────────────┐
│ [QR thumb]  5 XLM    GXXX...YYYY   [copy] [del]│
│ [QR thumb]  8 XLM    GABC...DEFG   [copy] [del]│
│ [QR thumb]  21 XLM   GHIJ...KLMN   [copy] [del]│
│                                                  │
│ [+]  [ 1 | 2 | 3 | 5 | 8 | 13 | 21 ]          │
└─────────────────────────────────────────────────┘
```

**Wallet row:**
- QR thumbnail (clickable → full QR dialog, same as links)
- Denomination label ("5 XLM") in bold
- Truncated address
- Copy button (copies `web+stellar:pay` URI, not raw address)
- Delete button (discards wallet, unpins QR)

**Add row:**
- `+` button + denomination selector (chips or radio group)
- Clicking `+` after selecting a denom generates the wallet

### Pattern
Mirrors the links section CRUD pattern:
- `@ui.refreshable async def wallets_section()`
- Add/delete trigger `wallets_section.refresh()`
- IPFS republish after changes

---

## UI — Public Linktree Wallet Display

### Changes to `linktree_renderer.py`

Replace the current single-wallet display with denom wallet cards:

```
WALLETS
┌──────────────────────────────────┐
│ [QR]  5 XLM     [copy pay link] │
│ [QR]  8 XLM     [copy pay link] │
│ [QR]  21 XLM    [copy pay link] │
└──────────────────────────────────┘
```

- QR thumbnail clickable → full branded QR dialog
- Copy button copies the `web+stellar:pay` URI
- No raw addresses shown publicly (privacy)

---

## Linktree JSON Schema Update

### `ipfs_client.py` — `build_linktree_json()`

Current `wallets` array:
```json
"wallets": [{"network": "stellar", "address": "GXXX..."}]
```

New format:
```json
"wallets": [
    {
        "network": "stellar",
        "type": "denom",
        "denomination": 5,
        "address": "GABC...DEFG",
        "pay_uri": "web+stellar:pay?destination=GABC...&amount=5&asset_code=XLM",
        "qr_cid": "bafy..."
    }
]
```

The main wallet address is **never** included in the public linktree JSON.

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `denom_watcher.py` | **NEW** | Background watcher: poll, merge, regenerate |
| `qr_gen.py` | MODIFY | Add `generate_denom_qr()` with denomination badge |
| `db.py` | MODIFY | Add `denom_wallets` table + CRUD functions |
| `main.py` | MODIFY | Replace wallet display with add/delete CRUD section |
| `ipfs_client.py` | MODIFY | Update `build_linktree_json()` wallet schema |
| `linktree_renderer.py` | MODIFY | Update public wallet display for denom wallets |
| `enrollment.py` | MODIFY | Remove stellar_address from linktree (keep private) |
| `config.py` | MODIFY | Add `DENOM_PRESETS` and `DENOM_FEE_PERCENT` |

---

## Implementation Steps

### Phase 1: Schema + Wallet Generation
1. Add `denom_wallets` table to `db.py` with CRUD functions
2. Add `DENOM_PRESETS` and `DENOM_FEE_PERCENT` to `config.py`
3. Create `generate_denom_qr()` in `qr_gen.py` (avatar + denom badge)
4. Build `create_denom_wallet_for_user()` helper — uses `StellarSharedAccountTokenBuilder(BANKER_25519, GUARDIAN_25519.public_key(), caveats={denomination, user_id})` to generate keypair + token, store token in DB, generate QR
5. Add wallet CRUD UI to `/profile/edit` (add/delete/display, mirroring links pattern)

### Phase 2: Payment Watcher + Auto-Regeneration
6. Create `denom_watcher.py` (poll, detect, AccountMerge, regenerate)
7. Register watcher as periodic task in `main.py` startup
8. Test end-to-end on testnet: create denom → fund it → verify merge → verify new wallet generated

### Phase 3: Public Display + Linktree
9. Update `build_linktree_json()` to include denom wallets (remove main address)
10. Update `linktree_renderer.py` for new denom wallet display
11. Update `enrollment.py` to stop including main wallet in linktree

### Phase 4: Polish
12. Handle edge cases: watcher retry on failed merges, stale wallet cleanup
13. Add "Generating..." loading state in UI during wallet creation
14. Notification when a denom wallet is paid (if user is online)

### Phase 5: Main Wallet UI in Settings
15. Wrap existing color theme section in `ui.expansion('THEME')` container
16. Add `ui.expansion('WALLET')` section for main (hidden) wallet
17. Implement balance display via Horizon `server.accounts()` lookup
18. Add Receive button → dialog with QR code mapped to main wallet address
19. Add Send button → dialog with address, amount, optional memo fields
20. Build `send_xlm()` helper in `stellar_ops.py` using existing `server`/`BANKER_KP` patterns

---

## UI — Main Wallet (Settings Page)

### Location
`/settings` page, inside a collapsible `ui.expansion('WALLET')` container. Coop members only. Sits alongside the theme section which moves into its own `ui.expansion('THEME')` container.

### Settings Page Layout (after refactor)

```
SETTINGS
┌──────────────────────────────────────────────┐
│ ▸ THEME                                      │  ← ui.expansion (collapsed by default)
│   [preview + palette swatches + save]        │
├──────────────────────────────────────────────┤
│ ▸ WALLET                                     │  ← ui.expansion (coop only)
│   Balance: 142.38 XLM         [↻ refresh]    │
│   GABC...DEFG                                │
│   [RECEIVE]    [SEND]                        │
└──────────────────────────────────────────────┘
```

### Balance Display
- Query Horizon on section load: `server.accounts().account_id(user['stellar_address']).call()`
- Parse native XLM balance from `account['balances']` array (`asset_type == 'native'`)
- Show balance with 2-decimal precision: `"142.38 XLM"`
- Refresh button re-queries and updates label
- If account doesn't exist yet (unfunded): show "Not funded" with explanatory text

### Receive Dialog
Triggered by RECEIVE button. Shows:
```
┌─────────────────────────────┐
│       Receive XLM           │
│                             │
│   ┌───────────────────┐     │
│   │                   │     │
│   │    [QR CODE]      │     │
│   │                   │     │
│   └───────────────────┘     │
│                             │
│   GABC...DEFG   [copy]      │
│                             │
│           [Close]           │
└─────────────────────────────┘
```
- QR encodes the main wallet address as `web+stellar:pay?destination={address}`
- Uses existing `generate_user_qr()` for branded QR with avatar + user colors
- Generated on-the-fly (no need to IPFS-pin — this is private, not published)
- Full address shown below QR with copy button

### Send Dialog
Triggered by SEND button. Shows:
```
┌─────────────────────────────┐
│         Send XLM            │
│                             │
│  Destination                │
│  ┌─────────────────────┐    │
│  │ G...                 │    │
│  └─────────────────────┘    │
│                             │
│  Amount (XLM)               │
│  ┌─────────────────────┐    │
│  │                      │    │
│  └─────────────────────┘    │
│                             │
│  Memo (optional)            │
│  ┌─────────────────────┐    │
│  │                      │    │
│  └─────────────────────┘    │
│                             │
│  [Cancel]         [Send]    │
└─────────────────────────────┘
```
- Destination: Stellar G-address input (validated: starts with `G`, 56 chars)
- Amount: numeric input, validated > 0 and ≤ balance
- Memo: optional text memo (max 28 bytes for Stellar text memos)
- Send button submits a `payment` operation from user's main wallet
- Requires decrypting the user's secret key via Guardian token extraction
- Success: show tx hash with explorer link, update balance
- Failure: show error message, keep dialog open

### Stellar Operations

New function in `stellar_ops.py`:

```python
def send_xlm(source_kp: Keypair, destination: str, amount: str, memo: str = None) -> dict:
    """Submit a payment from source to destination.

    Args:
        source_kp: Signing keypair (user's main wallet)
        destination: Destination Stellar address
        amount: XLM amount as string (e.g. "5.5")
        memo: Optional text memo

    Returns:
        Horizon transaction response dict (contains 'hash', etc.)
    """
    account = server.load_account(source_kp.public_key)
    builder = TransactionBuilder(
        source_account=account,
        network_passphrase=NET_PW,
        base_fee=100,
    )
    builder.append_payment_op(
        destination=destination,
        asset=Asset.native(),
        amount=amount,
    )
    if memo:
        builder.add_text_memo(memo)
    builder.set_timeout(30)
    tx = builder.build()
    tx.sign(source_kp)
    return server.submit_transaction(tx)


def get_xlm_balance(address: str) -> str | None:
    """Query native XLM balance for a Stellar address.

    Returns balance string (e.g. "142.3800000") or None if account not found.
    """
    try:
        account = server.accounts().account_id(address).call()
        for b in account['balances']:
            if b['asset_type'] == 'native':
                return b['balance']
    except Exception:
        return None
```

### User Secret Recovery (for Send)

The user's wallet secret is encrypted in `users.encrypted_token`. To sign a send transaction, we need to decrypt it:

```python
from hvym_stellar import StellarSharedAccountTokenBuilder

user_kp = StellarSharedAccountTokenBuilder.extract_shared_keypair(
    user['encrypted_token'], GUARDIAN_25519
)
```

This is the same pattern used by the denom watcher for extracting denom wallet secrets. The Guardian key is already loaded at startup.

### Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `main.py` | MODIFY | Wrap theme in `ui.expansion('THEME')`, add `ui.expansion('WALLET')` with balance/send/receive |
| `stellar_ops.py` | MODIFY | Add `send_xlm()` and `get_xlm_balance()` |

---

## Security Considerations

- **Main wallet never exposed**: Not in linktree JSON, not in public profile, not in HTML
- **Denom secrets encrypted**: Same Banker+Guardian dual-key as main wallet secret
- **Ephemeral by design**: Each denom wallet used exactly once, then merged and discarded
- **No memo tracking**: Address-based detection (account exists = paid). No memo to leak
- **AccountMerge is atomic**: Either the full merge succeeds or it doesn't — no partial state
- **Banker as intermediary**: All funds flow through Banker — user never directly touches denom wallet funds. If the payout to the user fails after merge, funds are safely held by Banker (can be retried)
- **Fee transparency**: `fee_xlm` recorded per transaction in `denom_wallets` table for auditing

---

## Verification Checklist

- [ ] Can create denom wallet of each denomination (1-21)
- [ ] QR code shows avatar + denomination number
- [ ] Denom wallet address appears in dashboard wallet section
- [ ] Copy button copies `web+stellar:pay` URI
- [ ] Delete removes wallet, unpins QR from IPFS
- [ ] Linktree JSON includes denom wallets, excludes main wallet
- [ ] Public linktree displays denom wallets with QR + pay link
- [ ] Funding a denom wallet on testnet triggers AccountMerge **to Banker**
- [ ] Banker deducts correct fee (10% default)
- [ ] Banker pays remainder to user's main wallet
- [ ] `merge_hash`, `payout_hash`, `fee_xlm` recorded in DB
- [ ] Spent wallet auto-replaced with fresh one (same denom)
- [ ] Linktree auto-republished after payment cycle
- [ ] If payout fails after merge, funds remain safe in Banker (retryable)
- [ ] Settings page: theme section inside collapsible expansion
- [ ] Settings page: wallet section inside collapsible expansion (coop only)
- [ ] Wallet balance displays correctly from Horizon
- [ ] Refresh button updates balance
- [ ] Receive dialog shows branded QR with main wallet address
- [ ] Receive dialog copy button copies address
- [ ] Send dialog validates destination (G-address, 56 chars)
- [ ] Send dialog validates amount (> 0, ≤ balance)
- [ ] Send dialog submits payment, shows tx hash with explorer link
- [ ] Send dialog shows error on failure without closing
