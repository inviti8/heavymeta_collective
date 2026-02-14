# LINKTREES.md — Unified Linktree Rendering Spec

## 1. Overview

Migrate from a dual-path linktree system to a single unified rendering pipeline
backed by IPFS/IPNS JSON.

**Current state:** Two independent rendering paths exist:

| Path | Source | Location |
|------|--------|----------|
| `/profile/{moniker_slug}` (public) | SQLite tables directly | `main.py:730-808` |
| Enrollment only | IPFS/IPNS JSON | `enrollment.py:12-40` |

**Problem:** Linktree JSON is published once at enrollment and never updated.
All subsequent edits (links, colors, settings) only touch SQLite. The public
profile reads from SQLite, not from the IPNS-published JSON. These are two
separate rendering paths that should be unified.

**Target state:** A single `/lt/{ipns_name}` route fetches linktree JSON from
IPFS, falls back to SQLite when IPFS is unavailable, and renders through one
shared function. Every profile edit triggers a re-publish to IPFS/IPNS so the
JSON stays current.

---

## 2. Linktree JSON Schema (v1) — Reference

Defined in `ipfs_client.py:161-231` (`build_linktree_json()`):

```json
{
  "schema_version": 1,
  "moniker": "Fibo",
  "member_type": "coop",
  "avatar_cid": "bafy...abc",
  "dark_mode": null,
  "colors": {
    "light": {
      "primary": "#8c52ff",
      "secondary": "#f2d894",
      "text": "#000000",
      "bg": "#ffffff",
      "card": "#f5f5f5",
      "border": "#e0e0e0"
    },
    "dark": {
      "primary": "#a87aff",
      "secondary": "#d4a843",
      "text": "#f0f0f0",
      "bg": "#1a1a1a",
      "card": "#2a2a2a",
      "border": "#444444"
    }
  },
  "links": [
    { "label": "My Site", "url": "https://example.com", "icon_cid": null, "sort_order": 0 }
  ],
  "wallets": [
    { "network": "stellar", "address": "GXXX..." }
  ],
  "card_design_cid": "bafy...ghi",
  "override_url": ""
}
```

**Field mapping from current SQLite:**

| SQLite source | JSON field |
|---|---|
| `user['moniker']` | `linktree['moniker']` |
| `user['stellar_address']` | `linktree['wallets'][0]['address']` |
| `colors['bg_color']` | `linktree['colors']['light']['bg']` |
| `colors['text_color']` | `linktree['colors']['light']['text']` |
| `colors['accent_color']` | `linktree['colors']['light']['primary']` |
| `colors['link_color']` | `linktree['colors']['light']['secondary']` |
| `db.get_links(user_id)` | `linktree['links']` |
| N/A (placeholder) | `linktree['avatar_cid']` |
| `user['nfc_image_cid']` | `linktree['card_design_cid']` |
| N/A | `linktree['dark_mode']` |

**App status of JSON fields:**

| JSON field | App support | Notes |
|---|---|---|
| `avatar_cid` | TODO: No `users.avatar_cid` DB column, no upload UI | Always `null` — renderer falls back to `/static/placeholder.png` |
| `icon_cid` (per link) | TODO: DB stores `icon_url` (text), no icon upload UI | `build_linktree_json()` bridges via `link.get("icon_cid") or link.get("icon_url")` — but the renderer assumes a bare CID, not a URL. Currently always `null` in practice. |
| `dark_mode` | TODO: No toggle in settings, hard-coded `None` | Renderer uses `colors.light` only |
| `colors.dark.*` | TODO: No per-user dark color columns in `profile_colors` table | Always uses `_DEFAULT_COLORS["dark"]` from `ipfs_client.py` |
| `card_design_cid` | Partial — `nfc_image_cid` exists in `users` table, card editor writes it | TODO: Not rendered on linktree page, not passed at enrollment |
| `sort_order` (per link) | Partial — DB column exists, `get_links()` sorts by it | TODO: No reorder UI — all links default to `sort_order=0` |
| `wallets` (array) | Partial — schema supports multiple, app creates one Stellar entry | TODO: No multi-wallet UI, no "add wallet" flow |
| `colors.light.card` | Not stored | TODO: No UI — uses default `#f5f5f5` |
| `colors.light.border` | Not stored | TODO: No UI — uses default `#e0e0e0` |

---

## 3. New Route: `/lt/{ipns_name}`

### Data Flow

Two paths depending on who is viewing:

