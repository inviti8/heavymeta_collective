from stellar_sdk import Keypair
from hvym_stellar import (
    Stellar25519KeyPair,
    StellarSharedDecryption,
    StellarSharedKeyTokenBuilder,
    TokenType,
)
import db
from config import BANKER_25519, GUARDIAN_25519, BANKER_KP, NET
from email_service import send_launch_key_email


async def generate_launch_credentials(user_id):
    # 1. Get user + encrypted secret
    user = await db.get_user_by_id(user_id)
    if not user or not user['encrypted_token']:
        raise ValueError('No encrypted credentials found for this user.')

    # 2. Decrypt user's Stellar secret (Guardian decrypts with Banker's pub)
    decryptor = StellarSharedDecryption(GUARDIAN_25519, BANKER_25519.public_key())
    encrypted_token = user['encrypted_token']
    if isinstance(encrypted_token, str):
        encrypted_token = encrypted_token.encode()
    user_secret = decryptor.decrypt(encrypted_token, from_address=BANKER_KP.public_key)
    if isinstance(user_secret, bytes):
        user_secret = user_secret.decode()
    user_keys = Keypair.from_secret(user_secret)

    # 3. Generate lock keypair (launch key)
    lock_keys = Keypair.random()
    lock_25519 = Stellar25519KeyPair(lock_keys)

    # 4. Build launch token
    caveats = {'network': NET}
    token_builder = StellarSharedKeyTokenBuilder(
        senderKeyPair=BANKER_25519,
        receiverPub=lock_25519.public_key(),
        token_type=TokenType.SECRET,
        caveats=caveats,
        secret=user_keys.secret,
    )
    launch_token = token_builder.serialize()

    # 5. Email launch key
    try:
        send_launch_key_email(user['email'], lock_keys.secret, user_keys.public_key)
    except Exception:
        pass  # Don't block if email fails

    return launch_token
