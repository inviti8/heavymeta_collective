import json
import os
import time
import requests
import httpx

# ── Tier definitions ──────────────────────────────────────────────
# Loaded from static/tiers.json — single source of truth.
# Prices are in USD. XLM/OPUS amounts calculated at runtime from live rates.
# "join" = one-time enrollment fee. "annual" = yearly renewal.

_TIERS_JSON = os.path.join(os.path.dirname(__file__), '..', 'static', 'tiers.json')
with open(_TIERS_JSON, 'r') as _f:
    TIERS = {t['key']: t for t in json.load(_f)}

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
