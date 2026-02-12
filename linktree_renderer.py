from nicegui import ui
from config import KUBO_GATEWAY, BLOCK_EXPLORER


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

    # 3D avatar scene CSS
    ui.add_head_html('''
    <style>
      #avatar-scene {
        position: fixed;
        border-radius: 50%;
        overflow: hidden;
        z-index: 99999;
        pointer-events: auto;
      }
    </style>
    ''')

    if is_preview:
        ui.button(icon='chevron_left', on_click=lambda: ui.navigate.back()).props(
            'flat round'
        ).classes('absolute top-2 left-2 opacity-70').style(f'color: {txt};')

    with ui.column().classes(
        'w-full items-center py-8'
    ).style(f'background: linear-gradient(to right, {acc}, {lnk});'):
        # Layout spacer — the 3D scene overlays this via fixed positioning
        ui.element('div').classes('avatar-placeholder shadow-md').style(
            'width: 8rem; height: 8rem; border-radius: 50%;'
        )
        import time as _time
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
                    icon_url = (f'{KUBO_GATEWAY}/ipfs/{link["icon_cid"]}'
                                if link.get('icon_cid')
                                else '/static/placeholder.png')
                    with ui.row().classes(
                        'items-center py-2 px-4 rounded-full w-full'
                    ).style(f'border: 1px solid {bdr};'):
                        ui.image(icon_url).classes('rounded-full w-8 h-8')
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
                        ).props('flat dense size=sm')

    with ui.footer().classes('flex justify-center items-center py-3').style(
        f'background-color: {acc};'
    ):
        ui.button(
            icon='arrow_back', on_click=lambda: ui.navigate.to('/')
        ).props('flat round').style('color: white;')
