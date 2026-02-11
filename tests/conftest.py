import os
import asyncio

# Set test env vars before importing config
os.environ["BANKER_SECRET"] = "SCHSSYPRQH2IOW2YMJFP32NOL5WN56URHDAUTQGQRN22CJOVDIXJ6AZT"
os.environ["GUARDIAN_SECRET"] = "SDXOTD3THO6JUV26FHDG2A3M4DI6LJDFGENMKZORRSW4Y474OERE4UOU"
os.environ["STRIPE_SECRET_KEY"] = "sk_test_fake"
os.environ["STRIPE_PUBLISHABLE_KEY"] = "pk_test_fake"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_fake"
os.environ["MAILTRAP_API_TOKEN"] = "fake_token"
os.environ["APP_SECRET_KEY"] = "test-secret"
os.environ["DATABASE_PATH"] = "./data/test_collective.db"
os.environ["STELLAR_NETWORK"] = "testnet"

import pytest
import db


@pytest.fixture(autouse=True)
def setup_test_db():
    """Reset test database before each test (sync wrapper)."""
    db_path = db.DATABASE_PATH
    if os.path.exists(db_path):
        os.remove(db_path)
    asyncio.get_event_loop().run_until_complete(db.init_db())
    yield
    if os.path.exists(db_path):
        os.remove(db_path)
