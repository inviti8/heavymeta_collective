from nicegui import ui, app
from auth import validate_signup_form, login_user, set_session, hash_password
from enrollment import process_free_enrollment, process_paid_enrollment
from payments.stellar_pay import create_stellar_payment_request, check_payment
from payments.stripe_pay import create_checkout_session
from payments.pricing import (
    TIERS, get_tier_price, get_xlm_amount,
    async_fetch_xlm_price, fetch_xlm_price,
)
from components import form_field
import db
import uuid as _uuid

_current_dialog = None


def open_auth_dialog(initial_tab='login'):
    global _current_dialog

    if _current_dialog is not None:
        try:
            _current_dialog.close()
        except Exception:
            pass
    _current_dialog = None

    with ui.dialog().props('persistent') as dialog, \
         ui.card().classes('w-full max-w-lg mx-auto p-6 gap-0'):

        # ── Header row ──
        with ui.row().classes('w-full items-center justify-between mb-4'):
            ui.label('HEAVYMETA').classes('text-xl font-semibold tracking-wide')
            ui.button(icon='close', on_click=dialog.close).props('flat round dense')

        # ── Top tabs: LOGIN | JOIN ──
        with ui.tabs().classes('w-full') as tabs:
            login_tab = ui.tab('LOGIN')
            join_tab = ui.tab('JOIN')

        with ui.tab_panels(tabs).classes('w-full'):

            # ══════════ LOGIN PANEL ══════════
            with ui.tab_panel(login_tab):
                email_login = form_field('EMAIL', 'Enter your email')
                pw_login = form_field('PASSWORD', 'Enter your password', True)

                login_error = ui.label('').classes('text-red-500 text-sm')
                login_error.set_visibility(False)

                async def handle_login():
                    login_error.set_visibility(False)
                    if not email_login.value or not pw_login.value:
                        login_error.text = 'Please enter your email and password.'
                        login_error.set_visibility(True)
                        return
                    user, rate_error = await login_user(
                        email_login.value.strip(), pw_login.value
                    )
                    if rate_error:
                        login_error.text = rate_error
                        login_error.set_visibility(True)
                    elif user:
                        set_session(user)
                        dialog.close()
                        ui.navigate.to('/profile/edit')
                    else:
                        login_error.text = 'Invalid email or password.'
                        login_error.set_visibility(True)

                ui.button('LOGIN', on_click=handle_login).classes(
                    'mt-8 px-8 py-3 text-lg w-full'
                )

            # ══════════ JOIN PANEL ══════════
            with ui.tab_panel(join_tab):
                moniker = form_field('MONIKER', 'Create a moniker')
                email_join = form_field('EMAIL', 'Enter your email')
                pw_join = form_field('PASSWORD', 'Create a password', True)

                with ui.column().classes('w-full gap-1'):
                    ui.label('MEMBERSHIP TIER').classes('text-base tracking-widest opacity-70')
                    tier = ui.radio(
                        {
                            'free':           'FREE — Linktree only',
                            'spark':          'SPARK — QR cards, basic access ($29.99 + $49.99/yr)',
                            'forge':          'FORGE — NFC, Pintheon, full access ($59.99 + $99.99/yr)',
                            'founding_forge': 'FOUNDING FORGE — Limited to 100 ($79.99 + $49.99/yr locked)',
                            'anvil':          'ANVIL — Advisory board ($149.99 + $249.99/yr)',
                        },
                        value='free',
                    ).classes('w-full')

                join_error = ui.label('').classes('text-red-500 text-sm')
                join_error.set_visibility(False)

                def update_button_text():
                    if tier.value == 'free':
                        signup_btn.text = 'SIGN UP — FREE'
                    else:
                        signup_btn.text = 'CONTINUE TO PAYMENT'

                tier.on_value_change(lambda: update_button_text())

                async def handle_signup():
                    join_error.set_visibility(False)

                    errors = await validate_signup_form(
                        moniker.value, email_join.value, pw_join.value
                    )
                    if errors:
                        join_error.text = ' '.join(errors)
                        join_error.set_visibility(True)
                        return

                    if tier.value == 'free':
                        try:
                            user_id = await process_free_enrollment(
                                moniker.value, email_join.value, pw_join.value
                            )
                            user = await db.get_user_by_id(user_id)
                            set_session(dict(user))
                            dialog.close()
                            ui.navigate.to('/profile/edit')
                        except Exception as e:
                            join_error.text = f'Signup failed: {e}'
                            join_error.set_visibility(True)
                    else:
                        # Paid tier — close auth dialog, open payment dialog
                        pw_hash = hash_password(pw_join.value)
                        form_data = {
                            'moniker': moniker.value.strip(),
                            'email': email_join.value.strip(),
                            'password_hash': pw_hash,
                            'tier': tier.value,
                        }
                        dialog.close()
                        _open_payment_dialog(form_data)

                signup_btn = ui.button(
                    'SIGN UP — FREE',
                    on_click=handle_signup,
                ).classes('mt-8 px-8 py-3 text-lg w-full')

        # Set initial tab
        tabs.value = initial_tab.upper()

    _current_dialog = dialog
    dialog.open()
    return dialog


