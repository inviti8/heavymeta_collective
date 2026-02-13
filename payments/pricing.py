import time
import requests
import httpx

# ── Tier definitions ──────────────────────────────────────────────
# Prices are in USD. XLM/OPUS amounts calculated at runtime from live rates.
# "join" = one-time enrollment fee. "annual" = yearly renewal.

TIERS = {
    'free': {
        'label': 'FREE',
        'description': 'Linktree only',
        'join_usd': 0,
        'annual_usd': 0,
    },
    'spark': {
        'label': 'SPARK',
        'description': 'QR cards, basic access',
        'join_usd': 29.99,
        'annual_usd': 49.99,
    },
    'forge': {
        'label': 'FORGE',
        'description': 'NFC cards, Pintheon node, full access',
        'join_usd': 59.99,
        'annual_usd': 99.99,
    },
    'founding_forge': {
        'label': 'FOUNDING FORGE',
        'description': 'Limited to 100 — governance vote, unlimited invites',
        'join_usd': 79.99,
        'annual_usd': 49.99,  # locked rate
    },
    'anvil': {
        'label': 'ANVIL',
        'description': 'Advisory board access',
        'join_usd': 149.99,
        'annual_usd': 249.99,
    },
}

# ── Discount rates by payment method ─────────────────────────────
# All discounts are off the USD base price.
DISCOUNTS = {
    'card': 0.00,   # 0% — base price
    'xlm':  0.50,   # 50% off
    'opus': 0.60,   # 60% off
}

_price_cache = {'price': None, 'timestamp': 0}
CACHE_TTL = 300  # 5 minutes
FALLBACK_PRICE = 0.10  # conservative fallback if API fails


# ── Price calculation ─────────────────────────────────────────────

def get_tier_price(tier_key, payment_method='card', price_type='join'):
    """Return USD-equivalent price for a tier + payment method combo."""
    tier = TIERS[tier_key]
    base = tier[f'{price_type}_usd']
    discount = DISCOUNTS.get(payment_method, 0)
    return round(base * (1 - discount), 2)


def get_xlm_amount(tier_key, price_type='join'):
    """Return XLM amount for a tier (at current exchange rate)."""
    usd_price = get_tier_price(tier_key, 'xlm', price_type)
    xlm_rate = fetch_xlm_price()
    return round(usd_price / xlm_rate, 2) if xlm_rate > 0 else 0


# ── XLM price fetching ───────────────────────────────────────────

def fetch_xlm_price():
    now = time.time()
    if _price_cache['price'] and (now - _price_cache['timestamp']) < CACHE_TTL:
        return _price_cache['price']

    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "stellar", "vs_currencies": "usd"},
            timeout=10,
        )
        resp.raise_for_status()
        price = resp.json()["stellar"]["usd"]
    except Exception:
        if _price_cache['price']:
            return _price_cache['price']
        return FALLBACK_PRICE

    _price_cache['price'] = price
    _price_cache['timestamp'] = now
    return price


async def async_fetch_xlm_price():
    """Non-blocking XLM price fetch. Uses same cache as sync version."""
    now = time.time()
    if _price_cache['price'] and (now - _price_cache['timestamp']) < CACHE_TTL:
        return _price_cache['price']

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "stellar", "vs_currencies": "usd"},
            )
            resp.raise_for_status()
            price = resp.json()["stellar"]["usd"]
    except Exception:
        if _price_cache['price']:
            return _price_cache['price']
        return FALLBACK_PRICE

    _price_cache['price'] = price
    _price_cache['timestamp'] = now
    return price