```
External visitor (NFC tap / QR scan):
  → heavymeta.coop/lt/k51qzi...
  → NiceGUI route handler
  → fetch_linktree_json(user)   // CID from SQLite → ipfs_cat
  → render_linktree(linktree, ipns_name)
  → HTML page

Owner preview (from dashboard):
  → heavymeta.coop/lt/k51qzi...
  → NiceGUI route handler
  → build_linktree_fresh(user)  // SQLite → build_linktree_json()
  → render_linktree(linktree, ipns_name)
  → HTML page (reflects latest edits immediately)
```

### Route Definition (in `main.py`)

```python
@ui.page('/lt/{ipns_name}')
async def linktree_page(ipns_name: str):
    """Public linktree rendered from IPFS/IPNS JSON."""

    # (1) Validate ipns_name exists in our DB
    user = await db.get_user_by_ipns_name(ipns_name)
    if not user:
        style_page('Heavymeta Profile')
        with ui.column().classes('w-full items-center mt-24'):
            ui.label('Profile not found.').classes('text-2xl opacity-50')
        return

    # (2) Fetch linktree JSON — owner sees fresh SQLite data,
    #     external visitors see published IPFS data
    is_owner = app.storage.user.get('user_id') == user['id']
    if is_owner:
        linktree = await ipfs_client.build_linktree_fresh(user['id'])
    else:
        linktree = await ipfs_client.fetch_linktree_json(user)

    # (3) Override redirect
    if linktree.get('override_url'):
        ui.navigate.to(linktree['override_url'])
        return

    # (4) Render
    render_linktree(linktree, ipns_name)
```

### New DB Function (in `db.py`)

```python
async def get_user_by_ipns_name(ipns_name):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM users WHERE ipns_name = ?", (ipns_name,)
        )
        return await cursor.fetchone()
```

---

## 4. Unified Renderer: `render_linktree()`

### Location

New file: `linktree_renderer.py`

Extracted from the current `public_profile()` rendering logic (`main.py:756-807`),
remapped to read from the JSON schema instead of SQLite row objects.

### Signature

```python
def render_linktree(linktree: dict, ipns_name: str) -> None
```

### Implementation

```python
from nicegui import ui
from config import KUBO_GATEWAY, BLOCK_EXPLORER

def render_linktree(linktree: dict, ipns_name: str):
    style_page('Heavymeta Profile')

    moniker = linktree.get('moniker', 'Unknown')
    colors = linktree.get('colors', {}).get('light', {})  # TODO: dark_mode toggle
    bg = colors.get('bg', '#ffffff')
    txt = colors.get('text', '#000000')
    acc = colors.get('primary', '#8c52ff')
    lnk = colors.get('secondary', '#8c52ff')
    avatar_cid = linktree.get('avatar_cid')  # TODO: always None until avatar upload exists
    links = linktree.get('links', [])
    wallets = linktree.get('wallets', [])  # TODO: only ever one Stellar wallet currently

    # Avatar URL: IPFS gateway if CID exists, else placeholder
    # TODO: will always be placeholder until avatar upload + users.avatar_cid column
    avatar_url = (f'{KUBO_GATEWAY}/ipfs/{avatar_cid}'
                  if avatar_cid else '/static/placeholder.png')

    ui.query('body').style(f'background-color: {bg};')

    # Header with gradient
    with ui.column().classes(
        'w-full items-center py-8'
    ).style(f'background: linear-gradient(to right, #f2d894, {acc}40);'):
        ui.image(avatar_url).classes('w-32 h-32 rounded-full shadow-md')
        ui.label(moniker).classes('text-3xl font-bold mt-4').style(f'color: {txt};')

        # Show first stellar wallet if present
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
        # Links
        if links:
            with ui.column().classes('w-full gap-2 border p-4 rounded-lg'):
                ui.label('LINKS').classes('text-lg font-bold').style(f'color: {txt};')
                for link in sorted(links, key=lambda l: l.get('sort_order', 0)):  # TODO: no reorder UI yet
                    # TODO: icon_cid is always null — no icon upload exists.
                    # When icon upload is added, ensure CIDs (not URLs) are stored.
                    icon_url = (f'{KUBO_GATEWAY}/ipfs/{link["icon_cid"]}'
                                if link.get('icon_cid')
                                else '/static/placeholder.png')
                    with ui.row().classes(
                        'items-center border py-2 px-4 rounded-full w-full'
                    ):
                        ui.image(icon_url).classes('rounded-full w-8 h-8')
                        ui.link(
                            link['label'], link['url'], new_tab=True
                        ).classes('font-semibold text-lg').style(f'color: {lnk};')

        # Wallets
        if wallets:
            with ui.column().classes('w-full gap-2 border p-4 rounded-lg'):
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

    # Footer
    with ui.footer().classes('bg-[#8c52ff] flex justify-center items-center py-3'):
        ui.button(
            icon='arrow_back', on_click=lambda: ui.navigate.to('/')
        ).props('flat round').style('color: white;')
```

