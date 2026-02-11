import config  # noqa: F401 — triggers startup validation
import db
from nicegui import ui, app
from fastapi import Request, HTTPException
import os
from components import style_page, form_field, image_with_text, dashboard_nav, dashboard_header
from auth import (
    validate_signup_form, login_user, set_session, require_auth, require_coop,
    hash_password,
)
from enrollment import process_free_enrollment, process_paid_enrollment, finalize_pending_enrollment
from payments.pricing import XLM_COST, get_xlm_usd_equivalent, get_stripe_price_display, fetch_xlm_price
from payments.stellar_pay import create_stellar_payment_request, check_payment
from payments.stripe_pay import create_checkout_session, handle_webhook
from launch import generate_launch_credentials

static_files_dir = os.path.join(os.path.dirname(__file__), 'static')
app.add_static_files('/static', static_files_dir)
app.on_startup(db.init_db)


# ─── Stripe Webhook (FastAPI route) ───────────────────────────────────────────

@app.post('/api/stripe/webhook')
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    try:
        result = handle_webhook(payload, sig_header)
    except Exception:
        raise HTTPException(status_code=400, detail='Invalid signature')

    if result.get('completed'):
        await finalize_pending_enrollment(
            user_id=result['user_id'],
            order_id=result['order_id'],
            payment_method='stripe',
            tx_hash=result['payment_intent'],
            xlm_price_usd=result.get('xlm_price_usd'),
        )
    return {'status': 'ok'}


# ─── Landing ──────────────────────────────────────────────────────────────────

@ui.page('/')
def landing():
    style_page('HEAVYMETA COLLECTIVE')

    with ui.column(
    ).classes('w-full items-center gap-16 mt-12'
    ).style('padding-inline: clamp(1rem, 20vw, 50rem);'):
        ui.image('/static/placeholder.png'
            ).classes('w-full max-w-5l'
            ).props('fit=cover')

        image_with_text('static/placeholder.png', 'lorem ipsum')
        image_with_text('static/placeholder.png', 'lorem ipsum')

        ui.button(
            'JOIN',
            on_click=lambda: ui.navigate.to('/join'),
        ).classes('mt-8 px-8 py-3 text-lg w-1/2')


# ─── Join ─────────────────────────────────────────────────────────────────────

