import config  # noqa: F401 — triggers startup validation
import db
from nicegui import ui, app
from fastapi import Request, HTTPException
import os
import httpx
from components import (
    style_page, image_with_text,
    dashboard_nav, dashboard_header,
    hide_dashboard_chrome, show_dashboard_chrome,
)
from auth import set_session, require_auth, require_coop
from enrollment import process_paid_enrollment, finalize_pending_enrollment
from payments.stripe_pay import handle_webhook, retrieve_checkout_session
from auth_dialog import open_auth_dialog
from launch import generate_launch_credentials
from stellar_ops import get_xlm_balance, send_xlm
import ipfs_client
from qr_gen import (
    regenerate_qr, generate_link_qr, regenerate_all_link_qrs, generate_user_qr,
)
from wallet_ops import create_denom_wallet_for_user, build_pay_uri
from config import DENOM_PRESETS, BANKER_25519, GUARDIAN_25519, BANKER_KP
from linktree_renderer import render_linktree
from theme import apply_theme, load_and_apply_theme, resolve_active_palette
import json
import time as _time

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
        # Idempotency: skip if user already upgraded to coop
        existing = await db.get_user_by_email(result['email'])
        if existing and existing['member_type'] == 'coop':
            return {'status': 'ok'}

        if existing:
            # Legacy: user was created as 'free' before payment
            await finalize_pending_enrollment(
                user_id=existing['id'],
                order_id=result['order_id'],
                payment_method='stripe',
                tx_hash=result['payment_intent'],
                xlm_price_usd=result.get('xlm_price_usd'),
            )
        else:
            # New flow: no user in DB yet — create from scratch
            await process_paid_enrollment(
                email=result['email'],
                moniker=result['moniker'],
                password_hash=result['password_hash'],
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
            on_click=lambda: open_auth_dialog('join'),
        ).classes('mt-8 px-8 py-3 text-lg w-1/2')


# ─── Join ─────────────────────────────────────────────────────────────────────

@ui.page('/join')
def join():
    style_page('HEAVYMETA')
    open_auth_dialog('join')


# ─── XLM Payment Page (redirects to dialog) ──────────────────────────────────

@ui.page('/join/pay/xlm')
def pay_xlm():
    style_page('HEAVYMETA')
    open_auth_dialog('join')


# ─── Success Page ─────────────────────────────────────────────────────────────

@ui.page('/join/success')
async def join_success(session_id: str = ''):
    """Stripe redirects here after checkout. Verifies payment and triggers enrollment."""
    # If already logged in as coop, go straight to dashboard
    if app.storage.user.get('authenticated') and app.storage.user.get('member_type') == 'coop':
        ui.navigate.to('/profile/edit')
        return

    # Get pending email (new flow) or user_id (legacy)
    pending = app.storage.user.get('pending_stripe', {})
    pending_email = pending.get('email')
    user_id = app.storage.user.get('user_id')

    if not pending_email and not user_id and not session_id:
        style_page('Welcome!')
        with ui.column(
        ).classes('w-full items-center gap-8 mt-12'
        ).style('padding-inline: clamp(1rem, 25vw, 50rem);'):
            ui.label('Session expired.').classes('text-2xl font-semibold')
            ui.label('Please log in to check your membership status.').classes('text-sm opacity-70')
            ui.button('LOGIN', on_click=lambda: open_auth_dialog('login')).classes('mt-4')
        return

    style_page('Welcome!')

    with ui.column(
    ).classes('w-full items-center gap-8 mt-12'
    ).style('padding-inline: clamp(1rem, 25vw, 50rem);'):
        ui.label('FINALIZING YOUR MEMBERSHIP...').classes('text-3xl font-semibold tracking-wide')
        spinner = ui.spinner('dots', size='lg')
        status_label = ui.label('Waiting for payment confirmation...').classes('text-sm opacity-70')

    _enrollment_triggered = False

    async def check_enrollment():
        nonlocal _enrollment_triggered

        # 1. Check if webhook already created the user as coop
        user = None
        if pending_email:
            user = await db.get_user_by_email(pending_email)
        elif user_id:
            user = await db.get_user_by_id(user_id)

        if user and user['member_type'] == 'coop':
            timer.deactivate()
            spinner.set_visibility(False)
            set_session(dict(user))
            if 'pending_stripe' in app.storage.user:
                del app.storage.user['pending_stripe']
            ui.navigate.to('/profile/edit')
            return

        # 2. Webhook hasn't fired yet — verify payment via Stripe API directly
        if session_id and not _enrollment_triggered:
            try:
                result = retrieve_checkout_session(session_id)
            except Exception:
                return  # Stripe API error, retry next poll

            if result is None:
                return  # Payment not yet complete, retry next poll

            _enrollment_triggered = True
            status_label.text = 'Payment confirmed — setting up your account...'

            # Idempotency: check if user was created between polls
            existing = await db.get_user_by_email(result['email'])
            if existing and existing['member_type'] == 'coop':
                timer.deactivate()
                spinner.set_visibility(False)
                set_session(dict(existing))
                if 'pending_stripe' in app.storage.user:
                    del app.storage.user['pending_stripe']
                ui.navigate.to('/profile/edit')
                return

            try:
                if existing:
                    # Legacy: upgrade existing free user
                    await finalize_pending_enrollment(
                        user_id=existing['id'],
                        order_id=result['order_id'],
                        payment_method='stripe',
                        tx_hash=result['payment_intent'],
                        xlm_price_usd=result.get('xlm_price_usd'),
                    )
                    user = await db.get_user_by_id(existing['id'])
                else:
                    # New flow: create from scratch
                    new_user_id, _ = await process_paid_enrollment(
                        email=result['email'],
                        moniker=result['moniker'],
                        password_hash=result['password_hash'],
                        order_id=result['order_id'],
                        payment_method='stripe',
                        tx_hash=result['payment_intent'],
                        xlm_price_usd=result.get('xlm_price_usd'),
                    )
                    user = await db.get_user_by_id(new_user_id)

                timer.deactivate()
                spinner.set_visibility(False)
                set_session(dict(user))
                if 'pending_stripe' in app.storage.user:
                    del app.storage.user['pending_stripe']
                ui.navigate.to('/profile/edit')
            except Exception as e:
                status_label.text = f'Account setup error: {e}'
                spinner.set_visibility(False)
                timer.deactivate()

    timer = ui.timer(3.0, check_enrollment)


