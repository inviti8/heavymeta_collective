import time as _time

from nicegui import ui
from config import KUBO_GATEWAY, BLOCK_EXPLORER


def open_qr_dialog(qr_url: str):
    """Open a dialog showing the QR code image."""
    with ui.dialog() as dialog, ui.card().classes(
        'items-center p-6'
    ).style('background-color: #1a1a2e; border-radius: 16px;'):
        ui.image(qr_url).classes('w-64 h-64 rounded-lg')

    dialog.open()


def render_linktree(linktree: dict, ipns_name: str, is_preview: bool = False):
    ui.page_title('Heavymeta Profile')

    moniker = linktree.get('moniker', 'Unknown')
    dark_mode = linktree.get('dark_mode', False)
    palette_key = 'dark' if dark_mode else 'light'
    colors = linktree.get('colors', {}).get(palette_key, {})
    bg = colors.get('bg', '#ffffff')
    txt = colors.get('text', '#000000')
    acc = colors.get('primary', '#8c52ff')
    lnk = colors.get('secondary', '#f2d894')
    card_bg = colors.get('card', '#f5f5f5')
    bdr = colors.get('border', '#e0e0e0')
    avatar_cid = linktree.get('avatar_cid')
    links = linktree.get('links', [])
    wallets = linktree.get('wallets', [])

    avatar_url = (f'{KUBO_GATEWAY}/ipfs/{avatar_cid}'
                  if avatar_cid else '/static/placeholder.png')

    ui.query('body').style(f'background-color: {bg};')

    # Dark base + fade-in + 3D avatar scene CSS + icon color override
    ui.add_head_html(f'''
    <style>
      html, body {{ background-color: #1a1a2e !important; }}
      @keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}
      .nicegui-content {{ animation: fadeIn 0.25s ease-out; }}
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

        stellar_wallet = next(
            (w for w in wallets if w['network'] == 'stellar'), None
        )
        if stellar_wallet:
            addr = stellar_wallet['address']
            short = f"{addr[:6]}...{addr[-4:]}"
            ui.link(
                short, f'{BLOCK_EXPLORER}/account/{addr}', new_tab=True
            ).classes('font-semibold text-sm').style(f'color: {lnk};')

    with ui.column().classes('w-full items-center gap-8 mt-8').style(
        'padding-inline: clamp(1rem, 25vw, 50rem);'
    ):
        if links:
            with ui.column().classes('w-full gap-2 p-4 rounded-lg').style(
                f'border: 1px solid {bdr};'
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

        if wallets:
            with ui.column().classes('w-full gap-2 p-4 rounded-lg').style(
                f'border: 1px solid {bdr};'
            ):
                ui.label('WALLETS').classes('text-lg font-bold').style(f'color: {txt};')
                for wallet in wallets:
                    with ui.row().classes('items-center gap-2 w-full'):
                        ui.image('/static/placeholder.png').classes(
                            'rounded-full w-8 h-8'
                        )
                        ui.label(wallet['address']).classes(
                            'text-sm font-mono break-all flex-1'
                        )
                        ui.button(
                            icon='content_copy',
                            on_click=lambda a=wallet['address']:
                                ui.run_javascript(
                                    f"navigator.clipboard.writeText('{a}')"
                                ),
                        ).props('flat dense size=sm').style(f'color: {txt} !important;')

