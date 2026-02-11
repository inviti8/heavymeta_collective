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
            ui.button('Join', on_click=lambda: ui.navigate.to('/join')).props('flat color=white')
            ui.button('Login', on_click=lambda: ui.navigate.to('/login')).props('flat color=white')


def dashboard_nav(active='dashboard'):
    """Bottom navigation bar for dashboard views. active = 'dashboard' | 'card_editor' | 'card_case'."""
    with ui.footer().classes(
        'bg-[#8c52ff] flex justify-around items-center py-3'
        ' transition-all duration-300 transform translate-y-0'
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
                     override_enabled=False, override_url=''):
    """Shared profile header for dashboard views."""
    moniker_slug = moniker.lower().replace(' ', '-')
    ui.add_head_html('<style>.q-page-container { padding-top: 0 !important; }</style>')
    with ui.header(
    ).classes(
        'text-black justify-start items-center bg-gradient-to-r from-[#f2d894] to-[#d6a5e2] pl-6'
        ' transition-all duration-300 transform translate-y-0'
    ).style('position: relative;') as header:
        # Top-right icon buttons
        with ui.row().classes('absolute top-2 right-4 gap-2 items-center'):
            ui.button(
                'PREVIEW',
                on_click=lambda: ui.navigate.to(f'/profile/{moniker_slug}'),
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
            ui.image('/static/placeholder.png').classes('w-[8vw] h-[8vw] rounded-full shadow-md')
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

                    override_toggle.on_value_change(lambda: _save_override())
                    override_input.on('change', lambda e: _save_override())
    return header


_HEADER_BASE = ('text-black justify-start items-center bg-gradient-to-r'
                ' from-[#f2d894] to-[#d6a5e2] pl-6'
                ' transition-all duration-300 transform')
_FOOTER_BASE = ('bg-[#8c52ff] flex justify-around items-center py-3'
                ' transition-all duration-300 transform')


def hide_dashboard_chrome(header, footer=None):
    """Hide the dashboard header (and optionally footer).

    Uses ``app.storage.user['_header_hidden']`` so repeated navigations
    between hidden-header pages don't replay the slide-up animation.
    """
    was_hidden = app.storage.user.get('_header_hidden', False)
    app.storage.user['_header_hidden'] = True

    if was_hidden:
        # Already hidden on previous page — build off-screen, no animation
        header.classes(replace=f'{_HEADER_BASE} -translate-y-full')
        header.visible = False
        if footer:
            footer.classes(replace=f'{_FOOTER_BASE} translate-y-full')
            footer.visible = False
    else:
        # Was visible — animate off-screen
        header.classes(replace=f'{_HEADER_BASE} -translate-y-full')
        ui.timer(0.3, lambda: setattr(header, 'visible', False), once=True)
        if footer:
            footer.classes(replace=f'{_FOOTER_BASE} translate-y-full')
            ui.timer(0.3, lambda: setattr(footer, 'visible', False), once=True)


def show_dashboard_chrome(header, footer=None):
    """Show the dashboard header (and optionally footer).

    If the header was hidden on the previous page, animates it back in.
    Otherwise it's already visible — no animation needed.
    """
    was_hidden = app.storage.user.get('_header_hidden', False)
    app.storage.user['_header_hidden'] = False

    if was_hidden:
        # Was hidden — build off-screen, then animate in
        header.classes(replace=f'{_HEADER_BASE} -translate-y-full')
        header.visible = True
        ui.timer(0.05, lambda: header.classes(
            replace=f'{_HEADER_BASE} translate-y-0'), once=True)
        if footer:
            footer.classes(replace=f'{_FOOTER_BASE} translate-y-full')
            footer.visible = True
            ui.timer(0.05, lambda: footer.classes(
                replace=f'{_FOOTER_BASE} translate-y-0'), once=True)
    # else: header already built visible with translate-y-0 — nothing to do


def _logout():
    app.storage.user.clear()
    ui.navigate.to('/')