@ui.page('/join')
def join():
    style_page('Join HEAVYMETA')

    with ui.column(
    ).classes(
        'w-full items-center gap-8 mt-12'
    ).style(
        'padding-inline: clamp(1rem, 35vw, 50rem);'
    ):
        ui.label('JOIN').classes('text-5xl font-semibold tracking-wide')
        with ui.row().classes('items-center gap-2'):
            ui.label('Already Registered?').classes('text-xl tracking-wide')
            ui.link('Login', '/login').classes('text-primary text-xl font-bold tracking-wide no-underline')

        moniker = form_field('MONIKER', 'Create a moniker')
        email = form_field('EMAIL', 'Enter your email')
        password = form_field('PASSWORD', 'Create a password', True)

        with ui.column().classes('w-full gap-1'):
            ui.label('MEMBERSHIP TIER').classes('text-base tracking-widest opacity-70')
            tier = ui.radio(
                {'free': 'FREE — Link-tree only', 'coop': 'COOP MEMBER — Full access'},
                value='free',
            ).classes('w-full')

        error_label = ui.label('').classes('text-red-500 text-sm')
        error_label.set_visibility(False)

        # ── Payment section (coop only) ──
        with ui.column().classes('w-full gap-4') as payment_section:
            ui.separator()
            ui.label('PAYMENT METHOD').classes('text-base tracking-widest opacity-70')
            with ui.row().classes('items-center gap-2'):
                ui.label('XLM').classes('text-sm font-bold')
                payment_toggle = ui.switch('', value=False)
                ui.label('CARD').classes('text-sm font-bold')

            # XLM details panel
            with ui.column().classes('w-full gap-2') as xlm_panel:
                try:
                    usd_equiv = get_xlm_usd_equivalent()
                    ui.label(f'PRICE: {XLM_COST} XLM (~${usd_equiv:.2f} USD)').classes('text-lg font-bold')
                except Exception:
                    ui.label(f'PRICE: {XLM_COST} XLM').classes('text-lg font-bold')

            xlm_panel.bind_visibility_from(payment_toggle, 'value', backward=lambda v: not v)

            # Card details panel
            with ui.column().classes('w-full gap-2') as card_panel:
                try:
                    stripe_display = get_stripe_price_display()
                    ui.label(f'PRICE: {stripe_display} USD (2x crypto price)').classes('text-lg font-bold')
                except Exception:
                    ui.label('PRICE: calculating...').classes('text-lg font-bold')
                ui.label('Join the future. Pay less with crypto.').classes('text-sm opacity-70 italic')

            card_panel.bind_visibility_from(payment_toggle, 'value', backward=lambda v: v)

        payment_section.bind_visibility_from(tier, 'value', backward=lambda v: v == 'coop')

        # ── Signup handler ──
        async def handle_signup():
            error_label.set_visibility(False)

            errors = await validate_signup_form(moniker.value, email.value, password.value)
            if errors:
                error_label.text = ' '.join(errors)
                error_label.set_visibility(True)
                return

            if tier.value == 'free':
                try:
                    user_id = await process_free_enrollment(
                        moniker.value, email.value, password.value
                    )
                    user = await db.get_user_by_id(user_id)
                    set_session(dict(user))
                    ui.navigate.to('/profile/edit')
                except Exception as e:
                    error_label.text = f'Signup failed: {e}'
                    error_label.set_visibility(True)
            else:
                # Coop — route to payment
                pw_hash = hash_password(password.value)
                if not payment_toggle.value:
                    # XLM payment
                    pay_req = create_stellar_payment_request()
                    # Store form data in session for the QR page
                    app.storage.user['pending_signup'] = {
                        'moniker': moniker.value.strip(),
                        'email': email.value.strip(),
                        'password_hash': pw_hash,
                        'order_id': pay_req['order_id'],
                        'memo': pay_req['memo'],
                        'qr': pay_req['qr'],
                        'address': pay_req['address'],
                        'amount': pay_req['amount'],
                    }
                    ui.navigate.to('/join/pay/xlm')
                else:
                    # Stripe payment — create pending user, redirect to Stripe
                    try:
                        user_id = await db.create_user(
                            email=email.value.strip(),
                            moniker=moniker.value.strip(),
                            member_type='free',  # pending, will be upgraded by webhook
                            password_hash=pw_hash,
                        )
                        order_id = f"stripe-{user_id[:8]}"
                        session = create_checkout_session(
                            order_id=order_id,
                            email=email.value.strip(),
                            moniker=moniker.value.strip(),
                            user_id=user_id,
                        )
                        await ui.run_javascript(f"window.location.href='{session.url}'")
                    except Exception as e:
                        error_label.text = f'Payment setup failed: {e}'
                        error_label.set_visibility(True)

        def update_button_text():
            if tier.value == 'coop':
                if payment_toggle.value:
                    try:
                        signup_btn.text = f'SIGN UP — PAY {get_stripe_price_display()}'
                    except Exception:
                        signup_btn.text = 'SIGN UP — PAY BY CARD'
                else:
                    signup_btn.text = f'SIGN UP — PAY {XLM_COST} XLM'
            else:
                signup_btn.text = 'SIGN UP — FREE'

        signup_btn = ui.button(
            'SIGN UP — FREE',
            on_click=handle_signup,
        ).classes('mt-8 px-8 py-3 text-lg w-1/2')

        tier.on_value_change(lambda: update_button_text())
        payment_toggle.on_value_change(lambda: update_button_text())


# ─── XLM Payment Page ────────────────────────────────────────────────────────

