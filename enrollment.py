import uuid
from stellar_sdk import Keypair
from hvym_stellar import Stellar25519KeyPair, StellarSharedKey
import db
import ipfs_client
from auth import hash_password
from email_service import send_welcome_email
from config import BANKER_25519, GUARDIAN_25519, NET
from stellar_ops import fund_account, register_on_roster


async def _setup_ipns(user_id, moniker, member_type, stellar_address=None):
    """Generate IPNS key, publish initial linktree, store in DB."""
    key_name = f"{user_id}-linktree"
    ipns_name = await ipfs_client.ipns_key_gen(key_name)

    # Export key and encrypt with Guardian for backup
    key_bytes = await ipfs_client.ipns_key_export(key_name)
    encryptor = StellarSharedKey(BANKER_25519, GUARDIAN_25519.public_key())
    encrypted_backup = encryptor.encrypt(key_bytes)

    # Build initial (empty) linktree JSON
    initial_linktree = ipfs_client.build_linktree_json(
        moniker=moniker,
        member_type=member_type,
        stellar_address=stellar_address,
        links=[],
        colors=None,
    )
    new_cid, _ = await ipfs_client.publish_linktree(key_name, initial_linktree)

    # Update user record with IPNS data
    await db.update_user(
        user_id,
        ipns_key_name=key_name,
        ipns_name=ipns_name,
        linktree_cid=new_cid,
        ipns_key_backup=encrypted_backup.decode() if isinstance(encrypted_backup, bytes) else encrypted_backup,
    )
    return ipns_name


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

    try:
        await _setup_ipns(user_id, moniker.strip(), 'free')
    except Exception:
        pass  # IPFS setup can be retried later

    return user_id


async def process_paid_enrollment(email, moniker, password_hash, order_id,
                                  payment_method, tx_hash, tier_key='forge',
                                  xlm_price_usd=None):
    from payments.pricing import get_tier_price

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
        member_type=tier_key,
        password_hash=password_hash,
        stellar_address=user_keys.public_key,
        shared_pub=user_25519.public_key(),
        encrypted_token=encrypted_secret.decode() if isinstance(encrypted_secret, bytes) else encrypted_secret,
        network=NET,
    )

    # 5. Store payment record
    price_usd = get_tier_price(tier_key, payment_method if payment_method == 'stellar' else 'card', 'join')
    await db.create_payment(
        user_id=user_id,
        method=payment_method,
        amount=str(price_usd),
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

    # 8. IPNS key + initial linktree
    try:
        await _setup_ipns(user_id, moniker.strip(), tier_key, user_keys.public_key)
    except Exception:
        pass  # IPFS setup can be retried later

    return user_id, user_keys.public_key


async def finalize_pending_enrollment(user_id, order_id, payment_method, tx_hash,
                                      tier_key='forge', xlm_price_usd=None):
    """For Stripe webhook — user already exists as pending, now complete enrollment."""
    from payments.pricing import get_tier_price

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
        member_type=tier_key,
        stellar_address=user_keys.public_key,
        shared_pub=user_25519.public_key(),
        encrypted_token=encrypted_secret.decode() if isinstance(encrypted_secret, bytes) else encrypted_secret,
        network=NET,
    )

    # Store payment
    price_usd = get_tier_price(tier_key, payment_method if payment_method == 'stellar' else 'card', 'join')
    await db.create_payment(
        user_id=user_id,
        method=payment_method,
        amount=str(price_usd),
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

    # IPNS key + initial linktree
    try:
        await _setup_ipns(user_id, user['moniker'], tier_key, user_keys.public_key)
    except Exception:
        pass  # IPFS setup can be retried later

    return user_id, user_keys.public_key
