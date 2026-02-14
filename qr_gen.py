"""QR code generation with embedded avatar and user color scheme."""

import io
import os
import tempfile
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer
from qrcode.image.styles.colormasks import SolidFillColorMask
from PIL import Image, ImageDraw, ImageFont


PLACEHOLDER = os.path.join(os.path.dirname(__file__), 'static', 'placeholder.png')


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert '#8c52ff' to (140, 82, 255)."""
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def generate_user_qr(url: str, avatar_path: str,
                     fg_hex: str = '#8c52ff',
                     bg_hex: str = '#ffffff') -> bytes:
    """Generate a branded QR code with embedded avatar.

    Args:
        url: Full URL to encode in the QR code.
        avatar_path: Filesystem path to avatar image for center embed.
        fg_hex: Foreground color (QR modules) as hex string.
        bg_hex: Background color as hex string.

    Returns:
        PNG image bytes.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=RoundedModuleDrawer(),
        color_mask=SolidFillColorMask(
            back_color=hex_to_rgb(bg_hex),
            front_color=hex_to_rgb(fg_hex),
        ),
        embeded_image_path=avatar_path,
    )

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


async def get_avatar_path(avatar_cid: str | None) -> str:
    """Return filesystem path to avatar image for QR embed."""
    if not avatar_cid:
        return PLACEHOLDER

    import ipfs_client
    data = await ipfs_client.ipfs_cat(avatar_cid)
    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    tmp.write(data)
    tmp.close()
    return tmp.name


async def _load_qr_style(user_id: str):
    """Load user colors, avatar path, and QR style params.

    Returns (fg_hex, bg_hex, avatar_path, user_dict) or None if user missing.
    Caller must clean up avatar_path if it differs from PLACEHOLDER.
    """
    import db as _db

    user = await _db.get_user_by_id(user_id)
    if not user:
        return None

    colors = await _db.get_profile_colors(user_id)
    settings = await _db.get_profile_settings(user_id)

    dark = bool(settings.get('dark_mode', 0))
    fg = colors.get('dark_accent_color' if dark else 'accent_color', '#8c52ff')
    bg = colors.get('dark_bg_color' if dark else 'bg_color', '#ffffff')

    avatar_path = await get_avatar_path(dict(user).get('avatar_cid'))
    return fg, bg, avatar_path, dict(user)


def _cleanup_avatar(user_dict, avatar_path):
    """Remove temp avatar file if it was fetched from IPFS."""
    if user_dict.get('avatar_cid') and avatar_path != PLACEHOLDER:
        try:
            os.unlink(avatar_path)
        except OSError:
            pass


async def regenerate_qr(user_id: str):
    """Regenerate the user's personal QR code image and update IPFS + DB."""
    import ipfs_client
    import db as _db

    style = await _load_qr_style(user_id)
    if not style:
        return
    fg, bg, avatar_path, user = style

    try:
        slug = user['moniker'].lower().replace(' ', '-')
        url = f'/profile/{slug}'

        png_bytes = generate_user_qr(url, avatar_path, fg, bg)
        old_cid = user.get('qr_code_cid')
        new_cid = await ipfs_client.replace_asset(png_bytes, old_cid, 'qr_code.png')
        await _db.update_user(user_id, qr_code_cid=new_cid)
    finally:
        _cleanup_avatar(user, avatar_path)


async def generate_link_qr(user_id: str, link_id: str, url: str):
    """Generate a branded QR code for a specific linktree URL.

    Uses the same colors and avatar as the user's personal QR.
    Pins to IPFS and updates the link_tree row with the CID.
    Returns the new CID or None on failure.
    """
    import ipfs_client
    import db as _db

    style = await _load_qr_style(user_id)
    if not style:
        return None
    fg, bg, avatar_path, user = style

    try:
        png_bytes = generate_user_qr(url, avatar_path, fg, bg)
        new_cid = await ipfs_client.ipfs_add(png_bytes, 'link_qr.png')
        await _db.update_link(link_id, qr_cid=new_cid)
        return new_cid
    finally:
        _cleanup_avatar(user, avatar_path)