@ui.page('/join/pay/xlm')
def pay_xlm():
    style_page('Complete Payment')

    pending = app.storage.user.get('pending_signup')
    if not pending:
        ui.navigate.to('/join')
        return

    with ui.column(
    ).classes('w-full items-center gap-8 mt-12'
    ).style('padding-inline: clamp(1rem, 25vw, 50rem);'):
        ui.label('COMPLETE YOUR PAYMENT').classes('text-3xl font-semibold tracking-wide')
        ui.label(f'Send exactly {pending["amount"]} XLM to:').classes('text-lg')

        with ui.card().classes('w-full items-center p-6 gap-4'):
            # QR code
            ui.image(pending['qr']).classes('w-64 h-64')

            # Address with copy
            with ui.row().classes('items-center gap-2 w-full'):
                ui.label('Address:').classes('font-bold text-sm')
                addr_label = ui.label(pending['address']).classes('text-xs font-mono break-all flex-1')
                ui.button(icon='content_copy', on_click=lambda: ui.run_javascript(
                    f"navigator.clipboard.writeText('{pending['address']}')"
                )).props('flat dense size=sm')

            # Amount
            with ui.row().classes('items-center gap-2'):
                ui.label('Amount:').classes('font-bold text-sm')
                ui.label(f'{pending["amount"]} XLM').classes('text-sm')

            # Memo with copy
            with ui.row().classes('items-center gap-2 w-full'):
                ui.label('Memo:').classes('font-bold text-sm')
                ui.label(pending['memo']).classes('text-xs font-mono flex-1')
                ui.button(icon='content_copy', on_click=lambda: ui.run_javascript(
                    f"navigator.clipboard.writeText('{pending['memo']}')"
                )).props('flat dense size=sm')

            ui.separator()
            status_label = ui.label('Waiting for payment...').classes('text-sm opacity-70')
            spinner = ui.spinner('dots', size='lg')

        # Poll for payment
        async def check_and_update():
            result = check_payment(pending['memo'])
            if result['paid']:
                timer.deactivate()
                spinner.set_visibility(False)
                status_label.text = 'Payment confirmed!'

                # Process enrollment
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
                    # Auto-login and redirect to dashboard
                    user = await db.get_user_by_id(user_id)
                    set_session(dict(user))
                    del app.storage.user['pending_signup']
                    ui.navigate.to('/profile/edit')
                except Exception as e:
                    status_label.text = f'Payment received but enrollment failed: {e}'

        timer = ui.timer(5.0, check_and_update)


# ─── Success Page ─────────────────────────────────────────────────────────────

@ui.page('/join/success')
async def join_success():
    """Stripe redirects here after checkout. Webhook may have already completed enrollment."""
    # If already logged in as coop, go straight to dashboard
    if app.storage.user.get('authenticated') and app.storage.user.get('member_type') == 'coop':
        ui.navigate.to('/profile/edit')
        return

    # Webhook may still be processing — poll until user is upgraded
    user_id = app.storage.user.get('user_id')

    style_page('Welcome!')

    with ui.column(
    ).classes('w-full items-center gap-8 mt-12'
    ).style('padding-inline: clamp(1rem, 25vw, 50rem);'):
        ui.label('FINALIZING YOUR MEMBERSHIP...').classes('text-3xl font-semibold tracking-wide')
        spinner = ui.spinner('dots', size='lg')
        status_label = ui.label('Waiting for payment confirmation...').classes('text-sm opacity-70')

    async def check_enrollment():
        if not user_id:
            status_label.text = 'Session expired. Please log in.'
            spinner.set_visibility(False)
            timer.deactivate()
            return
        user = await db.get_user_by_id(user_id)
        if user and user['member_type'] == 'coop':
            timer.deactivate()
            set_session(dict(user))
            ui.navigate.to('/profile/edit')

    timer = ui.timer(3.0, check_enrollment)


# ─── Login ────────────────────────────────────────────────────────────────────

