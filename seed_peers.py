"""Seed dummy peer users and link them to tester0's card wallet.

Usage:
    uv run python seed_peers.py
"""

import asyncio
import io
import uuid
from PIL import Image, ImageDraw, ImageFont

import db
import ipfs_client

OWNER_MONIKER = "tester0"

DUMMY_PEERS = [
    {"moniker": "peer_alpha",   "front": "#e74c3c", "back": "#c0392b", "text": "white"},
    {"moniker": "peer_bravo",   "front": "#3498db", "back": "#2980b9", "text": "white"},
    {"moniker": "peer_charlie", "front": "#2ecc71", "back": "#27ae60", "text": "white"},
    {"moniker": "peer_delta",   "front": "#f39c12", "back": "#e67e22", "text": "black"},
    {"moniker": "peer_echo",    "front": "#9b59b6", "back": "#8e44ad", "text": "white"},
]

CARD_W, CARD_H = 856, 540  # NFC card pixel ratio


def make_card_image(bg_color: str, text_color: str, label: str, side: str) -> bytes:
    """Generate a solid-color card PNG with moniker text."""
    img = Image.new("RGB", (CARD_W, CARD_H), bg_color)
    draw = ImageDraw.Draw(img)

    # Large moniker text centered
    try:
        font_big = ImageFont.truetype("arial.ttf", 64)
        font_sm = ImageFont.truetype("arial.ttf", 28)
    except OSError:
        font_big = ImageFont.load_default()
        font_sm = font_big

    # Moniker
    bbox = draw.textbbox((0, 0), label, font=font_big)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((CARD_W - tw) / 2, (CARD_H - th) / 2 - 20), label, fill=text_color, font=font_big)

    # Side label
    side_label = side.upper()
    bbox2 = draw.textbbox((0, 0), side_label, font=font_sm)
    tw2 = bbox2[2] - bbox2[0]
    draw.text(((CARD_W - tw2) / 2, CARD_H - 60), side_label, fill=text_color, font=font_sm)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def seed():
    await db.init_db()

    # Find owner (tester0)
    owner = await db.get_user_by_email("tester0@test.com")
    if not owner:
        # Try by moniker
        from aiosqlite import Row
        import aiosqlite
        from config import DATABASE_PATH
        async with aiosqlite.connect(DATABASE_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT * FROM users WHERE moniker = ?", (OWNER_MONIKER,)
            )
            owner = await cursor.fetchone()

    if not owner:
        print(f"ERROR: Owner '{OWNER_MONIKER}' not found in DB. Create the account first.")
        return

    owner_id = owner["id"]
    print(f"Owner: {OWNER_MONIKER} (id={owner_id})")

    for peer in DUMMY_PEERS:
        moniker = peer["moniker"]

        # Check if peer already exists
        import aiosqlite
        from config import DATABASE_PATH
        async with aiosqlite.connect(DATABASE_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT * FROM users WHERE moniker = ?", (moniker,)
            )
            existing = await cursor.fetchone()

        if existing:
            peer_id = existing["id"]
            print(f"  {moniker}: already exists (id={peer_id})")
        else:
            # Create dummy user
            peer_id = await db.create_user(
                email=f"{moniker}@dummy.test",
                moniker=moniker,
                member_type="coop",
                password_hash="dummy_not_a_real_hash",
            )
            print(f"  {moniker}: created (id={peer_id})")

        # Generate and pin card images
        front_png = make_card_image(peer["front"], peer["text"], moniker, "front")
        back_png = make_card_image(peer["back"], peer["text"], moniker, "back")

        try:
            front_cid = await ipfs_client.ipfs_add(front_png, f"{moniker}_front.png")
            back_cid = await ipfs_client.ipfs_add(back_png, f"{moniker}_back.png")
            print(f"    front CID: {front_cid}")
            print(f"    back  CID: {back_cid}")

            await db.update_user(peer_id, nfc_image_cid=front_cid, nfc_back_image_cid=back_cid)
        except Exception as e:
            print(f"    IPFS error (skipping pin): {e}")
            front_cid = None
            back_cid = None

        # Link peer to owner's wallet
        await db.add_peer_card(owner_id, peer_id)
        print(f"    linked to {OWNER_MONIKER}'s wallet")

    print("\nDone. Peer cards seeded.")


if __name__ == "__main__":
    asyncio.run(seed())
