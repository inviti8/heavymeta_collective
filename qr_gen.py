"""QR code generation with embedded avatar and user color scheme."""

import io
import os
import tempfile
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer
from qrcode.image.styles.colormasks import SolidFillColorMask


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


async def regenerate_qr(user_id: str):
    """Regenerate the user's QR code image and update IPFS + DB."""
    import db as _db
    import ipfs_client

    user = await _db.get_user_by_id(user_id)
    if not user:
        return

    colors = await _db.get_profile_colors(user_id)
    settings = await _db.get_profile_settings(user_id)

    dark = bool(settings.get('dark_mode', 0))
    fg = colors.get('dark_accent_color' if dark else 'accent_color', '#8c52ff')
    bg = colors.get('dark_bg_color' if dark else 'bg_color', '#ffffff')

    avatar_path = await get_avatar_path(dict(user).get('avatar_cid'))

    try:
        slug = user['moniker'].lower().replace(' ', '-')
        url = f'/profile/{slug}'

        png_bytes = generate_user_qr(url, avatar_path, fg, bg)
        old_cid = dict(user).get('qr_code_cid')
        new_cid = await ipfs_client.replace_asset(png_bytes, old_cid, 'qr_code.png')
        await _db.update_user(user_id, qr_code_cid=new_cid)
    finally:
        # Clean up temp file if we fetched avatar from IPFS
        if dict(user).get('avatar_cid') and avatar_path != PLACEHOLDER:
            try:
                os.unlink(avatar_path)
            except OSError:
                pass