@ui.page('/login')
def login():
    style_page('HEAVYMETA Login')

    with ui.column(
    ).classes(
        'w-full items-center gap-8 mt-12'
    ).style(
        'padding-inline: clamp(1rem, 35vw, 50rem);'
    ):
        ui.label('LOGIN').classes('text-5xl font-semibold tracking-wide')

        email = form_field('EMAIL', 'Enter your email')
        password = form_field('PASSWORD', 'Enter your password', True)

        error_label = ui.label('').classes('text-red-500 text-sm')
        error_label.set_visibility(False)

        async def handle_login():
            error_label.set_visibility(False)
            if not email.value or not password.value:
                error_label.text = 'Please enter your email and password.'
                error_label.set_visibility(True)
                return

            user, rate_error = await login_user(email.value.strip(), password.value)
            if rate_error:
                error_label.text = rate_error
                error_label.set_visibility(True)
            elif user:
                set_session(user)
                ui.navigate.to('/profile/edit')
            else:
                error_label.text = 'Invalid email or password.'
                error_label.set_visibility(True)

        ui.button(
            'LOGIN',
            on_click=handle_login,
        ).classes('mt-8 px-8 py-3 text-lg w-1/2')


# ─── Dashboard (Profile) ─────────────────────────────────────────────────────

@ui.page('/profile/edit')
async def profile():
    if not require_auth():
        return

    user_id = app.storage.user.get('user_id')
    user = await db.get_user_by_id(user_id)
    moniker = user['moniker'] if user else app.storage.user.get('moniker', 'Unknown')
    member_type = app.storage.user.get('member_type', 'free')
    psettings = await db.get_profile_settings(user_id)

    dashboard_header(moniker, member_type, user_id=user_id,
                     override_enabled=bool(psettings['linktree_override']),
                     override_url=psettings['linktree_url'])

    with ui.column().classes('w-full items-center gap-8 mt-1 pb-24'):
        # Upgrade CTA for free users
        if member_type == 'free':
            with ui.card().classes('w-[75vw] bg-gradient-to-r from-purple-100 to-yellow-100'):
                ui.label('Join the Coop').classes('text-xl font-bold')
                ui.label('Get full access, NFC card, and Pintheon node credentials.').classes('text-sm opacity-70')
                ui.button('UPGRADE', on_click=lambda: ui.navigate.to('/join')).classes('mt-2')

        # ── Links section with CRUD ──
        with ui.column().classes('w-[75vw] gap-2 border p-4 rounded-lg'):
            ui.label('LINKS').classes('text-2xl font-bold')

            @ui.refreshable
            async def links_section():
                links = await db.get_links(user_id)
                if links:
                    for link in links:
                        link_id = link['id']
                        with ui.row().classes(
                            'items-center bg-gray-100 py-2 px-4 rounded-full w-full gap-3'
                        ):
                            ui.image(
                                link['icon_url'] or '/static/placeholder.png'
                            ).classes('rounded-full w-8 h-8')
                            ui.label(link['label']).classes(
                                'font-semibold text-sm'
                            ).style('min-width: 100px;')
                            ui.link(link['url'], link['url'], new_tab=True).classes(
                                'text-gray-500 text-sm flex-1 truncate'
                            )
                            ui.button(
                                icon='edit',
                                on_click=lambda lid=link_id, lbl=link['label'], url=link['url']: open_edit_dialog(lid, lbl, url),
                            ).props('flat dense size=sm')
                            ui.button(
                                icon='delete',
                                on_click=lambda lid=link_id: confirm_delete(lid),
                            ).props('flat dense size=sm color=red')

                # Add link row
                with ui.row().classes('items-center w-full gap-2'):
                    async def add_link():
                        if add_label.value and add_url.value:
                            await db.create_link(
                                user_id=user_id,
                                label=add_label.value.strip(),
                                url=add_url.value.strip(),
                            )
                            add_label.value = ''
                            add_url.value = ''
                            links_section.refresh()

                    ui.button(icon='add', on_click=add_link).props(
                        'round outline dense size=sm'
                    ).classes('text-black')
                    add_label = ui.input('Label').props('outlined dense rounded').classes('w-28')
                    add_url = ui.input('URL').props('outlined dense rounded').classes('flex-1')

                # Empty placeholder slots
                for _ in range(4):
                    ui.element('div').classes(
                        'w-full h-10 bg-gray-100 rounded-full'
                    )

            await links_section()

            # Edit dialog
            async def open_edit_dialog(link_id, current_label, current_url):
                with ui.dialog() as dialog, ui.card().classes('p-4 gap-4 min-w-[300px]'):
                    ui.label('Edit Link').classes('text-lg font-bold')
                    edit_label = ui.input('Label', value=current_label).classes('w-full').props('outlined')
                    edit_url = ui.input('URL', value=current_url).classes('w-full').props('outlined')

                    with ui.row().classes('justify-end gap-2'):
                        ui.button('Cancel', on_click=dialog.close).props('flat')

                        async def save_edit():
                            if edit_label.value and edit_url.value:
                                await db.update_link(
                                    link_id,
                                    label=edit_label.value.strip(),
                                    url=edit_url.value.strip(),
                                )
                                dialog.close()
                                links_section.refresh()

                        ui.button('Save', on_click=save_edit)
                dialog.open()

            # Delete confirmation
            async def confirm_delete(link_id):
                with ui.dialog() as dialog, ui.card().classes('p-4 gap-4'):
                    ui.label('Delete this link?').classes('text-lg')
                    with ui.row().classes('justify-end gap-2'):
                        ui.button('Cancel', on_click=dialog.close).props('flat')

                        async def do_delete():
                            await db.delete_link(link_id)
                            dialog.close()
                            links_section.refresh()

                        ui.button('Delete', on_click=do_delete).props('color=red')
                dialog.open()

        # Wallets section (coop only)
        if member_type == 'coop':
            with ui.column().classes('w-[75vw] gap-1 border p-4 rounded-lg'):
                ui.label('WALLETS').classes('text-2xl font-bold')
                if user and user['stellar_address']:
                    with ui.row().classes('items-center gap-2 w-full'):
                        ui.image('/static/placeholder.png').classes('rounded-full w-8 h-8')
                        ui.label(f"{user['stellar_address']}").classes('text-sm font-mono break-all flex-1')

    dashboard_nav(active='dashboard')


