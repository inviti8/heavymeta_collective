import time
from passlib.hash import argon2
from nicegui import app, ui
from email_validator import validate_email, EmailNotValidError
import db

# Rate limiting: {email: (fail_count, first_fail_timestamp)}
_login_attempts = {}
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 300  # 5 minutes


def hash_password(password):
    return argon2.hash(password)


def verify_password(password, password_hash):
    return argon2.verify(password, password_hash)


def _check_rate_limit(email):
    key = email.lower().strip()
    if key not in _login_attempts:
        return None
    count, first_fail = _login_attempts[key]
    if time.time() - first_fail > LOCKOUT_SECONDS:
        del _login_attempts[key]
        return None
    if count >= MAX_ATTEMPTS:
        remaining = int(LOCKOUT_SECONDS - (time.time() - first_fail))
        return f'Too many attempts. Try again in {remaining} seconds.'
    return None


def _record_failed_attempt(email):
    key = email.lower().strip()
    now = time.time()
    if key in _login_attempts:
        count, first_fail = _login_attempts[key]
        if now - first_fail > LOCKOUT_SECONDS:
            _login_attempts[key] = (1, now)
        else:
            _login_attempts[key] = (count + 1, first_fail)
    else:
        _login_attempts[key] = (1, now)


def _clear_attempts(email):
    key = email.lower().strip()
    _login_attempts.pop(key, None)


async def login_user(email, password):
    rate_error = _check_rate_limit(email)
    if rate_error:
        return None, rate_error

    user = await db.get_user_by_email(email)
    if not user:
        _record_failed_attempt(email)
        return None, None
    if not verify_password(password, user['password_hash']):
        _record_failed_attempt(email)
        return None, None

    _clear_attempts(email)
    return dict(user), None


def set_session(user):
    app.storage.user['authenticated'] = True
    app.storage.user['user_id'] = user['id']
    app.storage.user['moniker'] = user['moniker']
    app.storage.user['member_type'] = user['member_type']
    app.storage.user['email'] = user['email']


def clear_session():
    app.storage.user.clear()


def require_auth():
    if not app.storage.user.get('authenticated'):
        ui.navigate.to('/login')
        return False
    return True


def require_coop():
    if not require_auth():
        return False
    if app.storage.user.get('member_type') != 'coop':
        ui.navigate.to('/join')
        return False
    return True


async def validate_signup_form(moniker, email, password):
    errors = []
    if not moniker or not moniker.strip():
        errors.append('Moniker is required.')
    elif len(moniker) > 100:
        errors.append('Moniker must be 100 characters or fewer.')
    elif not await db.check_moniker_available(moniker.strip()):
        errors.append('That moniker is already taken.')

    if not email or not email.strip():
        errors.append('Email is required.')
    else:
        try:
            validate_email(email.strip(), check_deliverability=False)
        except EmailNotValidError:
            errors.append('Please enter a valid email address.')
        else:
            if not await db.check_email_available(email.strip()):
                errors.append('An account with that email already exists.')

    if not password:
        errors.append('Password is required.')
    elif len(password) < 8:
        errors.append('Password must be at least 8 characters.')

    return errors
