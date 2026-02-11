import json
from stellar_sdk import Keypair, Server, TransactionBuilder, Network
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