# ─── Payment Dialog ───────────────────────────────────────────────────────────

def _open_payment_dialog(form_data):
    """Second dialog: CARD/XLM/OPUS payment tabs for paid signup."""
    global _current_dialog

    _cached_price = None
    tier_key = form_data.get('tier', 'forge')
    tier_info = TIERS[tier_key]

    with ui.dialog().props('persistent') as pay_dialog, \
         ui.card().classes('w-full max-w-lg mx-auto p-6 gap-0') as pay_card:

        with ui.row().classes('w-full items-center justify-between mb-4'):
            ui.label('PAYMENT').classes('text-xl font-semibold tracking-wide')
            ui.button(icon='close', on_click=pay_dialog.close).props('flat round dense')

        ui.label(f'Joining as: {tier_info["label"]}').classes('text-sm font-bold')
        ui.label(tier_info['description']).classes('text-xs opacity-60 mb-2')

        with ui.tabs().classes('w-full') as pay_tabs:
            card_tab = ui.tab('CARD')
            xlm_tab = ui.tab('XLM')
            opus_tab = ui.tab('OPUS')
        pay_tabs.value = 'CARD'

        with ui.tab_panels(pay_tabs).classes('w-full'):
            with ui.tab_panel(card_tab):
                card_price_label = ui.label(
                    'PRICE: calculating...'
                ).classes('text-lg font-bold')

            with ui.tab_panel(xlm_tab):
                xlm_price_label = ui.label(
                    'PRICE: calculating...'
                ).classes('text-lg font-bold')
                ui.label('Save 50% when you pay with XLM').classes(
                    'text-sm text-amber-600 font-medium'
                )

            with ui.tab_panel(opus_tab):
                opus_price_label = ui.label(
                    'Coming soon'
                ).classes('text-lg font-bold')
                ui.label(
                    'Pay with silk — deepest discount (60% off)'
                ).classes('text-sm text-amber-600 font-medium')
                ui.label(
                    'OPUS payment will be available in a future update.'
                ).classes('text-xs opacity-60')

        pay_error = ui.label('').classes('text-red-500 text-sm')
        pay_error.set_visibility(False)

        # ── Async price loading (fires immediately) ──
        async def load_prices():
            nonlocal _cached_price
            if _cached_price is not None:
                return
            price = await async_fetch_xlm_price()
            _cached_price = price

            # Card: base USD price
            card_usd = get_tier_price(tier_key, 'card', 'join')
            card_price_label.text = f'PRICE: ${card_usd:.2f} USD'

            # XLM: discounted price in XLM
            xlm_usd = get_tier_price(tier_key, 'xlm', 'join')
            xlm_amount = round(xlm_usd / price, 2) if price > 0 else 0
            xlm_price_label.text = f'PRICE: {xlm_amount} XLM (~${xlm_usd:.2f} USD)'

            update_pay_button()

        def update_pay_button():
            if pay_tabs.value == 'CARD':
                usd = get_tier_price(tier_key, 'card', 'join')
                pay_btn.text = f'SIGN UP — PAY ${usd:.2f}'
                pay_btn.enable()
            elif pay_tabs.value == 'XLM':
                xlm_usd = get_tier_price(tier_key, 'xlm', 'join')
                if _cached_price and _cached_price > 0:
                    xlm_amt = round(xlm_usd / _cached_price, 2)
                    pay_btn.text = f'SIGN UP — PAY {xlm_amt} XLM'
                else:
                    pay_btn.text = 'SIGN UP — PAY WITH XLM'
                pay_btn.enable()
            elif pay_tabs.value == 'OPUS':
                pay_btn.text = 'COMING SOON'
                pay_btn.disable()

        pay_tabs.on_value_change(lambda: update_pay_button())

        async def handle_pay():
            pay_error.set_visibility(False)

            if pay_tabs.value == 'XLM':
                # XLM payment — transition to QR view
                pay_req = create_stellar_payment_request(tier_key=tier_key)
                pending = {
                    **form_data,
                    'order_id': pay_req['order_id'],
                    'memo': pay_req['memo'],
                    'qr': pay_req['qr'],
                    'address': pay_req['address'],
                    'amount': pay_req['amount'],
                }
                app.storage.user['pending_signup'] = pending
                _show_xlm_payment(pay_card, pending, pay_dialog)
            elif pay_tabs.value == 'CARD':
                # Stripe payment — user created by webhook after payment confirmed
                try:
                    order_id = f"stripe-{_uuid.uuid4().hex[:8]}"
                    session = create_checkout_session(
                        order_id=order_id,
                        email=form_data['email'],
                        moniker=form_data['moniker'],
                        password_hash=form_data['password_hash'],
                        tier_key=tier_key,
                    )
                    # Store email + tier so /join/success can poll by email
                    app.storage.user['pending_stripe'] = {
                        'email': form_data['email'],
                        'tier': tier_key,
                    }
                    pay_dialog.close()
                    await ui.run_javascript(
                        f"window.location.href='{session.url}'"
                    )
                except Exception as e:
                    pay_error.text = f'Payment setup failed: {e}'
                    pay_error.set_visibility(True)

        card_usd = get_tier_price(tier_key, 'card', 'join')
        pay_btn = ui.button(
            f'SIGN UP — PAY ${card_usd:.2f}',
            on_click=handle_pay,
        ).classes('mt-8 px-8 py-3 text-lg w-full')

    _current_dialog = pay_dialog
    pay_dialog.open()

    # Fire async price load after dialog is open
    ui.timer(0.1, load_prices, once=True)


