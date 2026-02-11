import pytest
from unittest.mock import patch, MagicMock
from stellar_sdk import Keypair


@patch('stellar_ops.server')
def test_fund_account_builds_tx(mock_server):
    from stellar_ops import fund_account

    mock_account = MagicMock()
    mock_account.sequence = 1
    mock_server.load_account.return_value = mock_account
    mock_server.submit_transaction.return_value = {'hash': 'abc123'}

    dest = Keypair.random().public_key
    result = fund_account(dest, amount="22")
    assert mock_server.load_account.called
    assert mock_server.submit_transaction.called