---

## 5. IPFS JSON Fetch: `fetch_linktree_json()` and `build_linktree_fresh()`

### Location

`ipfs_client.py`

### Approach

We already store `linktree_cid` in SQLite at publish time. Use that CID
directly with `ipfs_cat()` — no IPNS resolution needed. Kubo is local
(`127.0.0.1:5001`); if it's down, enrollment and card uploads are also broken,
so there's no point adding a fallback for this one path.

For **owner preview**, we skip IPFS entirely and build the JSON fresh from
SQLite. This avoids a staleness window: IPNS publishing takes 2-6 seconds
(measured locally), during which `linktree_cid` in SQLite still points to the
old version. The owner always sees their latest edits; external visitors see
the last successfully published snapshot.

### Implementation

```python
async def fetch_linktree_json(user) -> dict:
    """Fetch published linktree JSON from local Kubo by CID.
    Used for external visitors."""
    import json

    raw = await ipfs_cat(user['linktree_cid'])
    return json.loads(raw)


async def build_linktree_fresh(user_id: str) -> dict:
    """Build linktree JSON directly from SQLite (skips IPFS).
    Used for owner preview so edits are visible immediately."""
    import db as _db

    user = await _db.get_user_by_id(user_id)
    links = await _db.get_links(user_id)
    colors = await _db.get_profile_colors(user_id)
    settings = await _db.get_profile_settings(user_id)

    return build_linktree_json(
        moniker=user['moniker'],
        member_type=user['member_type'],
        stellar_address=user['stellar_address'],
        links=[dict(link) for link in links],
        colors=colors,
        avatar_cid=None,  # TODO: no users.avatar_cid column yet
        card_design_cid=user.get('nfc_image_cid'),
        settings=settings,
    )
```

### Known Data Mismatch: `icon_url` vs `icon_cid`

TODO: The `link_tree` DB table stores `icon_url TEXT` but the JSON schema uses
`icon_cid`. The bridge in `build_linktree_json()` (`ipfs_client.py:207`) does
`link.get("icon_cid") or link.get("icon_url")`, which would pass a full URL
where the renderer expects a bare CID. Currently safe because `icon_url` is
always `NULL` (no icon upload UI exists), so `icon_cid` is always `null` in
the JSON and the renderer falls back to `/static/placeholder.png`. When icon
upload is implemented, it should write CIDs to a new `icon_cid` column (or
repurpose `icon_url` for CIDs only).

---

## 6. Re-Publish on Edit: `republish_linktree()`

### Core Helper (in `ipfs_client.py`)

```python
async def republish_linktree(user_id: str) -> str | None:
    """Rebuild linktree JSON from SQLite and re-publish to IPFS/IPNS.

    Returns the new CID on success, None on failure.
    Called after every linktree-relevant edit.
    """
    import db as _db

    user = await _db.get_user_by_id(user_id)
    if not user or not user['ipns_key_name']:
        return None  # No IPNS key — skip (enrollment may have failed)

    links = await _db.get_links(user_id)
    colors = await _db.get_profile_colors(user_id)
    settings = await _db.get_profile_settings(user_id)

    linktree = build_linktree_json(
        moniker=user['moniker'],
        member_type=user['member_type'],
        stellar_address=user['stellar_address'],
        links=[dict(link) for link in links],
        colors=colors,
        avatar_cid=None,  # TODO: no users.avatar_cid column yet
        card_design_cid=user.get('nfc_image_cid'),
        settings=settings,
    )

    try:
        new_cid, _ = await publish_linktree(
            user['ipns_key_name'],
            linktree,
            old_json_cid=user.get('linktree_cid'),
        )
        await _db.update_user(user_id, linktree_cid=new_cid)
        return new_cid
    except Exception:
        return None  # Fail silently — SQLite is still authoritative
```

### Fire-and-Forget Pattern

IPNS publishing takes 2-6 seconds on the local Kubo node (measured with
`allow-offline=true`). Use `asyncio.create_task()` so it doesn't block the UI.

