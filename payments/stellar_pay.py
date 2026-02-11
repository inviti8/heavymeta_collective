import uuid
import io
import base64
import qrcode
from stellar_sdk import Server
from config import BANKER_PUB, HORIZON_URL

XLM_COST = "333"
server = Server(horizon_url=HORIZON_URL)


def generate_stellar_qr(uri):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


def create_stellar_payment_request():
    order_id = str(uuid.uuid4())[:8]
    memo = f"hvym-{order_id}"

    stellar_uri = (
        f"web+stellar:pay"
        f"?destination={BANKER_PUB}"
        f"&amount={XLM_COST}"
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
        'amount': XLM_COST,
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
