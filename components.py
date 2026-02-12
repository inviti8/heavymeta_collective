from nicegui import ui, app


def form_field(label: str, placeholder: str, password=False):
    with ui.column().classes('w-full gap-1'):
        ui.label(label).classes('text-base tracking-widest opacity-70')
        field = ui.input(placeholder).props('outlined')
        if password:
            field.props('type=password')
        field.classes('w-full')
        return field


def image_with_text(img_src: str, text: str):
    with ui.row().classes('w-full max-w-5l items-start gap-8'):
        ui.image(img_src).classes('w-1/2').props('fit=cover')
        ui.label(text).classes('text-base leading-relaxed')


def user_link(img_src: str, url: str):
    with ui.row().classes('items-center border py-2 px-4 mx-5 rounded-full').style('box-sizing: border-box;'):
        ui.image(img_src).classes('rounded-full w-[3vw] h-[3vw]')
        ui.link(url).classes('text-[#8c52ff] font-semibold text-lg')


def user_wallet(img_src: str):
    return


def style_page(page_title: str):
    ui.page_title(page_title)
    ui.colors(primary='#8c52ff', secondary='#2c2f36', accent='#ffffff', neutral='#f5f5f5')
    with ui.header().classes('items-center'):
        ui.button('HEAVYMETA COLLECTIVE', on_click=lambda: ui.navigate.to('/')).classes('text-lg font-semibold')
        ui.space()
        authenticated = app.storage.user.get('authenticated', False)
        if authenticated:
            member_type = app.storage.user.get('member_type', 'free')
            ui.button('Profile', on_click=lambda: ui.navigate.to('/profile/edit')).props('flat color=white')
            if member_type == 'coop':
                ui.button('Launch', on_click=lambda: ui.navigate.to('/launch')).props('flat color=white')
            ui.button('Logout', on_click=lambda: _logout()).props('flat color=white')
        else:
            ui.button('Join', on_click=lambda: _open_dialog('join')).props('flat color=white')
            ui.button('Login', on_click=lambda: _open_dialog('login')).props('flat color=white')


def dashboard_nav(active='dashboard'):
    """Bottom navigation bar for dashboard views. active = 'dashboard' | 'card_editor' | 'card_case'."""
    with ui.footer().classes(
        'bg-[#8c52ff] flex justify-around items-center py-3'
    ) as footer:
        items = [
            ('badge', '/profile/edit', 'dashboard'),
            ('palette', '/card/editor', 'card_editor'),
            ('collections', '/card/case', 'card_case'),
        ]
        for icon, route, key in items:
            color = 'white' if key == active else 'rgba(255,255,255,0.5)'
            ui.button(
                icon=icon,
                on_click=lambda r=route: ui.navigate.to(r),
            ).props(f'flat round').style(f'color: {color}; font-size: 26px;')
    return footer