```python
import asyncio

def schedule_republish(user_id: str):
    """Schedule a non-blocking linktree republish."""
    asyncio.create_task(_safe_republish(user_id))

async def _safe_republish(user_id: str):
    """Wrapper that catches all exceptions to avoid unhandled task errors."""
    try:
        await republish_linktree(user_id)
    except Exception:
        pass  # Logged but not surfaced to user
```

### Edit Points to Instrument

Six callbacks need `ipfs_client.schedule_republish(user_id)` added after their
DB write:

| # | Edit Point | File | Current Line(s) | Trigger After |
|---|---|---|---|---|
| 1 | `add_link()` | `main.py:434-443` | `db.create_link(...)` | `ipfs_client.schedule_republish(user_id)` |
| 2 | `save_edit()` | `main.py:469-477` | `db.update_link(...)` | `ipfs_client.schedule_republish(user_id)` |
| 3 | `do_delete()` | `main.py:489-492` | `db.delete_link(...)` | `ipfs_client.schedule_republish(user_id)` |
| 4 | `save_colors()` | `main.py:712-721` | `db.upsert_profile_colors(...)` | `ipfs_client.schedule_republish(user_id)` |
| 5 | `_save_override()` | `components.py:130-135` | `db.upsert_profile_settings(...)` | `_ipfs.schedule_republish(user_id)` |
| 6 | `process_upload()` | `main.py:550-586` | `db.update_user(...)` (card upload) | `ipfs_client.schedule_republish(user_id)` |

For edit point #5 (`components.py`), add `import ipfs_client as _ipfs` at the
top of the callback scope.

