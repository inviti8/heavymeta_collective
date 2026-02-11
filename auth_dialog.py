from nicegui import ui, app
from auth import validate_signup_form, login_user, set_session, hash_password
from enrollment import process_free_enrollment, process_paid_enrollment
from payments.stellar_pay import create_stellar_payment_request, check_payment
from payments.stripe_pay import create_checkout_session
from payments.pricing import XLM_COST, async_fetch_xlm_price, fetch_xlm_price
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
                        {'free': 'FREE — Link-tree only', 'coop': 'COOP MEMBER — Full access'},
                        value='free',
                    ).classes('w-full')

                join_error = ui.label('').classes('text-red-500 text-sm')
                join_error.set_visibility(False)

                def update_button_text():
                    if tier.value == 'coop':
                        signup_btn.text = 'CONTINUE TO PAYMENT'
                    else:
                        signup_btn.text = 'SIGN UP — FREE'

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
                        # Coop — close auth dialog, open payment dialog
                        pw_hash = hash_password(pw_join.value)
                        form_data = {
                            'moniker': moniker.value.strip(),
                            'email': email_join.value.strip(),
                            'password_hash': pw_hash,
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
    """Second dialog: XLM/CARD payment tabs for coop signup."""
    global _current_dialog

    _cached_price = None

    with ui.dialog().props('persistent') as pay_dialog, \
         ui.card().classes('w-full max-w-lg mx-auto p-6 gap-0') as pay_card:

        with ui.row().classes('w-full items-center justify-between mb-4'):
            ui.label('PAYMENT').classes('text-xl font-semibold tracking-wide')
            ui.button(icon='close', on_click=pay_dialog.close).props('flat round dense')

        with ui.tabs().classes('w-full') as pay_tabs:
            xlm_tab = ui.tab('XLM')
            card_tab = ui.tab('CARD')

        with ui.tab_panels(pay_tabs).classes('w-full'):
            with ui.tab_panel(xlm_tab):
                xlm_price_label = ui.label(
                    f'PRICE: {XLM_COST} XLM'
                ).classes('text-lg font-bold')

            with ui.tab_panel(card_tab):
                card_price_label = ui.label(
                    'PRICE: calculating...'
                ).classes('text-lg font-bold')
                ui.label(
                    'Join the future. Pay less with crypto.'
                ).classes('text-sm opacity-70 italic')

        pay_error = ui.label('').classes('text-red-500 text-sm')
        pay_error.set_visibility(False)

        # ── Async price loading (fires immediately) ──
        async def load_prices():
            nonlocal _cached_price
            if _cached_price is not None:
                return
            price = await async_fetch_xlm_price()
            _cached_price = price
            usd = round(XLM_COST * price, 2)
            xlm_price_label.text = f'PRICE: {XLM_COST} XLM (~${usd:.2f} USD)'
            stripe_usd = round(XLM_COST * price * 2, 2)
            card_price_label.text = f'PRICE: ${stripe_usd:.2f} USD (2x crypto price)'
            update_pay_button()

        def update_pay_button():
            if pay_tabs.value == 'CARD':
                if _cached_price is not None:
                    stripe_usd = round(XLM_COST * _cached_price * 2, 2)
                    pay_btn.text = f'SIGN UP — PAY ${stripe_usd:.2f}'
                else:
                    pay_btn.text = 'SIGN UP — PAY BY CARD'
            else:
                pay_btn.text = f'SIGN UP — PAY {XLM_COST} XLM'

        pay_tabs.on_value_change(lambda: update_pay_button())

        async def handle_pay():
            pay_error.set_visibility(False)

            if pay_tabs.value != 'CARD':
                # XLM payment — transition to QR view
                pay_req = create_stellar_payment_request()
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
            else:
                # Stripe payment — user created by webhook after payment confirmed
                try:
                    order_id = f"stripe-{_uuid.uuid4().hex[:8]}"
                    session = create_checkout_session(
                        order_id=order_id,
                        email=form_data['email'],
                        moniker=form_data['moniker'],
                        password_hash=form_data['password_hash'],
                    )
                    # Store email so /join/success can poll by email
                    app.storage.user['pending_stripe'] = {
                        'email': form_data['email'],
                    }
                    pay_dialog.close()
                    await ui.run_javascript(
                        f"window.location.href='{session.url}'"
                    )
                except Exception as e:
                    pay_error.text = f'Payment setup failed: {e}'
                    pay_error.set_visibility(True)

        pay_btn = ui.button(
            f'SIGN UP — PAY {XLM_COST} XLM',
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
                    user_id, stellar_address = await process_paid_enrollment(
                        email=pending['email'],
                        moniker=pending['moniker'],
                        password_hash=pending['password_hash'],
                        order_id=pending['order_id'],
                        payment_method='stellar',
                        tx_hash=result['hash'],
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
