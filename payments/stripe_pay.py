import stripe
from config import STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET
from payments.pricing import TIERS, get_tier_price

stripe.api_key = STRIPE_SECRET_KEY


def create_checkout_session(order_id, email, moniker, password_hash,
                            tier_key='forge', base_url='http://localhost:8080'):
    tier = TIERS[tier_key]
    price_usd = get_tier_price(tier_key, 'card', 'join')
    price_cents = int(price_usd * 100)

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'unit_amount': price_cents,
                'product_data': {
                    'name': f'Heavymeta Collective — {tier["label"]} Membership',
                    'description': tier['description'],
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
            'tier': tier_key,
        },
    )
    return session


def create_card_checkout_session(order_id, email, card_id, amount_usd,
                                 base_url='http://localhost:8080'):
    price_cents = int(amount_usd * 100)

    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        line_items=[{
            'price_data': {
                'currency': 'usd',
                'unit_amount': price_cents,
                'product_data': {
                    'name': 'Heavymeta Collective — Custom NFC Card',
                    'description': 'Custom-designed NFC card with your artwork',
                },
            },
            'quantity': 1,
        }],
        mode='payment',
        success_url=f'{base_url}/card/order/success?session_id={{CHECKOUT_SESSION_ID}}',
        cancel_url=f'{base_url}/card/editor',
        customer_email=email,
        metadata={
            'order_id': order_id,
            'card_id': card_id,
            'purchase_type': 'card',
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
        'tier': cs.metadata.get('tier', 'forge'),
        'payment_intent': cs.payment_intent or '',
    }


def handle_webhook(payload, sig_header):
    event = stripe.Webhook.construct_event(
        payload, sig_header, STRIPE_WEBHOOK_SECRET
    )

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        purchase_type = session['metadata'].get('purchase_type', 'enrollment')

        if purchase_type == 'card':
            return {
                'completed': True,
                'purchase_type': 'card',
                'order_id': session['metadata']['order_id'],
                'card_id': session['metadata']['card_id'],
                'payment_intent': session.get('payment_intent', ''),
            }

        return {
            'completed': True,
            'purchase_type': 'enrollment',
            'email': session['metadata']['email'],
            'moniker': session['metadata']['moniker'],
            'password_hash': session['metadata']['password_hash'],
            'order_id': session['metadata']['order_id'],
            'tier': session['metadata'].get('tier', 'forge'),
            'payment_intent': session.get('payment_intent', ''),
        }

    return {'completed': False}
