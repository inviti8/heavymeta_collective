import time
import requests
import httpx

XLM_COST = 333
_price_cache = {'price': None, 'timestamp': 0}
CACHE_TTL = 300  # 5 minutes
FALLBACK_PRICE = 0.10  # conservative fallback if API fails


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


def get_xlm_usd_equivalent():
    return round(XLM_COST * fetch_xlm_price(), 2)


def get_stripe_price_cents():
    xlm_usd = fetch_xlm_price()
    stripe_usd = XLM_COST * xlm_usd * 2
    return int(stripe_usd * 100)


def get_stripe_price_display():
    cents = get_stripe_price_cents()
    return f"${cents / 100:.2f}"


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


async def async_get_xlm_usd_equivalent():
    return round(XLM_COST * await async_fetch_xlm_price(), 2)


async def async_get_stripe_price_cents():
    xlm_usd = await async_fetch_xlm_price()
    stripe_usd = XLM_COST * xlm_usd * 2
    return int(stripe_usd * 100)


async def async_get_stripe_price_display():
    cents = await async_get_stripe_price_cents()
    return f"${cents / 100:.2f}"
