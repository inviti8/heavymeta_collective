"""Thin async wrapper around Kubo's HTTP API for IPFS/IPNS operations."""

import base64
import json
import os
import httpx
from config import KUBO_API


# ── Content Operations ──

async def ipfs_add(data: bytes, filename: str = "data") -> str:
    """Pin bytes to IPFS, return CID."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{KUBO_API}/add",
            files={"file": (filename, data)},
            params={"pin": "true"},
        )
        resp.raise_for_status()
        return resp.json()["Hash"]


async def ipfs_add_json(obj: dict) -> str:
    """Pin JSON object to IPFS, return CID."""
    data = json.dumps(obj, separators=(",", ":")).encode()
    return await ipfs_add(data, "linktree.json")


async def ipfs_cat(cid: str) -> bytes:
    """Retrieve content by CID."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{KUBO_API}/cat", params={"arg": cid})
        resp.raise_for_status()
        return resp.content


async def ipfs_pin(cid: str):
    """Ensure CID is pinned."""
    async with httpx.AsyncClient() as client:
        await client.post(f"{KUBO_API}/pin/add", params={"arg": cid})


async def ipfs_unpin(cid: str):
    """Unpin CID — content becomes garbage-collectible."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(f"{KUBO_API}/pin/rm", params={"arg": cid})
            resp.raise_for_status()
        except httpx.HTTPStatusError:
            pass  # already unpinned


# ── IPNS Key Management ──

async def ipns_key_gen(name: str) -> str:
    """Generate a new IPNS keypair, return the IPNS name (peer ID)."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{KUBO_API}/key/gen",
            params={"arg": name, "type": "ed25519"},
        )
        resp.raise_for_status()
        return resp.json()["Id"]


def _keystore_path(name: str) -> str:
    """Get the filesystem path for a key in Kubo's keystore.

    Kubo stores keys as files named 'key_{base32lower_nopad(name)}'
    in $IPFS_PATH/keystore/ (defaults to ~/.ipfs/keystore/).
    """
    encoded = base64.b32encode(name.encode()).decode().lower().rstrip("=")
    ipfs_path = os.environ.get("IPFS_PATH", os.path.expanduser("~/.ipfs"))
    return os.path.join(ipfs_path, "keystore", f"key_{encoded}")


async def ipns_key_export(name: str) -> bytes:
    """Export raw IPNS key bytes from Kubo's keystore (for encrypted backup).

    Reads directly from the keystore directory since the HTTP API
    does not expose key/export.
    """
    path = _keystore_path(name)
    with open(path, "rb") as f:
        return f.read()


async def ipns_publish(key_name: str, cid: str) -> str:
    """Publish CID under IPNS key, return the IPNS name."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{KUBO_API}/name/publish",
            params={
                "arg": f"/ipfs/{cid}",
                "key": key_name,
                "allow-offline": "true",
            },
        )
        resp.raise_for_status()
        return resp.json()["Name"]


async def ipns_resolve(ipns_name: str) -> str:
    """Resolve IPNS name to current CID."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{KUBO_API}/name/resolve",
            params={"arg": ipns_name},
        )
        resp.raise_for_status()
        path = resp.json()["Path"]  # "/ipfs/bafy..."
        return path.split("/ipfs/")[-1]


# ── High-Level Operations ──

async def publish_linktree(key_name: str, linktree: dict,
                           old_json_cid: str = None) -> tuple[str, str]:
    """Pin linktree JSON and publish via IPNS.
    Returns (new_json_cid, ipns_name).
    Unpins old JSON CID if provided."""
    new_cid = await ipfs_add_json(linktree)
    ipns_name = await ipns_publish(key_name, new_cid)
    if old_json_cid and old_json_cid != new_cid:
        await ipfs_unpin(old_json_cid)
    return new_cid, ipns_name


async def replace_asset(new_data: bytes, old_cid: str = None,
                        filename: str = "asset") -> str:
    """Pin new asset, unpin old one. Returns new CID."""
    new_cid = await ipfs_add(new_data, filename)
    if old_cid and old_cid != new_cid:
        await ipfs_unpin(old_cid)
    return new_cid


# ── Linktree Assembly ──

_DEFAULT_COLORS = {
    "light": {
        "primary": "#8c52ff",
        "secondary": "#f2d894",
        "text": "#000000",
        "bg": "#ffffff",
        "card": "#f5f5f5",
        "border": "#e0e0e0",
    },
    "dark": {
        "primary": "#a87aff",
        "secondary": "#d4a843",
        "text": "#f0f0f0",
        "bg": "#1a1a1a",
        "card": "#2a2a2a",
        "border": "#444444",
    },
}


def build_linktree_json(*, moniker, member_type, stellar_address=None,
                        links=None, colors=None, avatar_cid=None,
                        card_design_cid=None, override_url="",
                        settings=None):
    """Assemble schema v1 linktree JSON from current data.

    Bridges Phase 2→3 by producing the canonical JSON structure
    from existing SQLite data or enrollment defaults.

    Args:
        moniker: User display name.
        member_type: 'free' or 'coop'.
        stellar_address: Stellar public key (coop members).
        links: List of link dicts with label, url, icon_cid, sort_order.
        colors: Dict with 'light' and 'dark' sub-dicts, or legacy
                profile_colors dict (bg_color, text_color, etc.).
        avatar_cid: IPFS CID for profile image.
        card_design_cid: IPFS CID for NFC card image.
        override_url: External URL redirect (empty = disabled).
        settings: Legacy profile_settings dict.
    """
    # Normalize colors from legacy format if needed
    if colors and "light" in colors:
        color_obj = colors
    elif colors:
        # Legacy profile_colors → new schema mapping
        color_obj = {
            "light": {
                "primary": colors.get("accent_color", _DEFAULT_COLORS["light"]["primary"]),
                "secondary": colors.get("link_color", _DEFAULT_COLORS["light"]["secondary"]),
                "text": colors.get("text_color", _DEFAULT_COLORS["light"]["text"]),
                "bg": colors.get("bg_color", _DEFAULT_COLORS["light"]["bg"]),
                "card": _DEFAULT_COLORS["light"]["card"],
                "border": _DEFAULT_COLORS["light"]["border"],
            },
            "dark": dict(_DEFAULT_COLORS["dark"]),
        }
    else:
        color_obj = dict(_DEFAULT_COLORS)

    # Build links array
    link_list = []
    for link in (links or []):
        link_list.append({
            "label": link.get("label", "") if isinstance(link, dict) else link["label"],
            "url": link.get("url", "") if isinstance(link, dict) else link["url"],
            "icon_cid": link.get("icon_cid") or link.get("icon_url"),
            "sort_order": link.get("sort_order", 0),
        })

    # Build wallets
    wallets = []
    if stellar_address:
        wallets.append({"network": "stellar", "address": stellar_address})

    # Override URL from settings if present
    if settings and settings.get("linktree_override") and settings.get("linktree_url"):
        override_url = settings["linktree_url"]

    return {
        "schema_version": 1,
        "moniker": moniker,
        "member_type": member_type,
        "avatar_cid": avatar_cid,
        "dark_mode": None,
        "colors": color_obj,
        "links": link_list,
        "wallets": wallets,
        "card_design_cid": card_design_cid,
        "override_url": override_url or "",
    }