# ─── Card Editor (shell) ────────────────────────────────────────────────────

@ui.page('/card/editor')
async def card_editor():
    if not require_auth():
        return

    user_id = app.storage.user.get('user_id')
    user = await db.get_user_by_id(user_id)
    moniker = user['moniker'] if user else app.storage.user.get('moniker', 'Unknown')
    member_type = app.storage.user.get('member_type', 'free')
    psettings = await db.get_profile_settings(user_id)

    dashboard_header(moniker, member_type, user_id=user_id,
                     override_enabled=bool(psettings['linktree_override']),
                     override_url=psettings['linktree_url'])

    with ui.column().classes('w-full items-center gap-8 mt-1 pb-24'):
        with ui.column().classes('w-[75vw] gap-4'):
            # Editor tabs
            with ui.row().classes('gap-2'):
                ui.button('PREVIEW', on_click=lambda: None).classes('px-4 py-1')
                ui.button('CODE', on_click=lambda: None).props('outline').classes('px-4 py-1')
                ui.space()
                ui.button('DELETE', on_click=lambda: None).props('flat color=red').classes('px-4 py-1')

            # Card preview area
            with ui.card().classes('w-full aspect-video'):
                ui.image('/static/placeholder.png').classes('w-full h-full').props('fit=cover')

            # Placeholder controls
            with ui.card().classes('w-full p-4 gap-2'):
                ui.label('CARD DESIGN').classes('text-lg font-bold')
                ui.label('Upload an image or edit the HTML for your NFC card.').classes('text-sm opacity-70')
                ui.button('UPLOAD IMAGE', on_click=lambda: None).classes('mt-2')

    dashboard_nav(active='card_editor')


