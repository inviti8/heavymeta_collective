"""Integration tests for ipfs_client against local Kubo node."""

import json
import uuid
import pytest
import httpx

# Skip entire module if Kubo isn't reachable
pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def require_kubo():
    """Skip all tests if Kubo isn't running on localhost:5001."""
    try:
        async with httpx.AsyncClient() as c:
            r = await c.post("http://127.0.0.1:5001/api/v0/id")
            r.raise_for_status()
    except Exception:
        pytest.skip("Kubo not running on localhost:5001")


@pytest.fixture
async def temp_key_name():
    """Generate a unique key name and clean up after test."""
    name = f"test-{uuid.uuid4().hex[:8]}"
    yield name
    # Clean up: remove the key from Kubo
    try:
        async with httpx.AsyncClient() as c:
            await c.post(
                "http://127.0.0.1:5001/api/v0/key/rm",
                params={"arg": name},
            )
    except Exception:
        pass


async def test_add_and_cat():
    """Round-trip: add bytes, cat back, verify match."""
    import ipfs_client

    data = b"hello heavymeta collective"
    cid = await ipfs_client.ipfs_add(data, "test.txt")
    assert cid  # non-empty CID string

    retrieved = await ipfs_client.ipfs_cat(cid)
    assert retrieved == data


async def test_add_json():
    """Add a dict as JSON, cat back, parse, verify equality."""
    import ipfs_client

    obj = {"name": "fibo", "links": [1, 2, 3], "nested": {"a": True}}
    cid = await ipfs_client.ipfs_add_json(obj)
    assert cid

    raw = await ipfs_client.ipfs_cat(cid)
    parsed = json.loads(raw)
    assert parsed == obj


async def test_pin_unpin():
    """Add content, unpin it, verify no error."""
    import ipfs_client

    cid = await ipfs_client.ipfs_add(b"pin test data")
    # Should not raise
    await ipfs_client.ipfs_unpin(cid)
    # Double unpin should also not raise
    await ipfs_client.ipfs_unpin(cid)


async def test_key_gen_and_export(temp_key_name):
    """Generate IPNS key, export, verify bytes returned."""
    import ipfs_client

    ipns_name = await ipfs_client.ipns_key_gen(temp_key_name)
    assert ipns_name  # should be a peer ID string (k51... or 12D3...)

    key_bytes = await ipfs_client.ipns_key_export(temp_key_name)
    assert isinstance(key_bytes, bytes)
    assert len(key_bytes) > 0


async def test_publish_and_resolve(temp_key_name):
    """Generate key, publish CID under it, resolve back, verify match."""
    import ipfs_client

    # Generate key
    await ipfs_client.ipns_key_gen(temp_key_name)

    # Add some content
    cid = await ipfs_client.ipfs_add(b"publish test")

    # Publish under the key
    ipns_name = await ipfs_client.ipns_publish(temp_key_name, cid)
    assert ipns_name

    # Resolve should return the same CID
    resolved_cid = await ipfs_client.ipns_resolve(ipns_name)
    assert resolved_cid == cid


async def test_publish_linktree(temp_key_name):
    """High-level: build JSON, publish, resolve, cat, verify schema."""
    import ipfs_client

    await ipfs_client.ipns_key_gen(temp_key_name)

    linktree = ipfs_client.build_linktree_json(
        moniker="TestUser",
        member_type="free",
        links=[{"label": "My Site", "url": "https://example.com", "sort_order": 0}],
    )
    new_cid, ipns_name = await ipfs_client.publish_linktree(temp_key_name, linktree)
    assert new_cid
    assert ipns_name

    # Resolve and fetch the JSON
    resolved_cid = await ipfs_client.ipns_resolve(ipns_name)
    assert resolved_cid == new_cid

    raw = await ipfs_client.ipfs_cat(resolved_cid)
    doc = json.loads(raw)
    assert doc["schema_version"] == 1
    assert doc["moniker"] == "TestUser"
    assert doc["member_type"] == "free"
    assert len(doc["links"]) == 1
    assert doc["links"][0]["label"] == "My Site"


async def test_replace_asset():
    """Add asset, replace it, verify new CID is different."""
    import ipfs_client

    old_cid = await ipfs_client.ipfs_add(b"original asset", "asset.png")
    new_cid = await ipfs_client.replace_asset(b"replacement asset", old_cid, "asset.png")
    assert new_cid
    assert new_cid != old_cid

    # Verify new content is correct
    content = await ipfs_client.ipfs_cat(new_cid)
    assert content == b"replacement asset"


async def test_build_linktree_json():
    """Verify JSON structure matches schema v1."""
    import ipfs_client

    doc = ipfs_client.build_linktree_json(
        moniker="Fibo",
        member_type="coop",
        stellar_address="GXXX...",
        links=[
            {"label": "Dev Site", "url": "https://heavymeta.dev", "icon_cid": None, "sort_order": 0},
            {"label": "Portfolio", "url": "https://example.com", "sort_order": 1},
        ],
        avatar_cid="bafy...abc",
        card_design_cid="bafy...ghi",
        override_url="",
    )

    assert doc["schema_version"] == 1
    assert doc["moniker"] == "Fibo"
    assert doc["member_type"] == "coop"
    assert doc["avatar_cid"] == "bafy...abc"
    assert doc["dark_mode"] is None
    assert "light" in doc["colors"]
    assert "dark" in doc["colors"]
    assert len(doc["colors"]["light"]) == 6
    assert len(doc["colors"]["dark"]) == 6
    assert len(doc["links"]) == 2
    assert doc["links"][0]["label"] == "Dev Site"
    assert doc["links"][1]["sort_order"] == 1
    assert len(doc["wallets"]) == 1
    assert doc["wallets"][0]["network"] == "stellar"
    assert doc["wallets"][0]["address"] == "GXXX..."
    assert doc["card_design_cid"] == "bafy...ghi"
    assert doc["override_url"] == ""


async def test_build_linktree_json_legacy_colors():
    """Verify legacy profile_colors dict maps correctly to new schema."""
    import ipfs_client

    legacy_colors = {
        "bg_color": "#111111",
        "text_color": "#222222",
        "accent_color": "#333333",
        "link_color": "#444444",
    }
    doc = ipfs_client.build_linktree_json(
        moniker="Legacy",
        member_type="free",
        colors=legacy_colors,
    )

    assert doc["colors"]["light"]["bg"] == "#111111"
    assert doc["colors"]["light"]["text"] == "#222222"
    assert doc["colors"]["light"]["primary"] == "#333333"
    assert doc["colors"]["light"]["secondary"] == "#444444"
    # Dark mode should use defaults
    assert doc["colors"]["dark"]["bg"] == "#1a1a1a"