**Note:** `enrollment.py:_setup_ipns()` builds the initial linktree without
`card_design_cid` or `avatar_cid` (both are `None` at enrollment time). This
is correct — those assets don't exist yet when the user first signs up. The
first `schedule_republish()` after a card upload (edit point #6) will include
the CID.

---

## 7. Preview Button Update

### Current Behavior (`components.py:84-89`)

```python
ui.button(
    'PREVIEW',
    on_click=lambda: ui.navigate.to(f'/profile/{moniker_slug}'),
)
```

### New Behavior

Add `ipns_name` parameter to `dashboard_header()`:

```python
def dashboard_header(moniker, member_type, user_id=None,
                     override_enabled=False, override_url='',
                     ipns_name=None):
```

Update PREVIEW button to prefer `/lt/`:

```python
preview_url = f'/lt/{ipns_name}' if ipns_name else f'/profile/{moniker_slug}'
ui.button(
    'PREVIEW',
    on_click=lambda: ui.navigate.to(preview_url),
)
```

### Call Sites to Update

All four already load `user = await db.get_user_by_id(user_id)`, so
`user['ipns_name']` is available.

| Page | File:Line | Add Parameter |
|---|---|---|
| `/profile/edit` | `main.py:388` | `ipns_name=user['ipns_name']` |
| `/card/editor` | `main.py:528` | `ipns_name=user['ipns_name']` |
| `/card/case` | `main.py:617` | `ipns_name=user['ipns_name']` |
| `/settings` | `main.py:661` | `ipns_name=user['ipns_name']` |

---

## 8. Migration from `/profile/{moniker_slug}`

### Redirect Strategy

Convert the existing route to a redirect:

```python
@ui.page('/profile/{moniker_slug}')
async def public_profile(moniker_slug: str):
    """Legacy route — redirects to /lt/{ipns_name}."""
    import aiosqlite
    from config import DATABASE_PATH

    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT ipns_name FROM users WHERE LOWER(REPLACE(moniker, ' ', '-')) = ?",
            (moniker_slug.lower(),)
        )
        user = await cursor.fetchone()

    if not user or not user['ipns_name']:
        style_page('Heavymeta Profile')
        with ui.column().classes('w-full items-center mt-24'):
            ui.label('Profile not found.').classes('text-2xl opacity-50')
        return

    ui.navigate.to(f'/lt/{user["ipns_name"]}')
```

### Timeline

- Phase 3: Both routes active, `/profile/` redirects to `/lt/`
- Phase 4: NFC cards programmed with `/lt/` URLs
- Phase 5: `/profile/` route can be removed (breaking change — only if no
  external links exist)

### Backfill for Pre-IPFS Users

TODO: This script does not exist yet. Needs to be written and run once before
the `/lt/` route can fully replace `/profile/`.

Users enrolled before IPFS integration have `ipns_name = NULL`. A one-time
migration generates keys for them:

```python
async def backfill_ipns_keys():
    """Generate IPNS keys for users enrolled before IPFS integration."""
    import aiosqlite
    from config import DATABASE_PATH

    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT id, moniker, member_type, stellar_address "
            "FROM users WHERE ipns_name IS NULL"
        )
        users = await cursor.fetchall()

    from enrollment import _setup_ipns
    for user in users:
        try:
            await _setup_ipns(user['id'], user['moniker'],
                              user['member_type'], user['stellar_address'])
        except Exception:
            pass  # Log and continue
```

---

## 9. Gateway vs App Route Clarification

| Path | Served by | Content | Purpose |
|------|-----------|---------|---------|
| `/lt/{ipns_name}` | NiceGUI (app route) | Rendered HTML page | User-facing linktree URL for NFC/QR |
| `/ipns/{ipns_name}` | Kubo gateway (reverse proxy) | Raw JSON | Machine-readable / developer access |
| `/ipfs/{cid}` | Kubo gateway (reverse proxy) | Raw content (JSON, images) | Direct CID access for assets |

### Reverse Proxy Config (nginx)

```nginx
# IPFS/IPNS gateway (raw content)
location /ipfs/ {
    proxy_pass http://127.0.0.1:8081/ipfs/;
}
location /ipns/ {
    proxy_pass http://127.0.0.1:8081/ipns/;
}

# App routes (NiceGUI)
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

### Image URLs in Renderer

In production, `KUBO_GATEWAY` (`config.py:65`) should be set to the public
domain (e.g., `https://heavymeta.coop`) so avatar and icon images resolve
through the reverse proxy. In development, it remains
`http://127.0.0.1:8081`.

---

## 10. Error Handling

### IPFS Connectivity Failures

If local Kubo is down, `fetch_linktree_json()` raises and the route shows an
error page for external visitors. This is consistent with the rest of the app —
enrollment and card uploads also require Kubo. Owner preview is unaffected
since `build_linktree_fresh()` reads from SQLite only.

### `republish_linktree()` Failure

Returns `None`. SQLite is already updated from the edit callback. The next
successful republish includes all accumulated changes.

### Image CID Failures

If the Kubo gateway is unreachable, images show broken. Avatar falls back to
`/static/placeholder.png` when `avatar_cid` is `None`.

### Missing IPNS Key

Users with `ipns_name = NULL` (pre-IPFS enrollment or failed setup):
- Cannot be reached at `/lt/` — return 404
- Continue to work at `/profile/{slug}` (renders from SQLite, no redirect)
- Preview button falls back to `/profile/{slug}`
- `republish_linktree()` exits early with `None`

### Stale CID After Failed Republish

IPNS record points to stale JSON but SQLite is current. Acceptable for MVP —
next successful republish resolves the drift.

---

## 11. File Changes Summary

| File | Change Type | Description |
|------|-------------|-------------|
| `linktree_renderer.py` | **NEW** | `render_linktree()` function, extracted from `public_profile()` |
| `ipfs_client.py` | **MODIFY** | Add `fetch_linktree_json()`, `build_linktree_fresh()`, `republish_linktree()`, `schedule_republish()` |
| `db.py` | **MODIFY** | Add `get_user_by_ipns_name()` |
| `main.py` | **MODIFY** | Add `/lt/{ipns_name}` route; convert `/profile/{slug}` to redirect; add `schedule_republish()` to 5 edit points; pass `ipns_name` to `dashboard_header()` |
| `components.py` | **MODIFY** | Add `ipns_name` parameter to `dashboard_header()`; update PREVIEW button URL; add `schedule_republish()` in `_save_override()` |
| `tests/test_linktree.py` | **NEW** | Tests for renderer, fetch, republish, `/lt/` route |

---

## 12. Implementation Sequence

1. **Database layer** — Add `db.get_user_by_ipns_name()`
2. **IPFS layer** — Add `fetch_linktree_json()`, `build_linktree_fresh()`,
   `republish_linktree()`, `schedule_republish()` to `ipfs_client.py`
3. **Renderer** — Create `linktree_renderer.py` with `render_linktree()`. Port
   rendering logic from `public_profile()` (`main.py:756-807`), remapping
   field sources from SQLite rows to JSON dict fields
4. **Routes** — Add `/lt/{ipns_name}` route in `main.py` using
   `fetch_linktree_json()` + `render_linktree()`. Convert `/profile/{slug}` to
   redirect
5. **Edit points** — Instrument all six edit callbacks with
   `ipfs_client.schedule_republish(user_id)`
6. **Preview button** — Add `ipns_name` parameter to `dashboard_header()` in
   `components.py`. Update all four call sites in `main.py`
7. **Tests** — Unit tests for `fetch_linktree_json()` with mocked IPFS.
   Integration test for `republish_linktree()` (requires Kubo). Route test
   for `/lt/` with mock data

---

## 13. Future Extensions (Out of Scope)

These are features the JSON schema already accommodates but the app does not
yet support. The renderer and build functions are written to degrade gracefully
(placeholders, defaults, skipped sections) until these are implemented.

- **TODO: Avatar upload** — Requires: `ALTER TABLE users ADD COLUMN avatar_cid TEXT`,
  upload UI on `/profile/edit`, pin via `replace_asset()`. Until then,
  `avatar_cid` is always `null` and the renderer shows `/static/placeholder.png`.
- **TODO: Link icon upload** — Requires: rename `link_tree.icon_url` to
  `icon_cid` (or add new column), upload UI in link add/edit dialog, pin via
  `replace_asset()`. Until then, all link icons show placeholder.
- **TODO: Dark mode toggle** — Requires: toggle in `/settings`, dark color
  columns in `profile_colors` table (or a second table), renderer logic to
  select `colors.dark` when `dark_mode` is `true`. Until then, `dark_mode` is
  hard-coded `null` and `colors.dark` uses `_DEFAULT_COLORS`.
- **TODO: Link reorder UI** — `sort_order` column exists in `link_tree` but
  all links default to 0. Needs drag-to-reorder or manual ordering on
  `/profile/edit`.
- **TODO: Multi-wallet support** — `wallets` array in JSON supports multiple
  networks but the app only creates one Stellar entry from `users.stellar_address`.
  Needs a `wallets` table and "add wallet" UI.
- **TODO: Card design preview on linktree** — `card_design_cid` is in the JSON
  (from `nfc_image_cid`). Could render a mini NFC card image on the public page.
- **TODO: IPNS backfill script** — `backfill_ipns_keys()` (Section 8) needs to
  be written and run once for users enrolled before IPFS integration.
- **Phase 5 (index-only SQLite)** — Drop `link_tree`, `profile_colors`,
  `profile_settings` tables and read exclusively from IPFS. SQLite becomes a
  lookup index only (`users.ipns_name`, `users.linktree_cid`). Blocked on all
  the above TODOs being resolved first.

---

## 14. Per-Link QR Codes

### Overview

Each link in a user's linktree gets its own QR code, generated automatically
when the link is created. The QR encodes the link's URL directly and uses the
same branded styling as the user's personal QR code (user colors, embedded
avatar, rounded modules, `ERROR_CORRECT_H`). QR images are pinned to IPFS
and referenced by CID in both the SQLite `link_tree` table and the linktree
JSON schema.