# ─── XLM QR Payment View ─────────────────────────────────────────────────────

def _show_xlm_payment(pay_card, pending, pay_dialog):
    """Transition payment dialog content to QR payment view."""
    _timer_ref = None

    def cleanup_and_close():
        nonlocal _timer_ref
        if _timer_ref is not None:
            try:
                _timer_ref.deactivate()
            except Exception:
                pass
            _timer_ref = None
        if app.storage.user.get('pending_signup'):
            del app.storage.user['pending_signup']
        pay_dialog.close()

    pay_card.clear()
    with pay_card:
        with ui.row().classes('w-full items-center justify-between mb-4'):
            ui.label('COMPLETE YOUR PAYMENT').classes('text-xl font-semibold tracking-wide')
            ui.button(icon='close', on_click=cleanup_and_close).props('flat round dense')

        ui.label(f'Send exactly {pending["amount"]} XLM to:').classes('text-lg')

        with ui.card().classes('w-full items-center p-6 gap-4'):
            ui.image(pending['qr']).classes('w-64 h-64')

            with ui.row().classes('items-center gap-2 w-full'):
                ui.label('Address:').classes('font-bold text-sm')
                ui.label(pending['address']).classes('text-xs font-mono break-all flex-1')
                ui.button(icon='content_copy', on_click=lambda: ui.run_javascript(
                    f"navigator.clipboard.writeText('{pending['address']}')"
                )).props('flat dense size=sm')

            with ui.row().classes('items-center gap-2'):
                ui.label('Amount:').classes('font-bold text-sm')
                ui.label(f'{pending["amount"]} XLM').classes('text-sm')

            with ui.row().classes('items-center gap-2 w-full'):
                ui.label('Memo:').classes('font-bold text-sm')
                ui.label(pending['memo']).classes('text-xs font-mono flex-1')
                ui.button(icon='content_copy', on_click=lambda: ui.run_javascript(
                    f"navigator.clipboard.writeText('{pending['memo']}')"
                )).props('flat dense size=sm')

            ui.separator()
            status_label = ui.label('Waiting for payment...').classes('text-sm opacity-70')
            spinner = ui.spinner('dots', size='lg')

        async def check_and_update():
            result = check_payment(pending['memo'])
            if result['paid']:
                _timer_ref.deactivate()
                spinner.set_visibility(False)
                status_label.text = 'Payment confirmed!'

                try:
                    xlm_price = fetch_xlm_price()
                    tier = pending.get('tier', 'forge')
                    user_id, stellar_address = await process_paid_enrollment(
                        email=pending['email'],
                        moniker=pending['moniker'],
                        password_hash=pending['password_hash'],
                        order_id=pending['order_id'],
                        payment_method='stellar',
                        tx_hash=result['hash'],
                        tier_key=tier,
                        xlm_price_usd=xlm_price,
                    )
                    user = await db.get_user_by_id(user_id)
                    set_session(dict(user))
                    if app.storage.user.get('pending_signup'):
                        del app.storage.user['pending_signup']
                    pay_dialog.close()
                    ui.navigate.to('/profile/edit')
                except Exception as e:
                    status_label.text = f'Payment received but enrollment failed: {e}'

        _timer_ref = ui.timer(5.0, check_and_update)
