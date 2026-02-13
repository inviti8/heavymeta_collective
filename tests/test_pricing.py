import pytest
from unittest.mock import patch, MagicMock
from payments.pricing import (
    fetch_xlm_price, get_tier_price, get_xlm_amount,
    TIERS, DISCOUNTS, _price_cache,
)


@pytest.fixture(autouse=True)
def reset_cache():
    _price_cache['price'] = None
    _price_cache['timestamp'] = 0
    yield


@patch('payments.pricing.requests.get')
def test_fetch_xlm_price(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"stellar": {"usd": 0.15}}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    price = fetch_xlm_price()
    assert price == 0.15


@patch('payments.pricing.requests.get')
def test_fetch_xlm_price_fallback(mock_get):
    mock_get.side_effect = Exception("API down")
    price = fetch_xlm_price()
    assert price == 0.10  # fallback


def test_get_tier_price_card():
    # Card = base price, no discount
    assert get_tier_price('forge', 'card', 'join') == 59.99
    assert get_tier_price('spark', 'card', 'join') == 29.99
    assert get_tier_price('free', 'card', 'join') == 0


def test_get_tier_price_xlm():
    # XLM = 50% off
    assert get_tier_price('forge', 'xlm', 'join') == 30.0
    assert get_tier_price('spark', 'xlm', 'join') == 14.99


def test_get_tier_price_opus():
    # OPUS = 60% off
    assert get_tier_price('forge', 'opus', 'join') == 24.0
    assert get_tier_price('anvil', 'opus', 'join') == 60.0


@patch('payments.pricing.requests.get')
def test_get_xlm_amount(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"stellar": {"usd": 0.20}}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    xlm = get_xlm_amount('forge', 'join')
    # forge XLM price = 59.99 * 0.5 = 30.00, at $0.20/XLM = 150 XLM
    assert xlm == 150.0


def test_tiers_dict():
    assert 'free' in TIERS
    assert 'spark' in TIERS
    assert 'forge' in TIERS
    assert 'founding_forge' in TIERS
    assert 'anvil' in TIERS
    assert TIERS['free']['join_usd'] == 0


def test_discounts_dict():
    assert DISCOUNTS['card'] == 0.0
    assert DISCOUNTS['xlm'] == 0.50
    assert DISCOUNTS['opus'] == 0.60
