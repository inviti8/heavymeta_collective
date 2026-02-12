"""Denomination wallet operations — create, build pay URI."""

from hvym_stellar import StellarSharedAccountTokenBuilder
from config import BANKER_25519, GUARDIAN_25519
import db
from qr_gen import generate_denom_wallet_qr


def build_pay_uri(address: str, denomination: int) -> str:
    return f"web+stellar:pay?destination={address}&amount={denomination}&asset_code=XLM"


async def create_denom_wallet_for_user(user_id: str, denomination: int) -> str:
    """Generate a new denomination wallet, store token, generate QR. Returns wallet ID."""
    # 1. Build shared account token (Banker → Guardian)
    token = StellarSharedAccountTokenBuilder(
        senderKeyPair=BANKER_25519,
        receiverPub=GUARDIAN_25519.public_key(),
        caveats={'denomination': denomination, 'user_id': user_id},
    )
    address = token.shared_public_key
    serialized = token.serialize()

    # 2. Store in DB
    wallet_id = await db.create_denom_wallet(
        user_id=user_id,
        denomination=denomination,
        stellar_address=address,
        token=serialized,
    )

    # 3. Generate branded QR
    pay_uri = build_pay_uri(address, denomination)
    await generate_denom_wallet_qr(user_id, wallet_id, pay_uri, denomination)

    return wallet_id