# ─── Card Case (shell) ──────────────────────────────────────────────────────

@ui.page('/card/case')
async def card_case():
    if not require_auth():
        return

    user_id = app.storage.user.get('user_id')
    user = await db.get_user_by_id(user_id)
    moniker = user['moniker'] if user else app.storage.user.get('moniker', 'Unknown')
    member_type = app.storage.user.get('member_type', 'free')
    psettings = await db.get_profile_settings(user_id)

    dashboard_header(moniker, member_type, user_id=user_id,
                     override_enabled=bool(psettings['linktree_override']),
                     override_url=psettings['linktree_url'])

    with ui.column().classes('w-full items-center gap-8 mt-1 pb-24'):
        with ui.column().classes('w-[75vw] gap-4'):
            ui.label('CARD CASE').classes('text-3xl font-bold')
            ui.label('Collect virtual cards from other Heavymeta members.').classes('text-sm opacity-70')

            # Placeholder cards (Apple Wallet style stack)
            for i in range(3):
                with ui.card().classes(
                    'w-full rounded-2xl overflow-hidden shadow-lg'
                ).style('margin-top: -2rem;' if i > 0 else ''):
                    with ui.row().classes('bg-gradient-to-r from-[#f2d894] to-[#d6a5e2] p-4 items-center gap-4'):
                        ui.image('/static/placeholder.png').classes('w-12 h-12 rounded-full')
                        with ui.column().classes('gap-0'):
                            ui.label(f'Member {i + 1}').classes('text-lg font-bold text-black')
                            ui.label('heavymeta.art').classes('text-xs opacity-50 text-black')
                    with ui.row().classes('p-3 gap-2'):
                        ui.icon('link').classes('text-sm opacity-50')
                        ui.label('3 links').classes('text-xs opacity-50')

            if True:  # empty state hint
                ui.separator().classes('my-4')
                ui.label('Tap a member\'s NFC card to add it here.').classes('text-sm opacity-50 text-center w-full')

    dashboard_nav(active='card_case')


# ─── Settings (Color Customization) ────────────────────────────────────────

