import mailtrap as mt
from config import MAILTRAP_API_TOKEN, NET, BLOCK_EXPLORER, CARD_VENDOR_EMAIL


def send_welcome_email(email, moniker):
    mail = mt.Mail(
        sender=mt.Address(email="noreply@heavymeta.art", name="Heavymeta Collective"),
        to=[mt.Address(email=email)],
        subject="Welcome to Heavymeta Collective",
        html=f"""
        <h1>Welcome, {moniker}!</h1>
        <p>You're now part of the Heavymeta Collective.</p>
        <p>Log in to customize your profile and link-tree.</p>
        """,
    )
    client = mt.MailtrapClient(token=MAILTRAP_API_TOKEN)
    client.send(mail)


def send_launch_key_email(email, launch_key_secret, stellar_address):
    acct_url = f"{BLOCK_EXPLORER}/account/{stellar_address}"
    mail = mt.Mail(
        sender=mt.Address(email="noreply@heavymeta.art", name="Heavymeta Collective"),
        to=[mt.Address(email=email)],
        subject="Your Pintheon Launch Key",
        html=f"""
        <h1>Your Launch Key</h1>
        <p><strong>Save this securely. You need it + your Launch Token to start your
        Pintheon node.</strong></p>
        <code>{launch_key_secret}</code>
        <h3>Node Address</h3>
        <p>{stellar_address}</p>
        <a href="{acct_url}">{acct_url}</a>
        """,
    )
    client = mt.MailtrapClient(token=MAILTRAP_API_TOKEN)
    client.send(mail)


def send_card_order_email(order, user, card, gateway_base):
    """Send NFC card order details to the vendor for fulfillment."""
    if not CARD_VENDOR_EMAIL:
        return

    order_id = order['id']
    moniker = user['moniker']
    front_link = f"{gateway_base}/ipfs/{card['front_image_cid']}" if card.get('front_image_cid') else 'N/A'
    back_link = f"{gateway_base}/ipfs/{card['back_image_cid']}" if card.get('back_image_cid') else 'N/A'

    try:
        mail = mt.Mail(
            sender=mt.Address(email="noreply@heavymeta.art", name="Heavymeta Collective"),
            to=[mt.Address(email=CARD_VENDOR_EMAIL)],
            subject=f"NFC Card Order — {order_id} — {moniker}",
            html=f"""
            <h1>NFC Card Order</h1>
            <table>
              <tr><td><strong>Order ID</strong></td><td>{order_id}</td></tr>
              <tr><td><strong>Member</strong></td><td>{moniker} ({user['email']})</td></tr>
              <tr><td><strong>Tier</strong></td><td>{user['member_type']}</td></tr>
              <tr><td><strong>Payment</strong></td><td>{order['payment_method']} — ${order['amount_usd']:.2f} USD</td></tr>
            </table>
            <h2>Card Images</h2>
            <p><strong>Front:</strong> <a href="{front_link}">{front_link}</a></p>
            <p><strong>Back:</strong> <a href="{back_link}">{back_link}</a></p>
            <h2>Shipping Address</h2>
            <p>
              {order['shipping_name']}<br>
              {order['shipping_street']}<br>
              {order['shipping_city']}, {order['shipping_state']} {order['shipping_zip']}<br>
              {order['shipping_country']}
            </p>
            """,
        )
        client = mt.MailtrapClient(token=MAILTRAP_API_TOKEN)
        client.send(mail)
    except Exception:
        pass  # don't block order finalization on email failure
