from nicegui import ui
import db


def _hex_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip('#')
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def outline_glow_css(hex_color: str) -> str:
    """Inline CSS for Pintheon-style outline: border + glow box-shadow."""
    r, g, b = _hex_rgb(hex_color)
    return (
        f'border: 1px solid rgba({r},{g},{b},0.55);'
        f'box-shadow: 0 0 2px rgba({r},{g},{b},0.1),'
        f'0 0 4px rgba({r},{g},{b},0.25),'
        f'0 0 6px rgba({r},{g},{b},0.4);'
    )


def resolve_active_palette(colors: dict, dark_mode: bool) -> dict:
    """Return the 6 active color values from the full 12-color dict."""
    p = 'dark_' if dark_mode else ''
    return {
        'primary': colors[f'{p}accent_color'],
        'secondary': colors[f'{p}link_color'],
        'text': colors[f'{p}text_color'],
        'bg': colors[f'{p}bg_color'],
        'card': colors[f'{p}card_color'],
        'border': colors[f'{p}border_color'],
    }


def apply_theme(primary, secondary, text, bg, card, border):
    """Inject dynamic theme CSS into the current page."""
    pr, pg, pb = _hex_rgb(primary)
    ui.run_javascript(f'''
        let s = document.getElementById('hm-theme');
        if (!s) {{
            s = document.createElement('style');
            s.id = 'hm-theme';
            document.head.appendChild(s);
        }}
        s.textContent = `
            :root {{
                --hm-primary: {primary};
                --hm-secondary: {secondary};
                --hm-text: {text};
                --hm-bg: {bg};
                --hm-card: {card};
                --hm-border: {border};
                --q-primary: {primary};
                --q-secondary: {secondary};
            }}
            body, .q-page {{
                background-color: {bg} !important;
                color: {text} !important;
            }}
            .q-header {{
                background: linear-gradient(to right, {primary}, {secondary}) !important;
                color: {text} !important;
            }}
            .q-footer {{
                background-color: {primary} !important;
            }}
            .q-card:not(.preview-card) {{
                background-color: {card} !important;
                border: 1px solid rgba({pr},{pg},{pb},0.55) !important;
                color: {text} !important;
                box-shadow: 0 0 2px rgba({pr},{pg},{pb},0.1),
                            0 0 4px rgba({pr},{pg},{pb},0.25),
                            0 0 6px rgba({pr},{pg},{pb},0.4) !important;
            }}
            .q-field__control {{
                color: {text} !important;
            }}
            .q-field__label, .q-field__native {{
                color: {text} !important;
            }}
            /* Footer nav buttons — white on primary background */
            .q-footer .q-btn,
            .q-footer .q-btn .q-icon,
            .q-footer .q-btn .q-btn__content {{
                color: white !important;
            }}
            /* Header buttons — theme text color */
            .q-header .q-btn,
            .q-header .q-btn .q-icon,
            .q-header .q-btn .q-btn__content {{
                color: {text} !important;
            }}
        `;
        document.body.style.backgroundColor = '{bg}';
        document.body.style.color = '{text}';
        // Override Quasar's inline --q-primary/--q-secondary on <body>
        document.body.style.setProperty('--q-primary', '{primary}');
        document.body.style.setProperty('--q-secondary', '{secondary}');
    ''')


async def load_and_apply_theme(user_id):
    """Load user's color scheme from DB and apply to current page."""
    colors = await db.get_profile_colors(user_id)
    settings = await db.get_profile_settings(user_id)
    dark = bool(settings.get('dark_mode', 0))
    palette = resolve_active_palette(colors, dark)
    apply_theme(**palette)
