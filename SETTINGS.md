# SETTINGS.md — Unified Theme: Dark/Light Mode & Color Swatch Customization

## Overview

The user's color scheme is a **unified theme** that applies to both the **app UI** (dashboard, header, footer, cards, settings, etc.) and the **public linktree**. The user picks dark or light mode via a toggle, customizes both palettes via swatch buttons, and sees the result reflected across the entire app immediately. On save, the scheme persists and is applied on every subsequent page load.

No system detection — the user decides their mode and colors.

---

## Current State (after Step 1-4 implementation)

### DB Schema (`db.py`)
- `profile_colors` table: 12 columns (6 light + 6 dark)
  - Light: `bg_color`, `text_color`, `accent_color`, `link_color`, `card_color`, `border_color`
  - Dark: `dark_bg_color`, `dark_text_color`, `dark_accent_color`, `dark_link_color`, `dark_card_color`, `dark_border_color`
- `profile_settings` table: includes `dark_mode INTEGER DEFAULT 0`
- Migrations in `init_db()` add columns idempotently for existing DBs

### Settings UI (`main.py:/settings`)
- Dark/light toggle, two palette cards with swatch buttons, live preview, SAVE
- Swatch buttons use glasswing closure pattern with `ui.color_picker`
- Preview reflects active mode — but **only the preview card updates**, not the surrounding app UI

### Linktree JSON (`ipfs_client.py`)
- `build_linktree_json()` maps all 12 DB colors into `colors.light` and `colors.dark`
- `dark_mode` boolean written from `profile_settings.dark_mode`

### Linktree Renderer (`linktree_renderer.py`)
- Selects `colors.dark` or `colors.light` based on `dark_mode` flag

### What's Missing
- **App-wide theme application**: The saved scheme only affects the linktree preview and public linktree. The app UI itself (header, footer, body, cards, nav) still uses hardcoded colors.
- **Live theme updates**: Toggling dark/light or picking a swatch color should update the entire page immediately, not just the preview card.
- **Theme on page load**: Every authenticated page should load the user's saved scheme and apply it.

---

## Glasswing Reference Pattern

From `../glasswing/main.py`:

1. **Swatch buttons**: Flat `ui.button()` with `background-color` set to current value. Click opens `ui.color_picker()`. On pick, button background updates instantly.

2. **Light/dark palettes**: Two `ui.card()` sections, both always visible for editing.

3. **Live theme application**: `apply_theme_colors()` injects a dynamic `<style id="dynamic-theme-colors">` block via `ui.run_javascript()`. Targets body, `.q-page`, `.q-card`, `.q-btn`, `.q-header`, `.q-footer`, etc. with `!important` overrides. Also sets Quasar CSS variables (`--q-primary`, `--q-secondary`).

4. **Three-layer approach**:
   - CSS custom properties on `:root`
   - Quasar variable overrides (`--q-primary`, etc.)
   - Direct DOM + dynamic stylesheet injection for guaranteed specificity

---

## Design — Unified Theme

### Color Scheme (6 colors per mode)

| Swatch | Light Default | Dark Default | DB Column | CSS Variable |
|--------|--------------|-------------|-----------|-------------|
| Primary (accent) | `#8c52ff` | `#a87aff` | `accent_color` / `dark_accent_color` | `--hm-primary` |
| Secondary (links) | `#f2d894` | `#d4a843` | `link_color` / `dark_link_color` | `--hm-secondary` |
| Text | `#000000` | `#f0f0f0` | `text_color` / `dark_text_color` | `--hm-text` |
| Background | `#ffffff` | `#1a1a1a` | `bg_color` / `dark_bg_color` | `--hm-bg` |
| Card | `#f5f5f5` | `#2a2a2a` | `card_color` / `dark_card_color` | `--hm-card` |
| Border | `#e0e0e0` | `#444444` | `border_color` / `dark_border_color` | `--hm-border` |

### Theme Applicator: `apply_theme()`