# ─── Login ────────────────────────────────────────────────────────────────────

@ui.page('/login')
def login():
    style_page('HEAVYMETA')
    open_auth_dialog('login')


# ─── Dashboard (Profile) ─────────────────────────────────────────────────────

@ui.page('/profile/edit')
async def profile():
    if not require_auth():
        return

    user_id = app.storage.user.get('user_id')
    user = await db.get_user_by_id(user_id)
    if not user:
        app.storage.user.clear()
        ui.navigate.to('/login')
        return
    moniker = user['moniker']
    member_type = app.storage.user.get('member_type', 'free')
    psettings = await db.get_profile_settings(user_id)

    avatar_cid = dict(user).get('avatar_cid')
    header = dashboard_header(moniker, member_type, user_id=user_id,
                              override_enabled=bool(psettings['linktree_override']),
                              override_url=psettings['linktree_url'],
                              ipns_name=user['ipns_name'],
                              avatar_cid=avatar_cid)
    show_dashboard_chrome(header)
    await load_and_apply_theme(user_id)

    # Avatar upload bridge (hidden trigger — same pattern as card editor)
    async def process_avatar_upload():
        try:
            b64 = await ui.run_javascript(
                'return window.__avatarUploadData', timeout=5.0,
            )
        except TimeoutError:
            ui.notify('Image too large for upload. Try a smaller file.', type='warning')
            return
        except Exception as e:
            ui.notify(f'Could not read image data: {e}', type='warning')
            return
        if not b64:
            ui.notify('No image data received', type='warning')
            return
        import base64
        try:
            img_bytes = base64.b64decode(b64)
            user_row = await db.get_user_by_id(user_id)
            old_cid = user_row['avatar_cid'] if user_row else None
            new_cid = await ipfs_client.replace_asset(img_bytes, old_cid, 'avatar.png')
            await db.update_user(user_id, avatar_cid=new_cid)
            await regenerate_qr(user_id)
            await regenerate_all_link_qrs(user_id)
            ipfs_client.schedule_republish(user_id)
            ui.notify('Avatar updated', type='positive')
        except Exception as e:
            import traceback
            traceback.print_exc()
            ui.notify(f'Avatar upload failed: {e}', type='negative')

    ui.button(on_click=process_avatar_upload).props(
        'id=avatar-upload-trigger').style('position:absolute;left:-9999px;')

    with ui.column().classes('w-full items-center gap-4 pb-24'):
        # Upgrade CTA for free users
        if member_type == 'free':
            with ui.card().classes('w-[75vw] bg-gradient-to-r from-purple-100 to-yellow-100'):
                ui.label('Join the Coop').classes('text-xl font-bold')
                ui.label('Get full access, NFC card, and Pintheon node credentials.').classes('text-sm opacity-70')
                ui.button('UPGRADE', on_click=lambda: open_auth_dialog('join')).classes('mt-2')

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
                            qr_cid = dict(link).get('qr_cid')
                            qr_thumb = (f'{config.KUBO_GATEWAY}/ipfs/{qr_cid}'
                                        if qr_cid else
                                        link['icon_url'] or '/static/placeholder.png')
                            ui.image(qr_thumb).classes('rounded w-8 h-8')
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
                            url_val = add_url.value.strip()
                            link_id = await db.create_link(
                                user_id=user_id,
                                label=add_label.value.strip(),
                                url=url_val,
                            )
                            await generate_link_qr(user_id, link_id, url_val)
                            ipfs_client.schedule_republish(user_id)
                            add_label.value = ''
                            add_url.value = ''
                            links_section.refresh()

                    ui.button(icon='add', on_click=add_link).props(
                        'round outline dense size=sm'
                    ).style('color: var(--hm-text);')
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
                                new_url = edit_url.value.strip()
                                # Regenerate QR if URL changed
                                if new_url != current_url:
                                    old_link = await db.get_link_by_id(link_id)
                                    if old_link and dict(old_link).get('qr_cid'):
                                        await ipfs_client.ipfs_unpin(dict(old_link)['qr_cid'])
                                    await generate_link_qr(user_id, link_id, new_url)
                                await db.update_link(
                                    link_id,
                                    label=edit_label.value.strip(),
                                    url=new_url,
                                )
                                ipfs_client.schedule_republish(user_id)
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
                            # Unpin QR before deleting
                            old_link = await db.get_link_by_id(link_id)
                            if old_link and dict(old_link).get('qr_cid'):
                                await ipfs_client.ipfs_unpin(dict(old_link)['qr_cid'])
                            await db.delete_link(link_id)
                            ipfs_client.schedule_republish(user_id)
                            dialog.close()
                            links_section.refresh()

                        ui.button('Delete', on_click=do_delete).props('color=red')
                dialog.open()

        # Wallets section (coop only)
        if member_type == 'coop':
            with ui.column().classes('w-[75vw] gap-2 border p-4 rounded-lg'):
                ui.label('WALLETS').classes('text-2xl font-bold')

                @ui.refreshable
                async def wallets_section():
                    wallets = await db.get_denom_wallets(user_id)
                    for w in wallets:
                        w = dict(w)
                        wallet_id = w['id']
                        denom = w['denomination']
                        addr = w['stellar_address']
                        qr_cid = w.get('qr_cid')
                        pay_uri = build_pay_uri(addr, denom)
                        qr_url = (f'{config.KUBO_GATEWAY}/ipfs/{qr_cid}'
                                  if qr_cid else '/static/placeholder.png')

                        with ui.row().classes(
                            'items-center py-2 px-4 rounded-full w-full gap-3'
                        ):
                            qr_img = ui.image(qr_url).classes('rounded w-8 h-8 cursor-pointer')
                            if qr_cid:
                                qr_img.on('click', lambda u=qr_url: _open_qr_dialog(u))
                            ui.label(f'{denom} XLM').classes('font-bold text-sm').style(
                                'min-width: 60px;'
                            )
                            short_addr = f'{addr[:6]}...{addr[-4:]}'
                            ui.label(short_addr).classes('text-sm font-mono opacity-70 flex-1')
                            ui.button(
                                icon='content_copy',
                                on_click=lambda u=pay_uri: ui.run_javascript(
                                    f"navigator.clipboard.writeText('{u}')"
                                ),
                            ).props('flat dense size=sm')
                            ui.button(
                                icon='delete',
                                on_click=lambda wid=wallet_id: confirm_delete_wallet(wid),
                            ).props('flat dense size=sm color=red')

                    # Add wallet row: + button + denom chip selector
                    with ui.row().classes('items-center w-full gap-2'):
                        denom_select = ui.toggle(
                            {d: str(d) for d in DENOM_PRESETS}, value=DENOM_PRESETS[0]
                        ).props('dense no-caps size=sm')

                        async def add_wallet():
                            denom = denom_select.value
                            await create_denom_wallet_for_user(user_id, denom)
                            ipfs_client.schedule_republish(user_id)
                            wallets_section.refresh()

                        ui.button(icon='add', on_click=add_wallet).props(
                            'round outline dense size=sm'
                        ).style('color: var(--hm-text);')

                await wallets_section()

                # QR dialog helper
                def _open_qr_dialog(qr_url):
                    with ui.dialog() as dlg, ui.card().classes(
                        'items-center p-6'
                    ).style('background-color: #1a1a2e; border-radius: 16px;'):
                        ui.image(qr_url).classes('w-64 h-64 rounded-lg')
                    dlg.open()

                # Delete confirmation
                async def confirm_delete_wallet(wallet_id):
                    with ui.dialog() as dialog, ui.card().classes('p-4 gap-4'):
                        ui.label('Delete this wallet?').classes('text-lg')
                        with ui.row().classes('justify-end gap-2'):
                            ui.button('Cancel', on_click=dialog.close).props('flat')

                            async def do_delete():
                                w = await db.get_denom_wallet_by_id(wallet_id)
                                if w and dict(w).get('qr_cid'):
                                    await ipfs_client.ipfs_unpin(dict(w)['qr_cid'])
                                await db.discard_denom_wallet(wallet_id)
                                ipfs_client.schedule_republish(user_id)
                                dialog.close()
                                wallets_section.refresh()

                            ui.button('Delete', on_click=do_delete).props('color=red')
                    dialog.open()

    dashboard_nav(active='dashboard')


