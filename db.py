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
    user_id      TEXT PRIMARY KEY REFERENCES users(id),
    bg_color     TEXT DEFAULT '#ffffff',
    text_color   TEXT DEFAULT '#000000',
    accent_color TEXT DEFAULT '#8c52ff',
    link_color   TEXT DEFAULT '#8c52ff'
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
"""


async def init_db():
    os.makedirs(os.path.dirname(DATABASE_PATH) or '.', exist_ok=True)
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        await conn.executescript(SCHEMA)
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


async def check_moniker_available(moniker):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        cursor = await conn.execute("SELECT 1 FROM users WHERE moniker = ?", (moniker,))
        return await cursor.fetchone() is None


async def check_email_available(email):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        cursor = await conn.execute("SELECT 1 FROM users WHERE email = ?", (email,))
        return await cursor.fetchone() is None


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


# --- Profile Colors ---

_COLOR_DEFAULTS = {
    'bg_color': '#ffffff',
    'text_color': '#000000',
    'accent_color': '#8c52ff',
    'link_color': '#8c52ff',
}


async def get_profile_colors(user_id):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM profile_colors WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
    if row:
        return {k: row[k] for k in _COLOR_DEFAULTS}
    return dict(_COLOR_DEFAULTS)


async def upsert_profile_colors(user_id, bg_color, text_color, accent_color, link_color):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        await conn.execute(
            """INSERT INTO profile_colors (user_id, bg_color, text_color, accent_color, link_color)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                   bg_color = excluded.bg_color,
                   text_color = excluded.text_color,
                   accent_color = excluded.accent_color,
                   link_color = excluded.link_color""",
            (user_id, bg_color, text_color, accent_color, link_color),
        )
        await conn.commit()
