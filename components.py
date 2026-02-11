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


def _logout():
    app.storage.user.clear()
    ui.navigate.to('/')