@ui.page('/settings')
async def settings():
    if not require_auth():
        return

    user_id = app.storage.user.get('user_id')
    user = await db.get_user_by_id(user_id)
    moniker = user['moniker'] if user else app.storage.user.get('moniker', 'Unknown')
    member_type = app.storage.user.get('member_type', 'free')
    psettings = await db.get_profile_settings(user_id)

    dashboard_header(moniker, member_type, user_id=user_id,
                     override_enabled=bool(psettings['linktree_override']),
                     override_url=psettings['linktree_url'])

    colors = await db.get_profile_colors(user_id)

    with ui.column().classes('w-full items-center gap-8 mt-1 pb-24'):
        with ui.column().classes('w-[75vw] gap-6'):
            ui.label('COLOR SETTINGS').classes('text-3xl font-bold')
            ui.label('Customize the colors on your public profile.').classes('text-sm opacity-70')

            bg_input = ui.color_input('Background', value=colors['bg_color']).classes('w-full')
            text_input = ui.color_input('Text', value=colors['text_color']).classes('w-full')
            accent_input = ui.color_input('Accent', value=colors['accent_color']).classes('w-full')
            link_input = ui.color_input('Links', value=colors['link_color']).classes('w-full')

            # Live preview card
            ui.label('PREVIEW').classes('text-lg font-bold mt-4')
            preview = ui.card().classes('w-full p-6 rounded-lg gap-3')
            with preview:
                preview_moniker = ui.label(moniker.upper()).classes('text-2xl font-bold')
                with ui.element('div').classes('px-3 py-1 rounded-lg').style(
                    'display: inline-block; width: fit-content;'
                ) as preview_badge:
                    ui.label('COOP MEMBER' if member_type == 'coop' else 'FREE MEMBER').classes('text-xs font-bold')
                preview_link1 = ui.label('example-link.com').classes('font-semibold')
                preview_link2 = ui.label('another-link.com').classes('font-semibold')

            def update_preview():
                bg = bg_input.value or '#ffffff'
                txt = text_input.value or '#000000'
                acc = accent_input.value or '#8c52ff'
                lnk = link_input.value or '#8c52ff'
                preview.style(f'background-color: {bg};')
                preview_moniker.style(f'color: {txt};')
                preview_badge.style(
                    f'background-color: {acc}40; display: inline-block; width: fit-content;'
                )
                preview_link1.style(f'color: {lnk};')
                preview_link2.style(f'color: {lnk};')

            update_preview()
            bg_input.on_value_change(lambda: update_preview())
            text_input.on_value_change(lambda: update_preview())
            accent_input.on_value_change(lambda: update_preview())
            link_input.on_value_change(lambda: update_preview())

            save_label = ui.label('').classes('text-green-600 text-sm')
            save_label.set_visibility(False)

            async def save_colors():
                await db.upsert_profile_colors(
                    user_id,
                    bg_color=bg_input.value or '#ffffff',
                    text_color=text_input.value or '#000000',
                    accent_color=accent_input.value or '#8c52ff',
                    link_color=link_input.value or '#8c52ff',
                )
                save_label.text = 'Colors saved!'
                save_label.set_visibility(True)

            ui.button('SAVE', on_click=save_colors).classes('mt-4 px-8 py-3 text-lg')

    dashboard_nav()


# ─── Public Profile (Client View) ───────────────────────────────────────────

@ui.page('/profile/{moniker_slug}')
async def public_profile(moniker_slug: str):
    style_page('Heavymeta Profile')

    # Look up user by moniker
    import aiosqlite
    from config import DATABASE_PATH, BLOCK_EXPLORER, NET
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM users WHERE LOWER(REPLACE(moniker, ' ', '-')) = ?",
            (moniker_slug.lower(),)
        )
        user = await cursor.fetchone()

    if not user:
        with ui.column().classes('w-full items-center mt-24'):
            ui.label('Profile not found.').classes('text-2xl opacity-50')
        return

    # Check for linktree override redirect
    psettings = await db.get_profile_settings(user['id'])
    if psettings['linktree_override'] and psettings['linktree_url']:
        ui.navigate.to(psettings['linktree_url'])
        return

    # Load custom colors
    colors = await db.get_profile_colors(user['id'])
    bg = colors['bg_color']
    txt = colors['text_color']
    acc = colors['accent_color']
    lnk = colors['link_color']

    # Apply background color
    ui.query('body').style(f'background-color: {bg};')

    # Client View header — blend accent into gradient end-color
    with ui.column().classes(
        'w-full items-center py-8'
    ).style(f'background: linear-gradient(to right, #f2d894, {acc}40);'):
        ui.image('/static/placeholder.png').classes('w-32 h-32 rounded-full shadow-md')
        ui.label(user['moniker']).classes('text-3xl font-bold mt-4').style(f'color: {txt};')
        if user['stellar_address']:
            addr = user['stellar_address']
            short = f"{addr[:6]}...{addr[-4:]}"
            ui.link(short, f'{BLOCK_EXPLORER}/account/{addr}', new_tab=True).classes(
                'font-semibold text-sm'
            ).style(f'color: {lnk};')

    with ui.column().classes('w-full items-center gap-8 mt-8').style(
        'padding-inline: clamp(1rem, 25vw, 50rem);'
    ):
        # Links
        links = await db.get_links(user['id'])
        if links:
            with ui.column().classes('w-full gap-2 border p-4 rounded-lg'):
                ui.label('LINKS').classes('text-lg font-bold').style(f'color: {txt};')
                for link in links:
                    with ui.row().classes('items-center border py-2 px-4 rounded-full w-full'):
                        ui.image('/static/placeholder.png').classes('rounded-full w-8 h-8')
                        ui.link(link['label'], link['url'], new_tab=True).classes(
                            'font-semibold text-lg'
                        ).style(f'color: {lnk};')

        # Wallets
        if user['stellar_address']:
            with ui.column().classes('w-full gap-2 border p-4 rounded-lg'):
                ui.label('WALLETS').classes('text-lg font-bold').style(f'color: {txt};')
                with ui.row().classes('items-center gap-2 w-full'):
                    ui.image('/static/placeholder.png').classes('rounded-full w-8 h-8')
                    ui.label(user['stellar_address']).classes('text-sm font-mono break-all flex-1')
                    ui.button(icon='content_copy', on_click=lambda: ui.run_javascript(
                        f"navigator.clipboard.writeText('{user['stellar_address']}')"
                    )).props('flat dense size=sm')

    # Bottom bar with back-to-home
    with ui.footer().classes('bg-[#8c52ff] flex justify-center items-center py-3'):
        ui.button(icon='arrow_back', on_click=lambda: ui.navigate.to('/')).props('flat round').style('color: white;')


