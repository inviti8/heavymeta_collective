import pytest
from unittest.mock import patch, MagicMock
from payments.pricing import (
    fetch_xlm_price, get_xlm_usd_equivalent, get_stripe_price_cents,
    get_stripe_price_display, XLM_COST, _price_cache,
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


@patch('payments.pricing.requests.get')
def test_get_xlm_usd_equivalent(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"stellar": {"usd": 0.20}}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    equiv = get_xlm_usd_equivalent()
    assert equiv == round(333 * 0.20, 2)


@patch('payments.pricing.requests.get')
def test_get_stripe_price_cents(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"stellar": {"usd": 0.15}}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    cents = get_stripe_price_cents()
    expected = int(333 * 0.15 * 2 * 100)
    assert cents == expected


@patch('payments.pricing.requests.get')
def test_get_stripe_price_display(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"stellar": {"usd": 0.15}}
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    display = get_stripe_price_display()
    assert display.startswith('$')
    assert '.' in display