async def regenerate_all_link_qrs(user_id: str):
    """Regenerate QR codes for all of a user's links.

    Called when avatar, colors, or dark mode change.
    """
    import ipfs_client
    import db as _db

    style = await _load_qr_style(user_id)
    if not style:
        return
    fg, bg, avatar_path, user = style

    try:
        links = await _db.get_links(user_id)
        for link in links:
            link = dict(link)
            old_cid = link.get('qr_cid')
            if old_cid:
                await ipfs_client.ipfs_unpin(old_cid)
            png_bytes = generate_user_qr(link['url'], avatar_path, fg, bg)
            new_cid = await ipfs_client.ipfs_add(png_bytes, 'link_qr.png')
            await _db.update_link(link['id'], qr_cid=new_cid)
    finally:
        _cleanup_avatar(user, avatar_path)


def generate_denom_qr(url: str, avatar_path: str, denomination: int,
                      fg_hex: str = '#8c52ff',
                      bg_hex: str = '#ffffff') -> bytes:
    """Generate branded QR with avatar + denomination badge."""
    base_png = generate_user_qr(url, avatar_path, fg_hex, bg_hex)
    img = Image.open(io.BytesIO(base_png)).convert('RGBA')

    w, h = img.size
    badge_size = int(w * 0.18)
    margin = int(w * 0.03)
    cx = w - margin - badge_size // 2
    cy = h - margin - badge_size // 2

    draw = ImageDraw.Draw(img)
    r = badge_size // 2
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=hex_to_rgb(fg_hex))

    text = str(denomination)
    font_size = int(badge_size * 0.55)
    try:
        font = ImageFont.truetype("arialbd.ttf", font_size)
    except OSError:
        font = ImageFont.load_default(font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text((cx - tw // 2, cy - th // 2), text, fill=(255, 255, 255), font=font)

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def generate_qr_card_front(qr_png_bytes: bytes, bg_hex: str,
                           card_width: int = 856, card_height: int = 540) -> bytes:
    """Generate a QR business card front: solid color background + centered QR.

    Args:
        qr_png_bytes: PNG bytes of the QR code image.
        bg_hex: Background color as hex string (e.g. '#8c52ff').
        card_width: Card width in pixels (default 856 — NFC card ratio).
        card_height: Card height in pixels (default 540).

    Returns:
        PNG image bytes of the composite card front.
    """
    bg_rgb = hex_to_rgb(bg_hex)
    card = Image.new('RGBA', (card_width, card_height), (*bg_rgb, 255))

    qr_img = Image.open(io.BytesIO(qr_png_bytes)).convert('RGBA')
    # Scale QR to 80% of card height, maintain aspect ratio
    target_h = int(card_height * 0.8)
    aspect = qr_img.width / qr_img.height
    target_w = int(target_h * aspect)
    qr_img = qr_img.resize((target_w, target_h), Image.LANCZOS)

    # Center on card
    x = (card_width - target_w) // 2
    y = (card_height - target_h) // 2
    card.paste(qr_img, (x, y), qr_img)

    buf = io.BytesIO()
    card.save(buf, format='PNG')
    return buf.getvalue()


async def regenerate_qr_card_front(user_id: str) -> str | None:
    """Regenerate the QR card front composite and store in IPFS + DB.

    Returns the new front_image_cid or None on failure.
    """
    import ipfs_client
    import db as _db

    style = await _load_qr_style(user_id)
    if not style:
        return None
    fg, bg, avatar_path, user = style

    try:
        slug = user['moniker'].lower().replace(' ', '-')
        url = f'/profile/{slug}'

        qr_bytes = generate_user_qr(url, avatar_path, fg, bg)
        card_front_bytes = generate_qr_card_front(qr_bytes, bg)

        qr_card = await _db.get_qr_card(user_id)
        old_cid = dict(qr_card).get('front_image_cid') if qr_card else None
        new_cid = await ipfs_client.replace_asset(
            card_front_bytes, old_cid, 'qr_card_front.png'
        )
        await _db.upsert_qr_card(user_id, front_image_cid=new_cid)
        return new_cid
    finally:
        _cleanup_avatar(user, avatar_path)


async def generate_denom_wallet_qr(user_id: str, wallet_id: str, pay_uri: str,
                                    denomination: int):
    """Generate branded denom QR, pin to IPFS, update DB."""
    import ipfs_client
    import db as _db

    style = await _load_qr_style(user_id)
    if not style:
        return None
    fg, bg, avatar_path, user = style

    try:
        png_bytes = generate_denom_qr(pay_uri, avatar_path, denomination, fg, bg)
        new_cid = await ipfs_client.ipfs_add(png_bytes, 'denom_qr.png')
        await _db.update_denom_wallet(wallet_id, qr_cid=new_cid)
        return new_cid
    finally:
        _cleanup_avatar(user, avatar_path)