# ─── Launch Credentials ──────────────────────────────────────────────────────

@ui.page('/launch')
async def launch():
    if not require_coop():
        return

    style_page('Launch Credentials')

    user_id = app.storage.user.get('user_id')
    user = await db.get_user_by_id(user_id)

    with ui.column(
    ).classes('w-full items-center gap-8 mt-12'
    ).style('padding-inline: clamp(1rem, 25vw, 50rem);'):
        ui.label('YOUR PINTHEON NODE CREDENTIALS').classes('text-3xl font-semibold tracking-wide')

        with ui.card().classes('w-full p-6 gap-4'):
            error_label = ui.label('').classes('text-red-500 text-sm')
            error_label.set_visibility(False)

            # Token display area (hidden until generated)
            with ui.column().classes('w-full gap-2') as token_area:
                pass
            token_area.set_visibility(False)

            async def do_generate():
                error_label.set_visibility(False)
                generate_btn.disable()
                try:
                    token = await generate_launch_credentials(user_id)
                    token_area.clear()
                    with token_area:
                        ui.label('LAUNCH TOKEN (copy this):').classes('text-sm font-bold')
                        ui.textarea(value=token).classes('w-full font-mono text-xs').props('readonly rows=6')
                        ui.button('COPY TO CLIPBOARD', on_click=lambda: ui.run_javascript(
                            f"navigator.clipboard.writeText(`{token}`)"
                        )).classes('mt-2')
                        ui.separator()
                        ui.label('Launch Key has been sent to your email.').classes('text-sm')
                        ui.label('You will need BOTH to launch your node.').classes('text-sm font-bold')
                    token_area.set_visibility(True)
                except Exception as e:
                    error_label.text = f'Failed to generate credentials: {e}'
                    error_label.set_visibility(True)
                finally:
                    generate_btn.enable()

            generate_btn = ui.button(
                'GENERATE LAUNCH CREDENTIALS',
                on_click=do_generate,
            ).classes('px-8 py-3 text-lg')

        # Node info
        if user and user['stellar_address']:
            with ui.card().classes('w-full p-6 gap-2'):
                ui.label(f"Node Address: {user['stellar_address']}").classes('text-sm font-mono break-all')
                ui.label(f'Network: {config.NET}').classes('text-sm')
                ui.label('Funded: 22 XLM').classes('text-sm')
                explorer_url = f"{config.BLOCK_EXPLORER}/account/{user['stellar_address']}"
                ui.link('View on Stellar Expert', explorer_url, new_tab=True).classes('text-sm text-primary')


ui.run(storage_secret=config.APP_SECRET_KEY)
