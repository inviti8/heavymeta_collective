import time as _time

from nicegui import ui
from config import KUBO_GATEWAY
from theme import outline_glow_css, _hex_rgb


def open_qr_dialog(qr_url: str):
    """Open a dialog showing the QR code image."""
    with ui.dialog() as dialog, ui.card().classes(
        'items-center p-6'
    ).style('background-color: #0d0d0d; border-radius: 16px;'):
        ui.image(qr_url).classes('w-64 h-64 rounded-lg')

    dialog.open()


def render_linktree(linktree: dict, ipns_name: str, is_preview: bool = False):
    ui.page_title('Heavymeta Profile')

    moniker = linktree.get('moniker', 'Unknown')
    dark_mode = linktree.get('dark_mode', False)
    palette_key = 'dark' if dark_mode else 'light'
    colors = linktree.get('colors', {}).get(palette_key, {})
    bg = colors.get('bg', '#efeff4')
    txt = colors.get('text', '#1f1f21')
    acc = colors.get('primary', '#7a48a9')
    lnk = colors.get('secondary', '#9f7ac1')
    card_bg = colors.get('card', '#ffffff')
    bdr = colors.get('border', '#cccccc')
    avatar_cid = linktree.get('avatar_cid')
    links = linktree.get('links', [])
    wallets = linktree.get('wallets', [])

    avatar_url = (f'{KUBO_GATEWAY}/ipfs/{avatar_cid}'
                  if avatar_cid else '/static/placeholder.png')

    ui.query('body').style(f'background-color: {bg};')

    # Derive glow RGB from user's accent color
    ar, ag, ab = _hex_rgb(acc)

    # Dark base + fade-in + 3D avatar scene CSS + icon color override
    ui.add_head_html(f'''
    <style>
      html, body {{ background-color: #0d0d0d !important; }}
      @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
      .nicegui-content {{ animation: fadeIn 0.25s ease-out; }}
      .q-card {{
        border: 1px solid rgba({ar},{ag},{ab},0.55);
        box-shadow: 0 0 2px rgba({ar},{ag},{ab},0.1),
                    0 0 4px rgba({ar},{ag},{ab},0.25),
                    0 0 6px rgba({ar},{ag},{ab},0.4);
      }}
      #avatar-scene {{
        position: fixed;
        z-index: 99999;
        pointer-events: auto;
      }}
      .q-footer .q-icon,
      .q-btn .q-icon {{
        color: {txt} !important;
      }}
    </style>
    ''')

    if is_preview:
        ui.button(icon='chevron_left', on_click=lambda: ui.navigate.to('/profile/edit')).props(
            'flat round'
        ).classes('fixed top-2 left-2 opacity-70').style(
            f'color: {txt}; z-index: 100000;'
        )

    with ui.column().classes(
        'w-full items-center py-8'
    ).style(f'background: linear-gradient(to right, {acc}, {lnk});'):
        # Layout spacer — the 3D scene overlays this via fixed positioning
        ui.element('div').classes('avatar-placeholder').style(
            'width: 8rem; height: 8rem;'
        )
        _av = int(_time.time())
        ui.add_body_html(
            f'<div id="avatar-scene" data-avatar-url="{avatar_url}"></div>'
            f'<script type="module" src="/static/js/avatar_view.js?v={_av}"></script>'
        )
        ui.label(moniker).classes('text-3xl font-bold mt-4').style(f'color: {txt};')


    with ui.column().classes('w-full items-center gap-8 mt-8').style(
        'padding-inline: clamp(1rem, 25vw, 50rem);'
    ):
        if links:
            with ui.column().classes('w-full gap-2 p-4 rounded-lg').style(
                outline_glow_css(acc)
            ):
                ui.label('LINKS').classes('text-lg font-bold').style(f'color: {txt};')
                for link in sorted(links, key=lambda l: l.get('sort_order', 0)):
                    qr_cid = link.get('qr_cid')
                    qr_url = (f'{KUBO_GATEWAY}/ipfs/{qr_cid}'
                              if qr_cid else '/static/placeholder.png')
                    with ui.row().classes(
                        'items-center py-2 px-4 rounded-full w-full'
                    ).style(f'border: 1px solid {bdr};'):
                        qr_img = ui.image(qr_url).classes(
                            'rounded w-8 h-8 cursor-pointer'
                        )
                        if qr_cid:
                            qr_img.on('click', lambda u=qr_url: open_qr_dialog(u))
                        ui.link(
                            link['label'], link['url'], new_tab=True
                        ).classes('font-semibold text-lg').style(f'color: {lnk};')

        denom_wallets = [w for w in wallets if w.get('type') == 'denomination']

        if denom_wallets:
            with ui.column().classes('w-full gap-2 p-4 rounded-lg').style(
                outline_glow_css(acc)
            ):
                ui.label('WALLETS').classes('text-lg font-bold').style(f'color: {txt};')
                for dw in denom_wallets:
                    qr_cid = dw.get('qr_cid')
                    qr_url = (f'{KUBO_GATEWAY}/ipfs/{qr_cid}'
                              if qr_cid else '/static/placeholder.png')
                    addr = dw['address']
                    denom = dw['denomination']
                    pay_uri = f"web+stellar:pay?destination={addr}&amount={denom}&asset_code=XLM"
                    short_addr = f'{addr[:6]}...{addr[-4:]}'

                    with ui.row().classes(
                        'items-center py-2 px-4 rounded-full w-full gap-3'
                    ).style(f'border: 1px solid {bdr};'):
                        qr_img = ui.image(qr_url).classes(
                            'rounded w-8 h-8 cursor-pointer'
                        )
                        if qr_cid:
                            qr_img.on('click', lambda u=qr_url: open_qr_dialog(u))
                        ui.label(f'{denom} XLM').classes(
                            'font-bold text-sm'
                        ).style(f'color: {txt}; min-width: 60px;')
                        ui.label(short_addr).classes(
                            'text-sm font-mono opacity-70 flex-1'
                        ).style(f'color: {txt};')
                        ui.button(
                            icon='content_copy',
                            on_click=lambda u=pay_uri:
                                ui.run_javascript(
                                    f"navigator.clipboard.writeText('{u}')"
                                ),
                        ).props('flat dense size=sm').style(f'color: {txt} !important;')

