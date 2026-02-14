import os
import uuid
import aiosqlite
from config import DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    email           TEXT UNIQUE NOT NULL,
    moniker         TEXT UNIQUE NOT NULL,
    member_type     TEXT NOT NULL,
    password_hash   TEXT NOT NULL,
    stellar_address TEXT,
    shared_pub      TEXT,
    encrypted_token TEXT,
    nfc_image_cid   TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    network         TEXT DEFAULT 'testnet'
);

CREATE TABLE IF NOT EXISTS link_tree (
    id          TEXT PRIMARY KEY,
    user_id     TEXT REFERENCES users(id),
    label       TEXT NOT NULL,
    url         TEXT NOT NULL,
    icon_url    TEXT,
    sort_order  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS profile_colors (
    user_id           TEXT PRIMARY KEY REFERENCES users(id),
    bg_color          TEXT DEFAULT '#ffffff',
    text_color        TEXT DEFAULT '#000000',
    accent_color      TEXT DEFAULT '#8c52ff',
    link_color        TEXT DEFAULT '#f2d894',
    card_color        TEXT DEFAULT '#f5f5f5',
    border_color      TEXT DEFAULT '#e0e0e0',
    dark_bg_color     TEXT DEFAULT '#1a1a1a',
    dark_text_color   TEXT DEFAULT '#f0f0f0',
    dark_accent_color TEXT DEFAULT '#a87aff',
    dark_link_color   TEXT DEFAULT '#d4a843',
    dark_card_color   TEXT DEFAULT '#2a2a2a',
    dark_border_color TEXT DEFAULT '#444444'
);

CREATE TABLE IF NOT EXISTS profile_settings (
    user_id           TEXT PRIMARY KEY REFERENCES users(id),
    linktree_override INTEGER DEFAULT 0,
    linktree_url      TEXT DEFAULT '',
    dark_mode         INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS peer_cards (
    id           TEXT PRIMARY KEY,
    owner_id     TEXT REFERENCES users(id),
    peer_id      TEXT REFERENCES users(id),
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(owner_id, peer_id)
);

CREATE TABLE IF NOT EXISTS payments (
    id              TEXT PRIMARY KEY,
    user_id         TEXT REFERENCES users(id),
    method          TEXT NOT NULL,
    amount          TEXT NOT NULL,
    xlm_price_usd   REAL,
    memo            TEXT,
    tx_hash         TEXT,
    status          TEXT DEFAULT 'pending',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS denom_wallets (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id),
    denomination    INTEGER NOT NULL,
    stellar_address TEXT NOT NULL,
    token           TEXT NOT NULL,
    qr_cid          TEXT,
    status          TEXT DEFAULT 'active',
    sort_order      INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    spent_at        TIMESTAMP,
    merge_hash      TEXT,
    payout_hash     TEXT,
    fee_xlm         REAL
);

CREATE TABLE IF NOT EXISTS user_cards (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id),
    front_image_cid TEXT,
    back_image_cid  TEXT,
    status          TEXT DEFAULT 'draft',
    is_active       INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS card_orders (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL REFERENCES users(id),
    card_id          TEXT NOT NULL REFERENCES user_cards(id),
    payment_method   TEXT,
    payment_status   TEXT DEFAULT 'pending',
    tx_hash          TEXT,
    amount_usd       REAL,
    shipping_name    TEXT,
    shipping_street  TEXT,
    shipping_city    TEXT,
    shipping_state   TEXT,
    shipping_zip     TEXT,
    shipping_country TEXT,
    order_status     TEXT DEFAULT 'pending',
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


async def init_db():
    os.makedirs(os.path.dirname(DATABASE_PATH) or '.', exist_ok=True)
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        await conn.executescript(SCHEMA)
        await conn.commit()

        # Migrations — idempotent column additions
        migrations = [
            "ALTER TABLE users ADD COLUMN ipns_key_name TEXT",
            "ALTER TABLE users ADD COLUMN ipns_name TEXT",
            "ALTER TABLE users ADD COLUMN linktree_cid TEXT",
            "ALTER TABLE users ADD COLUMN ipns_key_backup TEXT",
            "ALTER TABLE users ADD COLUMN nfc_back_image_cid TEXT",
            # Color columns for dark/light palettes
            "ALTER TABLE profile_colors ADD COLUMN card_color TEXT DEFAULT '#f5f5f5'",
            "ALTER TABLE profile_colors ADD COLUMN border_color TEXT DEFAULT '#e0e0e0'",
            "ALTER TABLE profile_colors ADD COLUMN dark_bg_color TEXT DEFAULT '#1a1a1a'",
            "ALTER TABLE profile_colors ADD COLUMN dark_text_color TEXT DEFAULT '#f0f0f0'",
            "ALTER TABLE profile_colors ADD COLUMN dark_accent_color TEXT DEFAULT '#a87aff'",
            "ALTER TABLE profile_colors ADD COLUMN dark_link_color TEXT DEFAULT '#d4a843'",
            "ALTER TABLE profile_colors ADD COLUMN dark_card_color TEXT DEFAULT '#2a2a2a'",
            "ALTER TABLE profile_colors ADD COLUMN dark_border_color TEXT DEFAULT '#444444'",
            # Dark mode preference
            "ALTER TABLE profile_settings ADD COLUMN dark_mode INTEGER DEFAULT 0",
            # Avatar
            "ALTER TABLE users ADD COLUMN avatar_cid TEXT",
            # QR code
            "ALTER TABLE users ADD COLUMN qr_code_cid TEXT",
            # Per-link QR codes
            "ALTER TABLE link_tree ADD COLUMN qr_cid TEXT",
            # show_network toggle for crypto/Stellar features
            "ALTER TABLE profile_settings ADD COLUMN show_network INTEGER DEFAULT 0",
            # Migrate binary 'coop' → named tier 'forge'
            "UPDATE users SET member_type = 'forge' WHERE member_type = 'coop'",
            # Migrate existing card images from users into user_cards
            """INSERT INTO user_cards (id, user_id, front_image_cid, back_image_cid, status, is_active)
               SELECT hex(randomblob(16)), id, nfc_image_cid, nfc_back_image_cid, 'ordered', 1
               FROM users
               WHERE nfc_image_cid IS NOT NULL
               AND NOT EXISTS (SELECT 1 FROM user_cards WHERE user_cards.user_id = users.id)""",
        ]
        for sql in migrations:
            try:
                await conn.execute(sql)
            except Exception:
                pass  # column already exists
        await conn.commit()


# --- Users ---

async def create_user(*, user_id=None, email, moniker, member_type, password_hash,
                      stellar_address=None, shared_pub=None, encrypted_token=None,
                      network='testnet'):
    uid = user_id or str(uuid.uuid4())
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        await conn.execute(
            """INSERT INTO users (id, email, moniker, member_type, password_hash,
               stellar_address, shared_pub, encrypted_token, network)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid, email, moniker, member_type, password_hash,
             stellar_address, shared_pub, encrypted_token, network),
        )
        await conn.commit()
    return uid


async def get_user_by_email(email):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM users WHERE email = ?", (email,))
        return await cursor.fetchone()


async def get_user_by_id(user_id):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        return await cursor.fetchone()


async def get_user_by_ipns_name(ipns_name):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM users WHERE ipns_name = ?", (ipns_name,)
        )
        return await cursor.fetchone()


async def get_user_by_moniker_slug(slug: str):
    """Look up user by URL-style moniker slug (lowercase, hyphens)."""
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM users WHERE LOWER(REPLACE(moniker, ' ', '-')) = ?",
            (slug.lower(),),
        )
        return await cursor.fetchone()


async def check_moniker_available(moniker):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        cursor = await conn.execute("SELECT 1 FROM users WHERE moniker = ?", (moniker,))
        return await cursor.fetchone() is None


async def check_email_available(email):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        cursor = await conn.execute("SELECT 1 FROM users WHERE email = ?", (email,))
        return await cursor.fetchone() is None


async def count_members_by_type(member_type):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM users WHERE member_type = ?", (member_type,)
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def update_user(user_id, **fields):
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [user_id]
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        await conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
        await conn.commit()


# --- Payments ---

async def create_payment(*, user_id, method, amount, xlm_price_usd=None,
                         memo=None, tx_hash=None, status='pending'):
    pid = str(uuid.uuid4())
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        await conn.execute(
            """INSERT INTO payments (id, user_id, method, amount, xlm_price_usd,
               memo, tx_hash, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (pid, user_id, method, amount, xlm_price_usd, memo, tx_hash, status),
        )
        await conn.commit()
    return pid


async def update_payment_status(payment_id, status, tx_hash=None):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        if tx_hash:
            await conn.execute(
                "UPDATE payments SET status = ?, tx_hash = ? WHERE id = ?",
                (status, tx_hash, payment_id),
            )
        else:
            await conn.execute(
                "UPDATE payments SET status = ? WHERE id = ?",
                (status, payment_id),
            )
        await conn.commit()


async def get_payment_by_memo(memo):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM payments WHERE memo = ?", (memo,))
        return await cursor.fetchone()


# --- Link Tree ---

async def get_links(user_id):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM link_tree WHERE user_id = ? ORDER BY sort_order", (user_id,)
        )
        return await cursor.fetchall()


async def create_link(*, user_id, label, url, icon_url=None, sort_order=0):
    lid = str(uuid.uuid4())
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        await conn.execute(
            "INSERT INTO link_tree (id, user_id, label, url, icon_url, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
            (lid, user_id, label, url, icon_url, sort_order),
        )
        await conn.commit()
    return lid


async def update_link(link_id, **fields):
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [link_id]
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        await conn.execute(f"UPDATE link_tree SET {set_clause} WHERE id = ?", values)
        await conn.commit()


async def delete_link(link_id):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        await conn.execute("DELETE FROM link_tree WHERE id = ?", (link_id,))
        await conn.commit()


async def get_link_by_id(link_id):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM link_tree WHERE id = ?", (link_id,)
        )
        return await cursor.fetchone()


# --- Profile Colors ---

_COLOR_DEFAULTS = {
    'bg_color': '#ffffff',
    'text_color': '#000000',
    'accent_color': '#8c52ff',
    'link_color': '#f2d894',
    'card_color': '#f5f5f5',
    'border_color': '#e0e0e0',
    'dark_bg_color': '#1a1a1a',
    'dark_text_color': '#f0f0f0',
    'dark_accent_color': '#a87aff',
    'dark_link_color': '#d4a843',
    'dark_card_color': '#2a2a2a',
    'dark_border_color': '#444444',
}

_COLOR_COLS = list(_COLOR_DEFAULTS.keys())


async def get_profile_colors(user_id):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM profile_colors WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
    if row:
        d = dict(row)
        return {k: d.get(k, _COLOR_DEFAULTS[k]) for k in _COLOR_DEFAULTS}
    return dict(_COLOR_DEFAULTS)


async def upsert_profile_colors(user_id, **colors):
    vals = {k: colors.get(k, _COLOR_DEFAULTS[k]) for k in _COLOR_COLS}
    cols = ', '.join(_COLOR_COLS)
    placeholders = ', '.join(['?'] * (1 + len(_COLOR_COLS)))
    updates = ', '.join(f'{c} = excluded.{c}' for c in _COLOR_COLS)
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        await conn.execute(
            f"""INSERT INTO profile_colors (user_id, {cols})
               VALUES ({placeholders})
               ON CONFLICT(user_id) DO UPDATE SET {updates}""",
            (user_id, *[vals[c] for c in _COLOR_COLS]),
        )
        await conn.commit()


# --- Profile Settings ---

_SETTINGS_DEFAULTS = {
    'linktree_override': 0,
    'linktree_url': '',
    'dark_mode': 0,
    'show_network': 0,
}


async def get_profile_settings(user_id):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM profile_settings WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
    if row:
        d = dict(row)
        return {k: d.get(k, _SETTINGS_DEFAULTS[k]) for k in _SETTINGS_DEFAULTS}
    return dict(_SETTINGS_DEFAULTS)


async def upsert_profile_settings(user_id, linktree_override, linktree_url,
                                   dark_mode=None, show_network=None):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        await conn.execute(
            """INSERT INTO profile_settings
                   (user_id, linktree_override, linktree_url, dark_mode, show_network)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   linktree_override = excluded.linktree_override,
                   linktree_url = excluded.linktree_url,
                   dark_mode = excluded.dark_mode,
                   show_network = excluded.show_network""",
            (user_id, int(linktree_override), linktree_url,
             int(dark_mode) if dark_mode is not None else 0,
             int(show_network) if show_network is not None else 0),
        )
        await conn.commit()


# --- Peer Cards ---

async def add_peer_card(owner_id, peer_id):
    pid = str(uuid.uuid4())
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        await conn.execute(
            """INSERT OR IGNORE INTO peer_cards (id, owner_id, peer_id)
               VALUES (?, ?, ?)""",
            (pid, owner_id, peer_id),
        )
        await conn.commit()
    return pid


async def remove_peer_card(owner_id, peer_id):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        await conn.execute(
            "DELETE FROM peer_cards WHERE owner_id = ? AND peer_id = ?",
            (owner_id, peer_id),
        )
        await conn.commit()


async def get_peer_cards(owner_id):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT u.moniker, uc.front_image_cid AS nfc_image_cid,
                      uc.back_image_cid AS nfc_back_image_cid,
                      u.ipns_name, u.member_type, u.id as peer_id
               FROM peer_cards pc
               JOIN users u ON u.id = pc.peer_id
               LEFT JOIN user_cards uc ON uc.user_id = u.id AND uc.is_active = 1
               WHERE pc.owner_id = ?
               ORDER BY pc.collected_at""",
            (owner_id,),
        )
        return await cursor.fetchall()


# --- Denomination Wallets ---

async def create_denom_wallet(*, user_id, denomination, stellar_address, token):
    wid = str(uuid.uuid4())
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        await conn.execute(
            """INSERT INTO denom_wallets
               (id, user_id, denomination, stellar_address, token)
               VALUES (?, ?, ?, ?, ?)""",
            (wid, user_id, denomination, stellar_address, token),
        )
        await conn.commit()
    return wid


async def get_denom_wallets(user_id, status='active'):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM denom_wallets WHERE user_id = ? AND status = ? ORDER BY sort_order",
            (user_id, status),
        )
        return await cursor.fetchall()


async def get_denom_wallet_by_id(wallet_id):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM denom_wallets WHERE id = ?", (wallet_id,)
        )
        return await cursor.fetchone()


async def get_all_active_denom_wallets():
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM denom_wallets WHERE status = 'active'"
        )
        return await cursor.fetchall()


async def mark_denom_spent(wallet_id, *, merge_hash, payout_hash, fee_xlm):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        await conn.execute(
            """UPDATE denom_wallets
               SET status = 'spent', spent_at = CURRENT_TIMESTAMP,
                   merge_hash = ?, payout_hash = ?, fee_xlm = ?
               WHERE id = ?""",
            (merge_hash, payout_hash, fee_xlm, wallet_id),
        )
        await conn.commit()


async def update_denom_wallet(wallet_id, **fields):
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [wallet_id]
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        await conn.execute(f"UPDATE denom_wallets SET {set_clause} WHERE id = ?", values)
        await conn.commit()


async def discard_denom_wallet(wallet_id):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        await conn.execute(
            "UPDATE denom_wallets SET status = 'discarded' WHERE id = ?",
            (wallet_id,),
        )
        await conn.commit()


# --- User Cards ---

async def create_user_card(user_id):
    card_id = str(uuid.uuid4())
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        await conn.execute(
            "INSERT INTO user_cards (id, user_id) VALUES (?, ?)",
            (card_id, user_id),
        )
        await conn.commit()
    return card_id


async def get_user_card_by_id(card_id):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM user_cards WHERE id = ?", (card_id,)
        )
        return await cursor.fetchone()


async def get_draft_card(user_id):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM user_cards WHERE user_id = ? AND status = 'draft' LIMIT 1",
            (user_id,),
        )
        return await cursor.fetchone()


async def get_user_cards(user_id, exclude_draft=False):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if exclude_draft:
            cursor = await conn.execute(
                "SELECT * FROM user_cards WHERE user_id = ? AND status != 'draft' ORDER BY created_at DESC",
                (user_id,),
            )
        else:
            cursor = await conn.execute(
                "SELECT * FROM user_cards WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            )
        return await cursor.fetchall()


async def get_active_card(user_id):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM user_cards WHERE user_id = ? AND is_active = 1",
            (user_id,),
        )
        return await cursor.fetchone()


async def update_card_images(card_id, **fields):
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [card_id]
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        await conn.execute(
            f"UPDATE user_cards SET {set_clause} WHERE id = ?", values
        )
        await conn.commit()


async def set_active_card(user_id, card_id):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        await conn.execute(
            "UPDATE user_cards SET is_active = 0 WHERE user_id = ?",
            (user_id,),
        )
        await conn.execute(
            "UPDATE user_cards SET is_active = 1 WHERE id = ? AND user_id = ?",
            (card_id, user_id),
        )
        await conn.commit()


async def count_ordered_cards(user_id):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM user_cards WHERE user_id = ? AND status != 'draft'",
            (user_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0


async def create_card_order(*, user_id, card_id, payment_method, amount_usd,
                            shipping_name, shipping_street, shipping_city,
                            shipping_state, shipping_zip, shipping_country,
                            tx_hash=None, payment_status='pending'):
    order_id = str(uuid.uuid4())
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        await conn.execute(
            """INSERT INTO card_orders
               (id, user_id, card_id, payment_method, payment_status, tx_hash,
                amount_usd, shipping_name, shipping_street, shipping_city,
                shipping_state, shipping_zip, shipping_country)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (order_id, user_id, card_id, payment_method, payment_status,
             tx_hash, amount_usd, shipping_name, shipping_street,
             shipping_city, shipping_state, shipping_zip, shipping_country),
        )
        await conn.commit()
    return order_id


async def finalize_card_order(order_id, tx_hash=None):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # Mark order as paid
        if tx_hash:
            await conn.execute(
                "UPDATE card_orders SET payment_status = 'paid', tx_hash = ? WHERE id = ?",
                (tx_hash, order_id),
            )
        else:
            await conn.execute(
                "UPDATE card_orders SET payment_status = 'paid' WHERE id = ?",
                (order_id,),
            )
        # Get order to find card_id and user_id
        cursor = await conn.execute(
            "SELECT * FROM card_orders WHERE id = ?", (order_id,)
        )
        order = await cursor.fetchone()
        if order:
            card_id = order['card_id']
            user_id = order['user_id']
            # Mark card as ordered
            await conn.execute(
                "UPDATE user_cards SET status = 'ordered' WHERE id = ?",
                (card_id,),
            )
            # Set as active card
            await conn.execute(
                "UPDATE user_cards SET is_active = 0 WHERE user_id = ?",
                (user_id,),
            )
            await conn.execute(
                "UPDATE user_cards SET is_active = 1 WHERE id = ?",
                (card_id,),
            )
        await conn.commit()