# ─── Card Editor (Three.js) ─────────────────────────────────────────────────

@ui.page('/card/editor')
async def card_editor():
    if not require_auth():
        return

    user_id = app.storage.user.get('user_id')
    user = await db.get_user_by_id(user_id)
    moniker = user['moniker'] if user else app.storage.user.get('moniker', 'Unknown')
    member_type = app.storage.user.get('member_type', 'free')
    psettings = await db.get_profile_settings(user_id)

    existing_front_cid = user['nfc_image_cid'] if user else None
    existing_back_cid = user['nfc_back_image_cid'] if user else None
    initial_front_url = f'{config.KUBO_GATEWAY}/ipfs/{existing_front_cid}' if existing_front_cid else ''
    initial_back_url = f'{config.KUBO_GATEWAY}/ipfs/{existing_back_cid}' if existing_back_cid else ''

    # Header hidden, footer visible
    header = dashboard_header(moniker, member_type, user_id=user_id,
                              override_enabled=bool(psettings['linktree_override']),
                              override_url=psettings['linktree_url'],
                              ipns_name=user['ipns_name'])
    hide_dashboard_chrome(header)

    # Full-viewport CSS for 3D card scene
    ui.add_head_html('''
    <style>
      .q-page, body { background-color: transparent !important; }
      .q-layout { pointer-events: none; }
      .q-footer { pointer-events: auto; }
      #card-scene { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 500; }
    </style>
    ''')

    # File upload bridge (Python side)
    async def process_upload():
        try:
            result = await ui.run_javascript(
                'return {data: window.__cardUploadData, face: window.__cardUploadFace}',
                timeout=5.0,
            )
        except TimeoutError:
            ui.notify('Image too large for upload. Try a smaller file.', type='warning')
            return
        except Exception as e:
            ui.notify(f'Could not read image data: {e}', type='warning')
            return

        b64_data = result.get('data') if result else None
        face = result.get('face', 'front') if result else 'front'
        if not b64_data:
            ui.notify('No image data received', type='warning')
            return

        cid_column = 'nfc_image_cid' if face == 'front' else 'nfc_back_image_cid'
        filename = 'nfc_card_front.png' if face == 'front' else 'nfc_card_back.png'

        try:
            import base64
            content = base64.b64decode(b64_data)
            user_row = await db.get_user_by_id(user_id)
            old_cid = user_row[cid_column]
            new_cid = await ipfs_client.replace_asset(content, old_cid, filename)
            await db.update_user(user_id, **{cid_column: new_cid})
            ipfs_client.schedule_republish(user_id)
            texture_url = f'{config.KUBO_GATEWAY}/ipfs/{new_cid}'
            await ui.run_javascript(f"window.updateCardTexture('{face}', '{texture_url}')")
            ui.notify(f'Card {face} image saved', type='positive')
        except httpx.ConnectError:
            ui.notify('IPFS daemon not running — preview applied but not saved',
                      type='warning')
        except Exception as e:
            ui.notify(f'Upload failed: {e}', type='negative')

    # Off-screen (not display:none) so programmatic .click() triggers Vue events
    upload_trigger = ui.button(on_click=process_upload).props(
        'id=card-upload-trigger').style('position:absolute;left:-9999px;')

    # Three.js scene container + JS module (cache-bust with timestamp)
    _cache_v = int(_time.time())
    ui.add_body_html(f'''
    <div id="card-scene"
         data-front-texture="{initial_front_url}"
         data-back-texture="{initial_back_url}"></div>
    <script type="module" src="/static/js/card_scene.js?v={_cache_v}"></script>
    ''')

    dashboard_nav(active='card_editor')


