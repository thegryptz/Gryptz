from __future__ import annotations

import os

import base58
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def generate_wallet() -> dict:
    seed = os.urandom(32)
    private_key_obj = Ed25519PrivateKey.from_private_bytes(seed)
    pubkey_bytes = private_key_obj.public_key().public_bytes_raw()
    keypair_bytes = seed + pubkey_bytes
    return {
        "address": base58.b58encode(pubkey_bytes).decode(),
        "private_key": base58.b58encode(keypair_bytes).decode(),
    }


def address_short(address: str) -> str:
    if len(address) > 10:
        return f"{address[:4]}...{address[-4:]}"
    return address
