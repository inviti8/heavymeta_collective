import uuid
from stellar_sdk import Keypair
from hvym_stellar import Stellar25519KeyPair, StellarSharedKey
import db
from auth import hash_password
from email_service import send_welcome_email
from config import BANKER_25519, GUARDIAN_25519, NET
from stellar_ops import fund_account, register_on_roster


async def process_free_enrollment(moniker, email, password):
    password_hash = hash_password(password)
    user_id = str(uuid.uuid4())
    await db.create_user(
        user_id=user_id,
        email=email.strip(),
        moniker=moniker.strip(),
        member_type='free',
        password_hash=password_hash,
    )
    try:
        send_welcome_email(email.strip(), moniker.strip())
    except Exception:
        pass  # Don't block enrollment on email failure
    return user_id


async def process_paid_enrollment(email, moniker, password_hash, order_id,
                                  payment_method, tx_hash, xlm_price_usd=None):
    # 1. Generate user's Stellar keypair
    user_keys = Keypair.random()
    user_25519 = Stellar25519KeyPair(user_keys)

    # 2. Fund user account from Banker (22 XLM)
    fund_account(user_keys.public_key, amount="22")

    # 3. Encrypt user secret with Banker + Guardian dual-key
    encryptor = StellarSharedKey(BANKER_25519, GUARDIAN_25519.public_key())
    encrypted_secret = encryptor.encrypt(user_keys.secret.encode())

    # 4. Store user record
    user_id = str(uuid.uuid4())
    await db.create_user(
        user_id=user_id,
        email=email.strip(),
        moniker=moniker.strip(),
        member_type='coop',
        password_hash=password_hash,
        stellar_address=user_keys.public_key,
        shared_pub=user_25519.public_key(),
        encrypted_token=encrypted_secret.decode() if isinstance(encrypted_secret, bytes) else encrypted_secret,
        network=NET,
    )

    # 5. Store payment record
    from payments.pricing import XLM_COST
    amount = str(XLM_COST) if payment_method == 'stellar' else str(xlm_price_usd or '')
    await db.create_payment(
        user_id=user_id,
        method=payment_method,
        amount=amount,
        xlm_price_usd=xlm_price_usd,
        memo=order_id,
        tx_hash=tx_hash,
        status='completed',
    )

    # 6. Register on roster contract
    try:
        register_on_roster(user_keys, moniker.strip())
    except Exception:
        pass  # Don't block enrollment if roster registration fails

    # 7. Send welcome email
    try:
        send_welcome_email(email.strip(), moniker.strip())
    except Exception:
        pass

    return user_id, user_keys.public_key


async def finalize_pending_enrollment(user_id, order_id, payment_method, tx_hash,
                                      xlm_price_usd=None):
    """For Stripe webhook — user already exists as pending, now complete enrollment."""
    user = await db.get_user_by_id(user_id)
    if not user:
        return None

    # Generate Stellar keypair + fund + encrypt
    user_keys = Keypair.random()
    user_25519 = Stellar25519KeyPair(user_keys)
    fund_account(user_keys.public_key, amount="22")

    encryptor = StellarSharedKey(BANKER_25519, GUARDIAN_25519.public_key())
    encrypted_secret = encryptor.encrypt(user_keys.secret.encode())

    # Update user with Stellar details
    await db.update_user(
        user_id,
        member_type='coop',
        stellar_address=user_keys.public_key,
        shared_pub=user_25519.public_key(),
        encrypted_token=encrypted_secret.decode() if isinstance(encrypted_secret, bytes) else encrypted_secret,
        network=NET,
    )

    # Store payment
    from payments.pricing import XLM_COST
    amount = str(XLM_COST) if payment_method == 'stellar' else str(xlm_price_usd or '')
    await db.create_payment(
        user_id=user_id,
        method=payment_method,
        amount=amount,
        xlm_price_usd=xlm_price_usd,
        memo=order_id,
        tx_hash=tx_hash,
        status='completed',
    )

    # Roster registration
    try:
        register_on_roster(user_keys, user['moniker'])
    except Exception:
        pass

    # Welcome email
    try:
        send_welcome_email(user['email'], user['moniker'])
    except Exception:
        pass

    return user_id, user_keys.public_key
