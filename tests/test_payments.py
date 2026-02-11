import pytest
from payments.stellar_pay import create_stellar_payment_request, generate_stellar_qr


def test_create_stellar_payment_request():
    req = create_stellar_payment_request()
    assert 'order_id' in req
    assert 'memo' in req
    assert req['memo'].startswith('hvym-')
    assert 'qr' in req
    assert req['qr'].startswith('data:image/png;base64,')
    assert 'address' in req
    assert req['amount'] == '333'


def test_generate_stellar_qr():
    uri = "web+stellar:pay?destination=GTEST&amount=333"
    qr = generate_stellar_qr(uri)
    assert qr.startswith('data:image/png;base64,')
    assert len(qr) > 100


def test_payment_requests_unique():
    req1 = create_stellar_payment_request()
    req2 = create_stellar_payment_request()
    assert req1['order_id'] != req2['order_id']
    assert req1['memo'] != req2['memo']