# ─── Card Wallet (3D) ────────────────────────────────────────────────────────

@ui.page('/card/case')
async def card_case():
    if not require_auth():
        return

    user_id = app.storage.user.get('user_id')
    user = await db.get_user_by_id(user_id)
    moniker = user['moniker'] if user else app.storage.user.get('moniker', 'Unknown')
    member_type = app.storage.user.get('member_type', 'free')
    psettings = await db.get_profile_settings(user_id)

    # Load peer cards from DB
    peers = await db.get_peer_cards(user_id)
    peer_data = []
    for p in peers:
        pd = dict(p)
        moniker_slug = pd['moniker'].lower().replace(' ', '-')
        peer_data.append({
            'moniker': pd['moniker'],
            'front_url': (f'{config.KUBO_GATEWAY}/ipfs/{pd["nfc_image_cid"]}'
                          if pd.get('nfc_image_cid') else ''),
            'back_url': (f'{config.KUBO_GATEWAY}/ipfs/{pd["nfc_back_image_cid"]}'
                         if pd.get('nfc_back_image_cid') else ''),
            'linktree_url': f'/profile/{moniker_slug}',
        })

    header = dashboard_header(moniker, member_type, user_id=user_id,
                              override_enabled=bool(psettings['linktree_override']),
                              override_url=psettings['linktree_url'],
                              ipns_name=user['ipns_name'])
    hide_dashboard_chrome(header)

    # Full-viewport CSS for 3D card scene
    ui.add_head_html('''
    <style>
      .q-page, body { background-color: transparent !important; }
      .q-layout { pointer-events: none; }
      .q-footer { pointer-events: auto; }
      #card-scene { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 500; }
    </style>
    ''')

    # Peer scan bridge (hidden trigger — scans QR codes to add peers)
    async def process_scanned_peer():
        try:
            slug = await ui.run_javascript('return window.__scannedPeerSlug', timeout=5.0)
        except Exception:
            ui.notify('Could not read scan data', type='warning')
            return
        if not slug:
            ui.notify('No scan data received', type='warning')
            return

        peer = await db.get_user_by_moniker_slug(slug)
        if not peer:
            ui.notify('Member not found', type='warning')
            await ui.run_javascript('window.__peerScanResult = "not_found"')
            return
        if peer['id'] == user_id:
            ui.notify("That's your own QR code!", type='info')
            await ui.run_javascript('window.__peerScanResult = "self"')
            return

        await db.add_peer_card(user_id, peer['id'])
        peer_moniker = peer['moniker']
        peer_moniker_slug = peer_moniker.lower().replace(' ', '-')
        new_peer_data = {
            'moniker': peer_moniker,
            'front_url': (f'{config.KUBO_GATEWAY}/ipfs/{peer["nfc_image_cid"]}'
                          if peer.get('nfc_image_cid') else ''),
            'back_url': (f'{config.KUBO_GATEWAY}/ipfs/{peer["nfc_back_image_cid"]}'
                          if peer.get('nfc_back_image_cid') else ''),
            'linktree_url': f'/profile/{peer_moniker_slug}',
        }
        ui.notify(f'Added {peer_moniker} to your card wallet!', type='positive')
        await ui.run_javascript(
            f'window.__peerScanResult = "ok";'
            f'window.__peerScanMoniker = {json.dumps(peer_moniker)};'
            f'window.__newPeerData = {json.dumps(new_peer_data)};'
        )

    ui.button(on_click=process_scanned_peer).props(
        'id=peer-scan-trigger').style('position:absolute;left:-9999px;')

    # Manual add bridge (hidden trigger — opens dialog for moniker input)
    async def open_manual_add_dialog():
        with ui.dialog() as dlg, ui.card().classes('p-6 gap-4'):
            ui.label('Add a peer').classes('text-lg font-semibold')
            slug_input = ui.input(placeholder='Enter moniker (e.g. jane-doe)').props(
                'outlined dense'
            ).classes('w-full')

            async def do_add():
                slug = slug_input.value.strip().lower().replace(' ', '-')
                if not slug:
                    ui.notify('Enter a moniker', type='warning')
                    return
                peer = await db.get_user_by_moniker_slug(slug)
                if not peer:
                    ui.notify('Member not found', type='warning')
                    return
                if peer['id'] == user_id:
                    ui.notify("That's you!", type='info')
                    return
                await db.add_peer_card(user_id, peer['id'])
                peer_moniker = peer['moniker']
                peer_moniker_slug = peer_moniker.lower().replace(' ', '-')
                new_peer_data = {
                    'moniker': peer_moniker,
                    'front_url': (f'{config.KUBO_GATEWAY}/ipfs/{peer["nfc_image_cid"]}'
                                  if peer.get('nfc_image_cid') else ''),
                    'back_url': (f'{config.KUBO_GATEWAY}/ipfs/{peer["nfc_back_image_cid"]}'
                                  if peer.get('nfc_back_image_cid') else ''),
                    'linktree_url': f'/profile/{peer_moniker_slug}',
                }
                ui.notify(f'Added {peer_moniker} to your wallet!', type='positive')
                await ui.run_javascript(
                    f'window.__newPeerData = {json.dumps(new_peer_data)};'
                    f'window.addPeerCard && window.addPeerCard();'
                )
                dlg.close()

            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('Cancel', on_click=dlg.close).props('flat')
                ui.button('Add', on_click=do_add)
        dlg.open()

    ui.button(on_click=open_manual_add_dialog).props(
        'id=manual-add-trigger').style('position:absolute;left:-9999px;')

    # Pass peer data as JSON + load wallet scene
    _cache_v = int(_time.time())
    peers_json = json.dumps(peer_data)
    ui.add_body_html(f'''
    <div id="card-scene"></div>
    <script id="peer-data" type="application/json">{peers_json}</script>
    <script type="module" src="/static/js/card_wallet.js?v={_cache_v}"></script>
    ''')

    dashboard_nav(active='card_case')