A shared function in `components.py` (or a new `theme.py`) that takes the 6 active colors and injects them into the page via `ui.run_javascript()`. This is the core mechanism — called on every page load and on every swatch/toggle change in settings.

**What it targets:**
```
body / .q-page             → --hm-bg (background)
body text / .q-page        → --hm-text (color)
.q-header                  → --hm-primary gradient
.q-footer                  → --hm-primary
.q-card                    → --hm-card (background), --hm-border (border)
.q-btn (primary)           → --hm-primary
links / .q-link            → --hm-secondary
--q-primary                → --hm-primary (Quasar override)
--q-secondary              → --hm-secondary (Quasar override)
```

**Implementation approach** (following glasswing pattern):
```python
def apply_theme(primary, secondary, text, bg, card, border):
    """Inject dynamic theme CSS into the current page."""
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
            }}
            .q-footer {{
                background-color: {primary} !important;
            }}
            .q-card {{
                background-color: {card} !important;
                border: 1px solid {border} !important;
                color: {text} !important;
            }}
        `;
    ''')
```

### Where `apply_theme()` Is Called

1. **On every authenticated page load** — after `dashboard_header()` or at page setup, load colors + dark_mode from DB, resolve active palette, call `apply_theme()`.

2. **In `/settings` on toggle/swatch change** — called immediately from `update_preview()` (renamed to `update_theme()`), so the entire page reflects the change live.

3. **In `/settings` on SAVE** — persists to DB, triggers IPFS republish, theme already visually applied.

4. **On public linktree** — `linktree_renderer.py` already applies colors directly via inline styles; no change needed there.

### Helper: `load_and_apply_theme()`

Convenience function for page handlers:
```python
async def load_and_apply_theme(user_id):
    """Load user's color scheme from DB and apply to current page."""
    colors = await db.get_profile_colors(user_id)
    settings = await db.get_profile_settings(user_id)
    dark = bool(settings.get('dark_mode', 0))
    p = 'dark_' if dark else ''
    apply_theme(
        primary=colors[f'{p}accent_color'],
        secondary=colors[f'{p}link_color'],
        text=colors[f'{p}text_color'],
        bg=colors[f'{p}bg_color'],
        card=colors[f'{p}card_color'],
        border=colors[f'{p}border_color'],
    )
```

### Settings Page Layout (updated)

```
  [<  back caret]

  SETTINGS
  "Customize your profile theme"

  ┌─ Mode ──────────────────────────────────┐
  │  LIGHT  [────●] DARK                    │
  └─────────────────────────────────────────┘

  ┌─ PREVIEW ───────────────────────────────┐
  │  (mini linktree: moniker, badge, links) │
  │  renders with active palette colors     │
  └─────────────────────────────────────────┘

  ┌─ Light Palette ─────────────────────────┐
  │  label: "light"                         │
  │  [■ primary] [■ secondary] [■ text]     │
  │  [■ bg]      [■ card]      [■ border]   │
  └─────────────────────────────────────────┘

  ┌─ Dark Palette ──────────────────────────┐
  │  label: "dark"                          │
  │  [■ primary] [■ secondary] [■ text]     │
  │  [■ bg]      [■ card]      [■ border]   │
  └─────────────────────────────────────────┘

  [ SAVE ]
```

- Preview is **above** the palette cards
- Both palettes always visible for customization
- Toggle + swatch changes update the **entire page** immediately (header, footer, body, cards, preview)
- SAVE persists; theme is already visually active

### Swatch Button Behavior

Each swatch is a small square `ui.button()` (flat, no text) with `background-color` matching the color value. Clicking opens `ui.color_picker(on_pick=handler)`. On pick:
1. Button background updates immediately
2. Color stored in local state dict
3. `apply_theme()` called — entire app UI updates live
4. Preview card also updates

Uses the glasswing closure pattern:
```python
def make_handler(key, btn_ref):
    def on_pick(e):
        btn_ref.style(f'background-color: {e.color} !important;')
        state[key] = e.color
        apply_live_theme()  # updates entire page
    return on_pick
```

### Dark/Light Mode Toggle

A `ui.switch()` — off = light, on = dark.

On toggle:
1. **Entire app UI updates immediately** — `apply_theme()` called with the newly-active palette
2. Preview card updates to show the selected mode's colors
3. Value persisted on SAVE

---

## Implementation Steps

### Step 1: DB Schema ✅ DONE
- 12 color columns in `profile_colors`
- `dark_mode` in `profile_settings`
- Migrations for existing DBs

### Step 2: Linktree JSON ✅ DONE
- `build_linktree_json()` maps all 12 DB colors to `colors.light` + `colors.dark`
- `dark_mode` boolean written from settings

### Step 3: Linktree Renderer ✅ DONE
- Selects palette based on `dark_mode` flag

### Step 4: Theme Applicator — NEW

**File:** `theme.py` (new)

Create `apply_theme(primary, secondary, text, bg, card, border)` — injects dynamic `<style id="hm-theme">` via `ui.run_javascript()`.

Create `load_and_apply_theme(user_id)` — loads from DB, resolves active palette, calls `apply_theme()`.

Create `resolve_active_palette(colors, dark_mode)` — returns the 6 active color values given the full 12-color dict and mode flag.

### Step 5: Settings Page — Live Theme Updates

**File:** `main.py` `/settings` handler

- Move preview card **above** the palette cards
- Rename `update_preview()` → `apply_live_theme()` which calls both `apply_theme()` (whole page) and updates the preview card
- On toggle change → `apply_live_theme()`
- On swatch pick → `apply_live_theme()`
- On SAVE → persist + IPFS republish (theme already visually applied)

### Step 6: Apply Theme on All Authenticated Pages

**File:** `main.py` — every page handler that uses `dashboard_header()`

After building the page, call `await load_and_apply_theme(user_id)`.

Pages to update:
- `/profile/edit` (dashboard)
- `/card/editor`
- `/card/case`
- `/settings` (already has live theme from Step 5)
- `/launch`

Also update `components.py`:
- `dashboard_header()` — the gradient currently hardcodes `from-[#f2d894] to-[#d6a5e2]`. This should use the theme colors instead. The CSS injection from `apply_theme()` will override via `.q-header` targeting.
- `dashboard_nav()` footer — currently hardcodes `bg-[#8c52ff]`. Will be overridden by `.q-footer` targeting.

### Step 7: Non-authenticated pages

The landing page (`/`) and public linktree use their own color schemes and should NOT be affected by the user's theme. No changes needed — the dynamic `<style>` is only injected on authenticated pages.

---

## Files Modified

| File | Changes |
|------|---------|
| `db.py` | ✅ 12 color columns, `dark_mode` setting, migrations |
| `ipfs_client.py` | ✅ Maps all colors to JSON, propagates `dark_mode` |
| `linktree_renderer.py` | ✅ Selects palette based on `dark_mode` flag |
| `theme.py` | **NEW** — `apply_theme()`, `load_and_apply_theme()`, `resolve_active_palette()` |
| `main.py` | Update `/settings` (preview above swatches, live theme), add `load_and_apply_theme()` calls to all dashboard pages |
| `components.py` | No hardcoded changes needed — CSS injection overrides header/footer colors |

## Verification

1. Fresh DB — new columns created with defaults, app loads with default light theme
2. Existing DB — migrations add columns, existing users get defaults
3. `/settings` — toggle dark/light → entire page (header, body, cards, footer) updates immediately
4. `/settings` — click swatch → color picker opens, pick a color → entire page updates live
5. Preview card renders above swatches with active palette colors
6. SAVE → navigate away → return → theme persists
7. Navigate to `/profile/edit` → user's saved theme applied on load
8. Navigate to `/card/editor` → same theme applied
9. Toggle to dark, save, go to `/profile/edit` → dark palette applied
10. Public linktree (`/lt/` or `/profile/`) → renders with correct palette from JSON
11. Landing page (`/`) → NOT affected by user's theme (uses default app colors)
12. Log out → log in as different user → that user's theme applied
