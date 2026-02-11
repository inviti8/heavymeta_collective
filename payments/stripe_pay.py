import stripe
from config import STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
from payments.pricing import get_stripe_price_cents, fetch_xlm_price

stripe.api_key = STRIPE_SECRET_KEY


def create_checkout_session(order_id, email, moniker, password_hash, base_url='http://localhost:8080'):
    price_cents = get_stripe_price_cents()
    xlm_price = fetch_xlm_price()

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'unit_amount': price_cents,
                'product_data': {
                    'name': 'Heavymeta Collective — Coop Membership',
                    'description': 'Full access membership with NFC card and Pintheon node',
                },
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url=f'{base_url}/join/success?session_id={{CHECKOUT_SESSION_ID}}',
        cancel_url=f'{base_url}/join',
        customer_email=email,
        metadata={
            'order_id': order_id,
            'email': email,
            'moniker': moniker,
            'password_hash': password_hash,
            'xlm_price_usd': str(xlm_price),
        },
    )
    return session


def retrieve_checkout_session(session_id):
    """Retrieve a completed Stripe checkout session and extract enrollment data."""
    cs = stripe.checkout.Session.retrieve(session_id)
    if cs.payment_status != 'paid':
        return None
    return {
        'email': cs.metadata['email'],
        'moniker': cs.metadata['moniker'],
        'password_hash': cs.metadata['password_hash'],
        'order_id': cs.metadata['order_id'],
        'xlm_price_usd': float(cs.metadata.get('xlm_price_usd', 0)),
        'payment_intent': cs.payment_intent or '',
    }


def handle_webhook(payload, sig_header):
    event = stripe.Webhook.construct_event(
        payload, sig_header, STRIPE_WEBHOOK_SECRET
    )

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        return {
            'completed': True,
            'email': session['metadata']['email'],
            'moniker': session['metadata']['moniker'],
            'password_hash': session['metadata']['password_hash'],
            'order_id': session['metadata']['order_id'],
            'xlm_price_usd': float(session['metadata'].get('xlm_price_usd', 0)),
            'payment_intent': session.get('payment_intent', ''),
        }

    return {'completed': False}