def dashboard_header(moniker, member_type, user_id=None,
                     override_enabled=False, override_url='',
                     ipns_name=None, avatar_cid=None):
    """Shared profile header for dashboard views."""
    moniker_slug = moniker.lower().replace(' ', '-')
    ui.add_head_html('''
    <style>
      .q-page-container { padding-top: 0 !important; }
      .q-header { transition: transform 0.3s ease !important; }
      .q-footer { transition: transform 0.3s ease !important; }
      #avatar-scene {
        position: fixed;
        border-radius: 50%;
        overflow: hidden;
        z-index: 6000;
        pointer-events: auto;
      }
    </style>
    ''')
    with ui.header(
    ).classes(
        'text-black justify-start items-center bg-gradient-to-r from-[#f2d894] to-[#d6a5e2] pl-6'
    ).style('position: relative;') as header:
        # Top-left logout caret
        def _confirm_logout():
            with ui.dialog() as dlg, ui.card().classes('p-6 gap-4'):
                ui.label('Log out?').classes('text-lg font-semibold')
                with ui.row().classes('w-full justify-end gap-2'):
                    ui.button('Cancel', on_click=dlg.close).props('flat')
                    ui.button('Log out', on_click=lambda: _logout()).props('flat color=red')
            dlg.open()

        ui.button(
            icon='logout', on_click=_confirm_logout,
        ).props('flat round').classes('absolute top-2 left-2 text-black opacity-70').style(
            'font-size: 18px;'
        )

        # Top-right icon buttons
        with ui.row().classes('absolute top-2 right-4 gap-2 items-center'):
            preview_url = f'/profile/{moniker_slug}'
            ui.button(
                'PREVIEW',
                on_click=lambda: ui.navigate.to(preview_url),
            ).props('flat dense rounded no-caps').classes(
                'bg-white/50 text-black px-5 py-2'
            ).style('font-size: 16px;')
            ui.button(
                on_click=lambda: ui.navigate.to('/launch'),
            ).props('flat round').classes('opacity-90').style(
                "background-image: url('/static/pintheon_logo.png');"
                "background-size: 40px 40px;"
                "background-repeat: no-repeat;"
                "background-position: center;"
                "font-size: 18px;"
            )
            ui.button(
                icon='settings',
                on_click=lambda: ui.navigate.to('/settings'),
            ).props('flat round').classes('text-black opacity-70').style(
                'font-size: 18px;'
            )

        with ui.row().classes('items-center gap-4 ml-6 my-2'):
            # Layout spacer — the 3D scene overlays this via fixed positioning
            import config
            avatar_url = (f'{config.KUBO_GATEWAY}/ipfs/{avatar_cid}'
                          if avatar_cid else '/static/placeholder.png')
            ui.element('div').classes('avatar-placeholder shadow-md').style(
                'width: 8vw; height: 8vw; border-radius: 50%;'
            )
            import time as _time
            _av = int(_time.time())
            ui.add_body_html(
                f'<div id="avatar-scene" data-avatar-url="{avatar_url}"></div>'
                f'<script type="module" src="/static/js/avatar_scene.js?v={_av}"></script>'
            )
            with ui.column().classes('gap-1'):
                ui.label(moniker).classes('text-2xl font-bold')
                badge_text = 'COOP MEMBER' if member_type == 'coop' else 'FREE MEMBER'
                with ui.element('div').classes(
                    'bg-[#ffde59] px-3 py-1 rounded-lg shadow-md'
                ).style('display: inline-block; width: fit-content;'):
                    ui.label(badge_text).classes('text-xs font-bold')

                # Override linktree row
                with ui.row().classes('items-center gap-2 mt-1'):
                    ui.image('/static/pintheon_logo.png').classes('w-5 h-5')
                    ui.label('override linktree').classes('text-xs opacity-70')
                    override_toggle = ui.switch('', value=bool(override_enabled)).props('dense')
                    override_input = ui.input(
                        placeholder='https://your-site.com',
                        value=override_url or '',
                    ).props('outlined dense').classes('text-xs').style('min-width: 200px;')
                    override_input.bind_visibility_from(override_toggle, 'value')

                if user_id:
                    import db as _db

                    async def _save_override():
                        await _db.upsert_profile_settings(
                            user_id,
                            linktree_override=int(override_toggle.value),
                            linktree_url=override_input.value.strip(),
                        )
                        import ipfs_client as _ipfs
                        _ipfs.schedule_republish(user_id)

                    override_toggle.on_value_change(lambda: _save_override())
                    override_input.on('change', lambda e: _save_override())
    return header


def hide_dashboard_chrome(header, footer=None):
    """Hide header and collapse its layout space.

    The header uses position:relative so it normally takes up flow space.
    Setting display:none removes it entirely from the layout.
    """
    header.set_visibility(False)
    header.style('display: none;')
    if footer:
        footer.set_visibility(False)
        footer.style('display: none;')


def show_dashboard_chrome(header, footer=None):
    """Slide the header down into view.

    Header is created visible (value=True). We immediately force it hidden
    (batched with creation, so the browser never renders it visible), then
    delayed show lets the CSS transition animate it in.
    """
    header.value = False
    ui.timer(0.05, header.show, once=True)
    if footer:
        footer.value = False
        ui.timer(0.05, footer.show, once=True)


def _open_dialog(tab):
    from auth_dialog import open_auth_dialog
    open_auth_dialog(tab)


def _logout():
    app.storage.user.clear()
    ui.navigate.to('/')
