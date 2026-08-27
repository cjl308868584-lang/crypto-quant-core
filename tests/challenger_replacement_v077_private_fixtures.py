from crypto_quant.canonical import canonical_json
from crypto_quant.challenger_replacement_binance_private_contract import (
    load_binance_private_activation_bytes,
)


def loaded_private_activation(*, build_identity, now, **changes):
    document = {
        "$schema": "./challenger-replacement-binance-private-activation-v1.schema.json",
        "schema_version": "1.0.0",
        "activation_id": "binance_private_activation_" + "5" * 64,
        "build_identity": dict(build_identity),
        "configuration_sha256": "6" * 64,
        "account_approval_sha256": "7" * 64,
        "block_id": "e0-block-" + "8" * 64,
        "stage": "E0",
        "capital_usdt": "100",
        "max_gross_exposure_usdt": "50",
        "max_leverage": "0.5",
        "expires_at": "2026-08-28T00:00:00.000Z",
        "production_activation": True,
    }
    document.update(changes)
    return load_binance_private_activation_bytes(
        (canonical_json(document) + "\n").encode("utf-8"),
        build_identity=build_identity,
        now=now,
    )
