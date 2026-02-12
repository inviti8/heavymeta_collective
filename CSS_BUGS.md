# CSS_BUGS.md — Footer & Button Color Scheme Compliance

## Problem

Footer nav icons and various buttons don't respect the user's color scheme. They use Quasar's default `--q-primary` blue or remain hardcoded despite `apply_theme()` setting CSS variables. The inline `style(f'color: ...')` on buttons is overridden by Quasar's internal specificity.

## Affected Elements

1. **Footer nav icons** — the 4 dashboard nav buttons (badge, palette, collections, qr_code). Set via `style(f'color: {color}')` but Quasar's `text-primary` class wins.
2. **Header buttons** — logout, PREVIEW, settings icons in the dashboard header.
3. **General action buttons** — SAVE, Cancel, Add, etc. throughout the app. These inherit Quasar's primary color.
4. **`.q-icon` elements** — Material Icons inside buttons get their color from the parent button's Quasar color prop.

## Root Cause Analysis

From the rendered HTML (captured from card editor view):

```html
<button class="q-btn q-btn-item ... text-primary q-btn--actionable ...">
  <span class="q-btn__content ...">
    <i class="q-icon notranslate material-icons">badge</i>
  </span>
</button>
```

Quasar adds `text-primary` automatically to buttons. This class maps to `color: var(--q-primary)` which has higher specificity than our inline `style` attribute in some contexts, AND higher specificity than inherited text color.

`apply_theme()` (in `theme.py`) sets `--q-primary` via `:root`, but only after JavaScript runs. The initial render uses Quasar's default `--q-primary: #5898d4`.

## Test Plan

Systematically try CSS selectors to turn the affected elements **red** (`#ff0000`). For each test, add the rule to `apply_theme()` and check if the elements turn red. Cross off failures, keep successes.

### Test Round 1: Footer Nav Icons

Target: the 4 nav buttons in `.q-footer`

| # | CSS Rule | Target | Result |
|---|----------|--------|--------|
| 1 | `.q-footer .q-btn { color: red !important; }` | Button text/icon color | |
| 2 | `.q-footer .q-icon { color: red !important; }` | Icon element directly | |
| 3 | `.q-footer .q-btn.text-primary { color: red !important; }` | Override text-primary class | |
| 4 | `.q-footer .q-btn .q-btn__content { color: red !important; }` | Content wrapper | |
| 5 | `.q-footer .q-btn .q-btn__content .q-icon { color: red !important; }` | Full specificity chain | |
| 6 | `.q-footer .material-icons { color: red !important; }` | Material Icons directly | |
| 7 | `.q-footer [class*="text-primary"] { color: red !important; }` | Attribute selector | |

### Test Round 2: Header Buttons

Target: logout, settings, PREVIEW in `.q-header`

| # | CSS Rule | Target | Result |
|---|----------|--------|--------|
| 8 | `.q-header .q-btn { color: red !important; }` | All header buttons | |
| 9 | `.q-header .q-icon { color: red !important; }` | Header icons | |
| 10 | `.q-header .q-btn.text-primary { color: red !important; }` | Override text-primary | |

### Test Round 3: General Buttons

Target: SAVE, Add, form buttons in `.q-page`

| # | CSS Rule | Target | Result |
|---|----------|--------|--------|
| 11 | `.q-btn--standard.bg-primary { background-color: red !important; }` | Filled buttons bg | |
| 12 | `.q-btn--standard.bg-primary .q-btn__content { color: red !important; }` | Filled button text | |
| 13 | `.q-btn--flat.text-primary { color: red !important; }` | Flat buttons | |

### Test Round 4: CSS Variable Override

Target: replace Quasar's variable at the root so ALL elements using `text-primary` get the theme color

| # | CSS Rule | Target | Result |
|---|----------|--------|--------|
| 14 | `:root { --q-primary: red !important; }` | Global primary override | |
| 15 | `body { --q-primary: red !important; }` | Body-scoped override | |
| 16 | `.q-footer { --q-primary: red !important; }` | Footer-scoped override | |

## Test Procedure

1. Pick the next untested rule from the table
2. Add it to the `apply_theme()` template string in `theme.py` (inside the `:root` block or as a new rule)
3. Reload the app, navigate to dashboard
4. Check if footer icons / header buttons / action buttons turn red
5. Record result (pass/fail) in the table
6. Remove the test rule, move to next

## Solution Applied

Based on root cause analysis, the fix targets three levels of Quasar's DOM: `.q-btn`, `.q-btn .q-icon`, and `.q-btn .q-btn__content` — all with `!important` to beat Quasar's `text-primary` specificity.

### Changes Made

**`theme.py` — `apply_theme()` dynamic CSS:**
```css
/* Footer nav buttons — white on primary background */
.q-footer .q-btn,
.q-footer .q-btn .q-icon,
.q-footer .q-btn .q-btn__content { color: white !important; }

/* Header buttons — theme text color */
.q-header .q-btn,
.q-header .q-btn .q-icon,
.q-header .q-btn .q-btn__content { color: {text} !important; }
```

**`components.py` — `dashboard_header()` static `<style>` block:**
Same rules with hardcoded `black` for header (before theme JS runs) and `white` for footer.

**`components.py` — `dashboard_nav()` simplified:**
Replaced inline `color` style with `opacity` (1.0 active, 0.5 inactive). CSS override forces white on all footer buttons; opacity distinguishes active/inactive.
