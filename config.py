import os
from dotenv import load_dotenv
from stellar_sdk import Keypair, Network
from hvym_stellar import Stellar25519KeyPair

load_dotenv()

# --- Stellar Keys (fail fast if missing) ---
BANKER_SECRET = os.environ["BANKER_SECRET"]
GUARDIAN_SECRET = os.environ["GUARDIAN_SECRET"]

BANKER_KP = Keypair.from_secret(BANKER_SECRET)
GUARDIAN_KP = Keypair.from_secret(GUARDIAN_SECRET)
BANKER_PUB = BANKER_KP.public_key
GUARDIAN_PUB = GUARDIAN_KP.public_key

BANKER_25519 = Stellar25519KeyPair(BANKER_KP)
GUARDIAN_25519 = Stellar25519KeyPair(GUARDIAN_KP)

# --- Stripe ---
STRIPE_SECRET_KEY = os.environ["STRIPE_SECRET_KEY"]
STRIPE_PUBLISHABLE_KEY = os.environ["STRIPE_PUBLISHABLE_KEY"]
STRIPE_WEBHOOK_SECRET = os.environ["STRIPE_WEBHOOK_SECRET"]

# --- Mailtrap ---
MAILTRAP_API_TOKEN = os.environ["MAILTRAP_API_TOKEN"]

# --- App ---
APP_SECRET_KEY = os.environ["APP_SECRET_KEY"]
DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/collective.db")

# --- Network ---
NET = os.getenv("STELLAR_NETWORK", "testnet")

NETWORK_CONFIG = {
    "testnet": {
        "horizon_url": "https://horizon-testnet.stellar.org",
        "rpc_url": "https://soroban-testnet.stellar.org",
        "passphrase": Network.TESTNET_NETWORK_PASSPHRASE,
        "explorer": "https://stellar.expert/explorer/testnet",
    },
    "mainnet": {
        "horizon_url": "https://horizon.stellar.org",
        "rpc_url": "https://soroban.stellar.org",
        "passphrase": Network.PUBLIC_NETWORK_PASSPHRASE,
        "explorer": "https://stellar.expert/explorer/public",
    },
}

HORIZON_URL = NETWORK_CONFIG[NET]["horizon_url"]
RPC_URL = NETWORK_CONFIG[NET]["rpc_url"]
NET_PW = NETWORK_CONFIG[NET]["passphrase"]
BLOCK_EXPLORER = NETWORK_CONFIG[NET]["explorer"]

# --- Contracts (testnet) ---
CONTRACTS = {
    "hvym_roster": "CDWX72R3Z7CAKWWBNKVNDLSUH5WZOC4CR7OOFJQANO2IX37S3IE4JRRO",
    "hvym_collective": "CAYD2PS5KR4VSEQPQZEUDF3KHT2NDWTGVXAHPPMLLS4HHM5ARUNALFUU",
    "opus_token": "CB3MM62JMDTNVJVOXORUOOPBFAWVTREJLA5VN4YME4MBNCHGBHQPQH7G",
    "hvym_pin_service": "CCEDYFIHUCJFITWEOT7BWUO2HBQQ72L244ZXQ4YNOC6FYRDN3MKDQFK7",
}