On the public-facing linktree, each link's QR thumbnail is clickable. Clicking
opens a dialog with a 3D rendering of that QR code — the same Three.js
rounded-plane presentation used in the main `/qr` view.

### Schema Changes

#### SQLite: `link_tree` table

Add a `qr_cid` column to store the IPFS CID of the generated QR image:

```python
# In db.py migrations list:
"ALTER TABLE link_tree ADD COLUMN qr_cid TEXT",
```

#### Linktree JSON schema (v1)

Add `qr_cid` to each link object:

```json
{
  "links": [
    {
      "label": "My Site",
      "url": "https://example.com",
      "icon_cid": null,
      "qr_cid": "bafy...xyz",
      "sort_order": 0
    }
  ]
}
```

Update `build_linktree_json()` in `ipfs_client.py` to include the new field:

```python
link_list.append({
    "label": link.get("label", ""),
    "url": link.get("url", ""),
    "icon_cid": link.get("icon_cid") or link.get("icon_url"),
    "qr_cid": link.get("qr_cid"),      # ← new field
    "sort_order": link.get("sort_order", 0),
})
```

### QR Generation

Reuse `generate_user_qr()` from `qr_gen.py`. The only difference from the
personal QR is the encoded URL — here it's the link's target URL instead of
the user's profile URL.

