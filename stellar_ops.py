import json
from stellar_sdk import Asset, Keypair, Server, TransactionBuilder, Network
from config import (
    BANKER_KP, BANKER_PUB, HORIZON_URL, NET_PW, NET,
    RPC_URL, CONTRACTS,
)

server = Server(horizon_url=HORIZON_URL)


def fund_account(destination_pub, amount="22"):
    banker_account = server.load_account(BANKER_PUB)
    tx = (
        TransactionBuilder(
            source_account=banker_account,
            network_passphrase=NET_PW,
            base_fee=100,
        )
        .append_create_account_op(destination=destination_pub, starting_balance=amount)
        .set_timeout(30)
        .build()
    )
    tx.sign(BANKER_KP)
    response = server.submit_transaction(tx)
    return response


def get_xlm_balance(address):
    """Query Horizon for the native XLM balance of an account.

    Returns balance string (e.g. '142.38') or None if account not found.
    """
    try:
        account = server.accounts().account_id(address).call()
        for b in account['balances']:
            if b['asset_type'] == 'native':
                return b['balance']
    except Exception:
        return None
    return None


def send_xlm(source_kp, destination, amount, memo=None):
    """Build, sign, and submit an XLM payment transaction.

    Returns the Horizon response dict (contains 'hash') on success.
    Raises on failure.
    """
    source_account = server.load_account(source_kp.public_key)
    builder = (
        TransactionBuilder(
            source_account=source_account,
            network_passphrase=NET_PW,
            base_fee=100,
        )
        .append_payment_op(
            destination=destination,
            asset=Asset.native(),
            amount=str(amount),
        )
        .set_timeout(30)
    )
    if memo:
        builder.add_text_memo(memo)
    tx = builder.build()
    tx.sign(source_kp)
    return server.submit_transaction(tx)


def register_on_roster(user_keys, moniker):
    from bindings.hvym_roster import Client as RosterClient

    client = RosterClient(
        contract_id=CONTRACTS["hvym_roster"],
        rpc_url=RPC_URL,
    )
    canon_data = json.dumps({"type": "coop_member"}).encode()
    tx = client.join(
        caller=user_keys.public_key,
        name=moniker.encode(),
        canon=canon_data,
        source=user_keys.public_key,
        signer=user_keys,
    )
    tx.simulate()
    return tx.sign_and_submit()