# ─── QR Code View (3D) ──────────────────────────────────────────────────────

@ui.page('/qr')
async def qr_view():
    if not require_auth():
        return

    user_id = app.storage.user.get('user_id')
    user = await db.get_user_by_id(user_id)
    moniker = user['moniker'] if user else app.storage.user.get('moniker', 'Unknown')
    member_type = app.storage.user.get('member_type', 'free')
    psettings = await db.get_profile_settings(user_id)

    header = dashboard_header(moniker, member_type, user_id=user_id,
                              override_enabled=bool(psettings['linktree_override']),
                              override_url=psettings['linktree_url'],
                              ipns_name=user['ipns_name'])
    hide_dashboard_chrome(header)

    # Get or generate QR code
    qr_cid = dict(user).get('qr_code_cid') if user else None
    if not qr_cid:
        try:
            await regenerate_qr(user_id)
            user = await db.get_user_by_id(user_id)
            qr_cid = dict(user).get('qr_code_cid')
        except Exception:
            pass

    qr_url = f'{config.KUBO_GATEWAY}/ipfs/{qr_cid}' if qr_cid else ''

    # Full-viewport CSS for 3D QR display
    ui.add_head_html('''
    <style>
      .q-page, body { background-color: transparent !important; }
      .q-layout { pointer-events: none; }
      .q-footer { pointer-events: auto; }
      #qr-scene {
        position: fixed;
        top: 0; left: 0;
        width: 100vw; height: 100vh;
        z-index: 500;
        pointer-events: auto;
      }
    </style>
    ''')

    _cache_v = int(_time.time())
    ui.add_body_html(
        f'<div id="qr-scene" data-qr-url="{qr_url}"></div>'
        f'<script type="module" src="/static/js/qr_view.js?v={_cache_v}"></script>'
    )

    dashboard_nav(active='qr_code')


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

    header = dashboard_header(moniker, member_type, user_id=user_id,
                              override_enabled=bool(psettings['linktree_override']),
                              override_url=psettings['linktree_url'],
                              ipns_name=user['ipns_name'])
    hide_dashboard_chrome(header)

    colors = await db.get_profile_colors(user_id)

    # Mutable state dict for all 12 colors + dark_mode
    state = dict(colors)
    state['dark_mode'] = bool(psettings.get('dark_mode', 0))

    # Swatch labels and DB keys for each palette
    _SWATCH_DEFS = [
        ('Primary', 'accent_color'),
        ('Secondary', 'link_color'),
        ('Text', 'text_color'),
        ('Background', 'bg_color'),
        ('Card', 'card_color'),
        ('Border', 'border_color'),
    ]

    with ui.column().classes('w-full items-center gap-4 pt-2 pb-24'):
        ui.button(icon='chevron_left', on_click=lambda: ui.navigate.back()).props(
            'flat round'
        ).classes('self-start ml-4 opacity-70')
        with ui.column().classes('w-[75vw] gap-6'):
            ui.label('SETTINGS').classes('text-3xl font-bold')
            # ── THEME expansion ──
            with ui.expansion('THEME', icon='palette').classes('w-full'):

                # ── Live preview (above palettes) ──
                ui.label('PREVIEW').classes('text-lg font-bold mt-2')
                preview = ui.card().classes('w-full p-6 rounded-lg gap-3 preview-card')
                with preview:
                    preview_moniker = ui.label(moniker.upper()).classes('text-2xl font-bold')
                    with ui.element('div').classes('px-3 py-1 rounded-lg').style(
                        'display: inline-block; width: fit-content;'
                    ) as preview_badge:
                        preview_badge_label = ui.label(
                            'COOP MEMBER' if member_type == 'coop' else 'FREE MEMBER'
                        ).classes('text-xs font-bold')
                    preview_link1 = ui.label('example-link.com').classes('font-semibold')
                    preview_link2 = ui.label('another-link.com').classes('font-semibold')

                # ── Helper: build a palette column with 6 swatches ──
                def build_palette(label, prefix, container):
                    """Build 6 color swatch buttons inside container.
                    prefix='' for light, prefix='dark_' for dark."""
                    with container:
                        ui.label(label).classes('text-md font-medium opacity-70')
                        with ui.row().classes('flex-wrap gap-3'):
                            for swatch_label, base_key in _SWATCH_DEFS:
                                key = f'{prefix}{base_key}' if prefix else base_key
                                color_val = state.get(key, '#888888')
                                with ui.column().classes('items-center gap-1'):
                                    btn = ui.button().props('flat unelevated').classes(
                                        'w-10 h-10 min-w-0 p-0 rounded-lg'
                                    ).style(
                                        f'background-color: {color_val} !important;'
                                        'border: 1px solid rgba(128,128,128,0.3);'
                                    )

                                    def make_handler(k, b):
                                        def on_pick(e):
                                            b.style(
                                                f'background-color: {e.color} !important;'
                                                'border: 1px solid rgba(128,128,128,0.3);'
                                            )
                                            state[k] = e.color
                                            apply_live_theme()
                                        return on_pick

                                    with btn:
                                        ui.color_picker(
                                            on_pick=make_handler(key, btn)
                                        ).props('no-header no-footer')

                                    ui.label(swatch_label).classes(
                                        'text-[10px] opacity-50'
                                    )

                # ── Toggle + both palettes in one row ──
                with ui.row().classes('w-full items-start gap-4'):
                    with ui.column().classes('items-center gap-1 pt-4'):
                        ui.label('LIGHT').classes('text-xs font-bold opacity-70')
                        mode_toggle = ui.switch('', value=state['dark_mode']).props('dense')
                        ui.label('DARK').classes('text-xs font-bold opacity-70')
                    light_col = ui.column().classes('flex-1 gap-2 preview-card p-3 rounded-lg')
                    dark_col = ui.column().classes('flex-1 gap-2 preview-card p-3 rounded-lg')

                build_palette('light', '', light_col)
                build_palette('dark', 'dark_', dark_col)

                def apply_live_theme():
                    """Update preview card + entire app UI."""
                    p = 'dark_' if mode_toggle.value else ''
                    bg = state.get(f'{p}bg_color', '#ffffff')
                    txt = state.get(f'{p}text_color', '#000000')
                    acc = state.get(f'{p}accent_color', '#8c52ff')
                    lnk = state.get(f'{p}link_color', '#f2d894')
                    card_c = state.get(f'{p}card_color', '#f5f5f5')
                    border_c = state.get(f'{p}border_color', '#e0e0e0')
                    # Update preview card
                    preview.style(f'background-color: {bg};')
                    preview_moniker.style(f'color: {txt};')
                    preview_badge.style(
                        f'background-color: {acc}40; display: inline-block; width: fit-content;'
                    )
                    preview_badge_label.style(f'color: {txt};')
                    preview_link1.style(f'color: {lnk};')
                    preview_link2.style(f'color: {lnk};')
                    # Update entire app UI
                    apply_theme(
                        primary=acc, secondary=lnk, text=txt,
                        bg=bg, card=card_c, border=border_c,
                    )

                apply_live_theme()
                mode_toggle.on_value_change(lambda: apply_live_theme())

                # ── Save ──
                save_label = ui.label('').classes('text-sm')
                save_label.set_visibility(False)

                async def save_settings():
                    color_kwargs = {k: state[k] for k in db._COLOR_COLS}
                    await db.upsert_profile_colors(user_id, **color_kwargs)
                    await db.upsert_profile_settings(
                        user_id,
                        linktree_override=psettings['linktree_override'],
                        linktree_url=psettings['linktree_url'],
                        dark_mode=int(mode_toggle.value),
                    )
                    await regenerate_qr(user_id)
                    await regenerate_all_link_qrs(user_id)
                    ipfs_client.schedule_republish(user_id)
                    save_label.text = 'Settings saved!'
                    save_label.set_visibility(True)

                ui.button('SAVE', on_click=save_settings).classes(
                    'mt-4 px-8 py-3 text-lg'
                )

            # ── WALLET expansion (coop only) ──
            if member_type == 'coop':
                with ui.expansion('WALLET', icon='account_balance_wallet').classes(
                    'w-full'
                ):
                    stellar_addr = user['stellar_address'] if user else ''

                    # ── Balance display ──
                    bal_raw = get_xlm_balance(stellar_addr)
                    bal_text = f'{float(bal_raw):.2f} XLM' if bal_raw else 'Not funded'
                    balance_label = ui.label(bal_text).classes(
                        'text-2xl font-bold'
                    )

                    # Truncated address + copy
                    with ui.row().classes('items-center gap-2'):
                        addr_short = (
                            f'{stellar_addr[:6]}...{stellar_addr[-6:]}'
                            if len(stellar_addr) > 12 else stellar_addr
                        )
                        ui.label(addr_short).classes('text-sm opacity-60 font-mono')
                        ui.button(
                            icon='content_copy',
                            on_click=lambda: ui.run_javascript(
                                f'navigator.clipboard.writeText("{stellar_addr}")'
                            ),
                        ).props('flat dense size=sm')

                    def refresh_balance():
                        b = get_xlm_balance(stellar_addr)
                        balance_label.text = (
                            f'{float(b):.2f} XLM' if b else 'Not funded'
                        )

                    with ui.row().classes('gap-3 mt-2'):
                        ui.button('REFRESH', icon='refresh',
                                  on_click=refresh_balance).props('flat dense')

                        # ── Receive dialog ──
                        def open_receive():
                            import base64
                            pay_uri = (
                                f'web+stellar:pay?destination={stellar_addr}'
                            )
                            png_bytes = generate_user_qr(
                                pay_uri,
                                os.path.join(static_files_dir, 'stellar_logo.png'),
                                colors.get('accent_color', '#8c52ff'),
                                colors.get('bg_color', '#ffffff'),
                            )
                            b64 = base64.b64encode(png_bytes).decode()
                            data_uri = f'data:image/png;base64,{b64}'
                            with ui.dialog() as dlg, ui.card().classes(
                                'items-center gap-3 p-6'
                            ):
                                ui.label('RECEIVE XLM').classes(
                                    'text-lg font-bold'
                                )
                                ui.image(data_uri).classes('w-64 h-64')
                                with ui.row().classes('items-center gap-2'):
                                    ui.label(stellar_addr).classes(
                                        'text-xs font-mono break-all'
                                    )
                                    ui.button(
                                        icon='content_copy',
                                        on_click=lambda: ui.run_javascript(
                                            f'navigator.clipboard.writeText("{stellar_addr}")'
                                        ),
                                    ).props('flat dense size=sm')
                                ui.button('CLOSE', on_click=dlg.close).props(
                                    'flat'
                                )
                            dlg.open()

                        ui.button('RECEIVE', icon='qr_code',
                                  on_click=open_receive).props('flat dense')

                        # ── Send dialog ──
                        def open_send():
                            with ui.dialog() as dlg, ui.card().classes(
                                'gap-4 p-6 min-w-[320px]'
                            ):
                                ui.label('SEND XLM').classes(
                                    'text-lg font-bold'
                                )
                                dest_input = ui.input(
                                    'Destination address',
                                    validation={
                                        'Must start with G':
                                            lambda v: v.startswith('G'),
                                        'Must be 56 characters':
                                            lambda v: len(v) == 56,
                                    },
                                ).classes('w-full')
                                amt_input = ui.number(
                                    'Amount (XLM)', min=0.0000001,
                                    format='%.7f',
                                ).classes('w-full')
                                memo_input = ui.input(
                                    'Memo (optional)',
                                    validation={
                                        'Max 28 characters':
                                            lambda v: len(v) <= 28,
                                    },
                                ).classes('w-full')
                                send_error = ui.label('').classes(
                                    'text-sm text-red-500'
                                )
                                send_error.set_visibility(False)

                                async def do_send():
                                    d = dest_input.value or ''
                                    a = amt_input.value
                                    m = memo_input.value or ''
                                    # Validate
                                    if not d.startswith('G') or len(d) != 56:
                                        send_error.text = 'Invalid destination address.'
                                        send_error.set_visibility(True)
                                        return
                                    if not a or float(a) <= 0:
                                        send_error.text = 'Amount must be greater than 0.'
                                        send_error.set_visibility(True)
                                        return
                                    cur_bal = get_xlm_balance(stellar_addr)
                                    if cur_bal and float(a) > float(cur_bal):
                                        send_error.text = 'Amount exceeds balance.'
                                        send_error.set_visibility(True)
                                        return
                                    try:
                                        from hvym_stellar import StellarSharedDecryption
                                        from stellar_sdk import Keypair
                                        decryptor = StellarSharedDecryption(
                                            GUARDIAN_25519,
                                            BANKER_25519.public_key(),
                                        )
                                        enc = user['encrypted_token']
                                        if isinstance(enc, str):
                                            enc = enc.encode()
                                        secret = decryptor.decrypt(
                                            enc,
                                            from_address=BANKER_KP.public_key,
                                        )
                                        if isinstance(secret, bytes):
                                            secret = secret.decode()
                                        user_kp = Keypair.from_secret(secret)
                                        resp = send_xlm(
                                            user_kp, d, str(a),
                                            memo=m if m else None,
                                        )
                                        tx_hash = resp.get('hash', 'unknown')
                                        dlg.close()
                                        ui.notify(
                                            f'Sent! TX: {tx_hash[:12]}...',
                                            type='positive',
                                        )
                                        refresh_balance()
                                    except Exception as exc:
                                        send_error.text = f'Error: {exc}'
                                        send_error.set_visibility(True)

                                with ui.row().classes('gap-3 mt-2'):
                                    ui.button('SEND', on_click=do_send).props(
                                        'color=primary'
                                    )
                                    ui.button(
                                        'CANCEL', on_click=dlg.close
                                    ).props('flat')
                            dlg.open()

                        ui.button('SEND', icon='send',
                                  on_click=open_send).props('flat dense')

    dashboard_nav()