```python
# In qr_gen.py — new function:

async def generate_link_qr(user_id: str, link_id: str, url: str):
    """Generate a branded QR code for a specific linktree URL.

    Uses the same colors and avatar as the user's personal QR.
    Pins to IPFS and updates the link_tree row with the CID.
    """
    import db as _db
    import ipfs_client

    user = await _db.get_user_by_id(user_id)
    colors = await _db.get_profile_colors(user_id)
    settings = await _db.get_profile_settings(user_id)

    dark = bool(settings.get('dark_mode', 0))
    fg = colors.get('dark_accent_color' if dark else 'accent_color', '#8c52ff')
    bg = colors.get('dark_bg_color' if dark else 'bg_color', '#ffffff')

    avatar_path = await get_avatar_path(dict(user).get('avatar_cid'))

    try:
        png_bytes = generate_user_qr(url, avatar_path, fg, bg)
        new_cid = await ipfs_client.ipfs_add(png_bytes, 'link_qr.png')
        await _db.update_link(link_id, qr_cid=new_cid)
        return new_cid
    finally:
        if dict(user).get('avatar_cid') and avatar_path != PLACEHOLDER:
            try:
                os.unlink(avatar_path)
            except OSError:
                pass
```

### Generation Triggers

| Event | Action |
|-------|--------|
| Link created (`add_link()`) | Generate QR for the new link |
| Link URL edited (`save_edit()`) | Regenerate QR (URL changed, old CID unpinned) |
| Link deleted (`do_delete()`) | Unpin old QR CID from IPFS |
| Avatar/colors/dark mode changed | Regenerate QR for ALL user links (style changed) |

#### Wiring in `main.py`

After `db.create_link()` in `add_link()`:
```python
link_id = await db.create_link(user_id=user_id, label=..., url=...)
await qr_gen.generate_link_qr(user_id, link_id, url)
ipfs_client.schedule_republish(user_id)
```

After URL edit in `save_edit()`:
```python
await db.update_link(link_id, label=..., url=...)
# Only regenerate QR if URL changed
if new_url != old_url:
    old_link = ...  # fetch before update to get old qr_cid
    if old_link.get('qr_cid'):
        await ipfs_client.ipfs_unpin(old_link['qr_cid'])
    await qr_gen.generate_link_qr(user_id, link_id, new_url)
ipfs_client.schedule_republish(user_id)
```

After `db.delete_link()` in `do_delete()`:
```python
link = await db.get_link_by_id(link_id)  # fetch before delete
if link and link.get('qr_cid'):
    await ipfs_client.ipfs_unpin(link['qr_cid'])
await db.delete_link(link_id)
ipfs_client.schedule_republish(user_id)
```

#### Bulk regeneration (style changes)

Add helper to `qr_gen.py`:
```python
async def regenerate_all_link_qrs(user_id: str):
    """Regenerate QR codes for all of a user's links.
    Called when avatar, colors, or dark mode change."""
    import db as _db

    links = await _db.get_links(user_id)
    for link in links:
        link = dict(link)
        old_cid = link.get('qr_cid')
        if old_cid:
            await ipfs_client.ipfs_unpin(old_cid)
        await generate_link_qr(user_id, link['id'], link['url'])
```

Wire into existing color/avatar/dark_mode change handlers alongside
`regenerate_qr(user_id)`:
```python
await qr_gen.regenerate_qr(user_id)
await qr_gen.regenerate_all_link_qrs(user_id)
```

### DB Helper

Add `get_link_by_id()` to `db.py` (needed for fetching `qr_cid` before
delete/edit):

```python
async def get_link_by_id(link_id):
    async with aiosqlite.connect(DATABASE_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            "SELECT * FROM link_tree WHERE id = ?", (link_id,)
        )
        return await cursor.fetchone()
```

### Public Linktree Renderer — Clickable QR Thumbnails

In `linktree_renderer.py`, replace the current `icon_url` image with the
link's QR code thumbnail. Make it clickable to open a 3D QR dialog.

```python
for link in sorted(links, key=lambda l: l.get('sort_order', 0)):
    qr_cid = link.get('qr_cid')
    qr_url = (f'{KUBO_GATEWAY}/ipfs/{qr_cid}'
              if qr_cid else '/static/placeholder.png')

    with ui.row().classes(
        'items-center py-2 px-4 rounded-full w-full'
    ).style(f'border: 1px solid {bdr};'):
        # QR thumbnail — clickable to open 3D dialog
        qr_img = ui.image(qr_url).classes('rounded w-8 h-8 cursor-pointer')
        qr_img.on('click', lambda url=qr_url: open_qr_dialog(url))

        ui.link(
            link['label'], link['url'], new_tab=True
        ).classes('font-semibold text-lg').style(f'color: {lnk};')
```

