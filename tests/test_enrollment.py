import pytest
from unittest.mock import patch
from enrollment import process_free_enrollment
import db


@pytest.mark.asyncio
@patch('enrollment.send_welcome_email')
async def test_free_enrollment(mock_email):
    user_id = await process_free_enrollment('testuser', 'test@example.com', 'password123')
    assert user_id is not None

    user = await db.get_user_by_id(user_id)
    assert user is not None
    assert user['moniker'] == 'testuser'
    assert user['email'] == 'test@example.com'
    assert user['member_type'] == 'free'
    assert user['stellar_address'] is None
    assert user['password_hash'] is not None
    assert user['password_hash'] != 'password123'


@pytest.mark.asyncio
@patch('enrollment.send_welcome_email')
async def test_free_enrollment_creates_unique_ids(mock_email):
    id1 = await process_free_enrollment('user1', 'user1@example.com', 'password123')
    id2 = await process_free_enrollment('user2', 'user2@example.com', 'password123')
    assert id1 != id2
