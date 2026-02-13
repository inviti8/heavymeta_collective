import uuid
import io
import os
import base64
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer
from qrcode.image.styles.colormasks import SolidFillColorMask
from stellar_sdk import Server
from config import BANKER_PUB, HORIZON_URL
from payments.pricing import get_xlm_amount

server = Server(horizon_url=HORIZON_URL)

STELLAR_LOGO = os.path.join(os.path.dirname(__file__), '..', 'static', 'stellar_logo.png')


def generate_stellar_qr(uri):
    """Generate a branded QR code with the Stellar logo embedded in the center."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=RoundedModuleDrawer(),
        color_mask=SolidFillColorMask(
            back_color=(255, 255, 255),
            front_color=(0, 0, 0),
        ),
        embeded_image_path=STELLAR_LOGO,
    )
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


def create_stellar_payment_request(tier_key='forge'):
    order_id = str(uuid.uuid4())[:8]
    memo = f"hvym-{order_id}"
    xlm_amount = str(get_xlm_amount(tier_key, 'join'))

    stellar_uri = (
        f"web+stellar:pay"
        f"?destination={BANKER_PUB}"
        f"&amount={xlm_amount}"
        f"&asset_code=XLM"
        f"&memo={memo}"
    )

    qr_data_uri = generate_stellar_qr(stellar_uri)

    return {
        'order_id': order_id,
        'memo': memo,
        'uri': stellar_uri,
        'qr': qr_data_uri,
        'address': BANKER_PUB,
        'amount': xlm_amount,
    }


def check_payment(expected_memo):
    try:
        ops = server.operations().for_account(BANKER_PUB).limit(20).order(desc=True).call()
        for op in ops["_embedded"]["records"]:
            tx = server.transactions().transaction(op["transaction_hash"]).call()
            if tx.get("memo") == expected_memo:
                from config import BLOCK_EXPLORER
                return {
                    'paid': True,
                    'hash': tx["hash"],
                    'url': f'{BLOCK_EXPLORER}/tx/{tx["hash"]}',
                }
    except Exception:
        pass
    return {'paid': False}