### 3D QR Dialog

When a QR thumbnail is clicked, a NiceGUI dialog opens containing a Three.js
scene rendering the QR code on a rounded-corner plane — identical to the
`/qr` view but inside a dialog.

#### Approach: Reuse `qr_view.js` pattern in a dialog-scoped container

```python
def open_qr_dialog(qr_url: str):
    """Open a dialog with a 3D QR code view."""
    import time as _time

    with ui.dialog().props('maximized') as dialog, \
         ui.card().classes('w-full h-full p-0').style(
             'background-color: #1a1a2e;'
         ):
        # Close button
        ui.button(icon='close', on_click=dialog.close).props(
            'flat round'
        ).classes('absolute top-4 right-4 z-10').style('color: white;')

        # 3D scene container (same pattern as /qr view)
        _cv = int(_time.time())
        ui.add_body_html(
            f'<div id="qr-dialog-scene" data-qr-url="{qr_url}"></div>'
            f'<script type="module" src="/static/js/qr_dialog.js?v={_cv}"></script>'
        )

    dialog.open()
```

#### New JS file: `static/js/qr_dialog.js`

A minimal version of `qr_view.js` — same scene setup (renderer, orthographic
camera, rounded-rect ShapeGeometry, MeshBasicMaterial, UV remapping, mouse-
tracking tilt) but:

- Targets `#qr-dialog-scene` instead of `#qr-scene`
- No scan button or scanner overlay
- No click-and-hold download
- Cleans up renderer on dialog close (dispose geometry, material, renderer)

Alternatively, parameterize `qr_view.js` to accept a container ID so both
the `/qr` page and the dialog can share the same scene code:

```javascript
// qr_view.js — already has init(container)
// Just need to export or make it findable by a second bootstrap block

// qr_dialog.js — thin wrapper:
import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js';

function boot() {
  const container = document.getElementById('qr-dialog-scene');
  if (!container) return false;
  initQrScene(container);  // shared function from qr_view.js or inlined
  return true;
}

if (!boot()) {
  const observer = new MutationObserver((_m, obs) => {
    if (boot()) obs.disconnect();
  });
  observer.observe(document.body, { childList: true, subtree: true });
}
```

### Dashboard Link List — Show QR Thumbnail

In `main.py` `/profile/edit` links section, replace the current `icon_url`
image with the link's QR code:

```python
with ui.row().classes('items-center bg-gray-100 py-2 px-4 rounded-full w-full gap-3'):
    qr_cid = link.get('qr_cid') or link['qr_cid']
    qr_url = (f'{config.KUBO_GATEWAY}/ipfs/{qr_cid}'
              if qr_cid else '/static/placeholder.png')
    ui.image(qr_url).classes('rounded w-8 h-8')
    # ... rest of link row
```

### File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `db.py` | **MODIFY** | Add `qr_cid TEXT` migration to `link_tree`; add `get_link_by_id()` |
| `qr_gen.py` | **MODIFY** | Add `generate_link_qr()`, `regenerate_all_link_qrs()` |
| `ipfs_client.py` | **MODIFY** | Add `qr_cid` to link objects in `build_linktree_json()` |
| `main.py` | **MODIFY** | Wire QR generation into `add_link()`, `save_edit()`, `do_delete()`; show QR thumbnail in link list |
| `linktree_renderer.py` | **MODIFY** | Replace icon with clickable QR thumbnail; add `open_qr_dialog()` |
| `static/js/qr_dialog.js` | **NEW** | 3D QR scene for dialog (minimal `qr_view.js` variant) |

### Implementation Sequence

1. **`db.py`** — Add `qr_cid TEXT` migration + `get_link_by_id()`
2. **`ipfs_client.py`** — Add `qr_cid` field to link objects in `build_linktree_json()`
3. **`qr_gen.py`** — Add `generate_link_qr()` and `regenerate_all_link_qrs()`
4. **`main.py`** — Wire QR generation into link CRUD handlers; update link list to show QR thumbnail
5. **`static/js/qr_dialog.js`** — Create 3D dialog scene (reuse `qr_view.js` pattern)
6. **`linktree_renderer.py`** — Replace icon with clickable QR thumbnail + `open_qr_dialog()`
7. **Test** — Add link → QR generated → visible in dashboard + public linktree → click opens 3D dialog
