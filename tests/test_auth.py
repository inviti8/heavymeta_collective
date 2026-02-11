import pytest
from auth import hash_password, verify_password, validate_signup_form
import db


def test_hash_and_verify():
    pw = "testpassword123"
    hashed = hash_password(pw)
    assert hashed != pw
    assert verify_password(pw, hashed)
    assert not verify_password("wrong", hashed)


@pytest.mark.asyncio
async def test_validate_signup_empty_fields():
    errors = await validate_signup_form('', '', '')
    assert len(errors) >= 3  # moniker, email, password


@pytest.mark.asyncio
async def test_validate_signup_short_password():
    errors = await validate_signup_form('testuser', 'test@example.com', 'short')
    assert any('8 characters' in e for e in errors)


@pytest.mark.asyncio
async def test_validate_signup_invalid_email():
    errors = await validate_signup_form('testuser', 'not-an-email', 'password123')
    assert any('valid email' in e for e in errors)


@pytest.mark.asyncio
async def test_validate_signup_valid():
    errors = await validate_signup_form('testuser', 'test@example.com', 'password123')
    assert errors == []


@pytest.mark.asyncio
async def test_validate_signup_duplicate_moniker():
    await db.create_user(
        email='existing@example.com',
        moniker='taken',
        member_type='free',
        password_hash=hash_password('password123'),
    )
    errors = await validate_signup_form('taken', 'new@example.com', 'password123')
    assert any('taken' in e.lower() for e in errors)


@pytest.mark.asyncio
async def test_validate_signup_duplicate_email():
    await db.create_user(
        email='existing@example.com',
        moniker='existinguser',
        member_type='free',
        password_hash=hash_password('password123'),
    )
    errors = await validate_signup_form('newuser', 'existing@example.com', 'password123')
    assert any('already exists' in e for e in errors)