# ─── Public Linktree (IPFS/IPNS) ────────────────────────────────────────────

@ui.page('/lt/{ipns_name}')
async def linktree_page(ipns_name: str):
    """Public linktree rendered from IPFS/IPNS JSON."""
    user = await db.get_user_by_ipns_name(ipns_name)
    if not user:
        ui.page_title('Heavymeta Profile')
        with ui.column().classes('w-full items-center mt-24'):
            ui.label('Profile not found.').classes('text-2xl opacity-50')
        return

    is_owner = app.storage.user.get('user_id') == user['id']
    if is_owner:
        linktree = await ipfs_client.build_linktree_fresh(user['id'])
    else:
        linktree = await ipfs_client.fetch_linktree_json(user)

    if linktree.get('override_url'):
        ui.navigate.to(linktree['override_url'])
        return

    render_linktree(linktree, ipns_name, is_preview=is_owner)


# ─── Legacy Profile Redirect ────────────────────────────────────────────────

@ui.page('/profile/{moniker_slug}')
async def public_profile(moniker_slug: str):
    """Public profile route. Redirects to /lt/{ipns_name} when available,
    or renders directly from DB for the owner when IPNS isn't set up."""
    import aiosqlite
    from config import DATABASE_PATH

    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT id, ipns_name FROM users WHERE LOWER(REPLACE(moniker, ' ', '-')) = ?",
            (moniker_slug.lower(),)
        )
        user = await cursor.fetchone()

    if not user:
        ui.page_title('Heavymeta Profile')
        with ui.column().classes('w-full items-center mt-24'):
            ui.label('Profile not found.').classes('text-2xl opacity-50')
        return

    # If IPNS is available, redirect to the /lt/ route
    if user['ipns_name']:
        ui.navigate.to(f'/lt/{user["ipns_name"]}')
        return

    # Owner without IPNS — render directly from DB
    is_owner = app.storage.user.get('user_id') == user['id']
    if is_owner:
        linktree = await ipfs_client.build_linktree_fresh(user['id'])
        render_linktree(linktree, '', is_preview=True)
        return

    # External visitor, no IPNS — can't render
    ui.page_title('Heavymeta Profile')
    with ui.column().classes('w-full items-center mt-24'):
        ui.label('Profile not yet published.').classes('text-2xl opacity-50')


# ─── Launch Credentials ──────────────────────────────────────────────────────

@ui.page('/launch')
async def launch():
    if not require_coop():
        return

    ui.page_title('Launch Credentials')

    user_id = app.storage.user.get('user_id')
    user = await db.get_user_by_id(user_id)
    await load_and_apply_theme(user_id)

    with ui.column(
    ).classes('w-full items-center gap-8 mt-12'
    ).style('padding-inline: clamp(1rem, 25vw, 50rem);'):
        ui.button(icon='chevron_left', on_click=lambda: ui.navigate.back()).props(
            'flat round'
        ).classes('self-start text-black opacity-70')
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
