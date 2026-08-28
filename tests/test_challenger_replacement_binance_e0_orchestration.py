import unittest
from contextlib import contextmanager
import json
from types import SimpleNamespace
from unittest.mock import patch


class BinanceE0OrchestrationTests(unittest.TestCase):
    OPPORTUNITY = "ETHUSDT@2026-08-28T12:00:00.000Z"

    def test_missing_authority_fails_before_installed_state_or_network(self):
        from crypto_quant import challenger_replacement_binance_e0_orchestration as module
        @contextmanager
        def installed_sources():
            yield {"build_identity": {"release_tag": "v0.78.1"}}
        with patch.object(
            module, "_open_fixed_private_authority",
            side_effect=module.BinanceE0OrchestrationError(
                "BINANCE_E0_AUTHORITY_ARTIFACTS_REQUIRED"
            ),
        ), patch.object(module, "open_fixed_v3_installed_sources",
                        side_effect=installed_sources) as installed, \
                patch.object(module, "run_challenger_replacement_binance_private_intent") as runtime, \
                self.assertRaisesRegex(
                    module.BinanceE0OrchestrationError,
                    "BINANCE_E0_AUTHORITY_ARTIFACTS_REQUIRED",
                ):
            module.run_fixed_binance_private_opportunity(self.OPPORTUNITY)
        installed.assert_called_once()
        runtime.assert_not_called()

    def test_private_runtime_uses_only_fixed_installed_and_authority_sources(self):
        from crypto_quant import challenger_replacement_binance_e0_orchestration as module
        slot = {"stage": "OPPORTUNITY_OBSERVED"}
        state = SimpleNamespace(replay=lambda: {
            "opportunities": {self.OPPORTUNITY: slot},
        })
        root = object()
        build = {"release_tag": "v0.78.1"}
        activation = object()
        credential = object()
        preflight = object()

        @contextmanager
        def authority(_build):
            yield activation, credential, preflight

        @contextmanager
        def installed():
            yield {"state": state, "event_root": root,
                   "build_identity": build}

        intent = {"opportunity_id": self.OPPORTUNITY}
        expected = {"status": "TERMINAL_RECONCILED"}
        with patch.object(module, "_open_fixed_private_authority", authority), \
                patch.object(module, "open_fixed_v3_installed_sources", installed), \
                patch.object(module, "build_binance_order_intent_from_opportunity",
                             return_value=intent) as derive, \
                patch.object(module, "run_challenger_replacement_binance_private_intent",
                             return_value=expected) as runtime:
            self.assertEqual(
                module.run_fixed_binance_private_opportunity(self.OPPORTUNITY),
                expected,
            )
        derive.assert_called_once_with(
            slot=slot, activation=activation, attempt_ordinal=1,
        )
        runtime.assert_called_once_with(
            state=state, event_root=root, intent=intent,
            preflight_capability=preflight, activation=activation,
            credential=credential, build_identity=build,
        )

    def test_emergency_stop_is_fixed_to_existing_exposed_perpetual(self):
        from crypto_quant import challenger_replacement_binance_e0_orchestration as module
        private = {
            "product": "PERPETUAL", "action": "OPEN_SHORT",
            "stage": "BINANCE_ORDER_PARTIALLY_FILLED",
        }
        state = SimpleNamespace(replay=lambda: {
            "opportunities": {self.OPPORTUNITY: {
                "stage": "OPPORTUNITY_OBSERVED", "private": private,
            }},
        })
        build = {"release_tag": "v0.78.1"}
        activation = object()
        credential = SimpleNamespace(identity={"credential_id": "redacted"})
        preflight = SimpleNamespace(load=lambda **_kwargs: {"status": "OK"})
        attempt = {"opportunity_id": self.OPPORTUNITY}

        @contextmanager
        def authority(_build):
            yield activation, credential, preflight

        @contextmanager
        def installed():
            yield {"state": state, "event_root": object(),
                   "build_identity": build}

        position = SimpleNamespace(body=b'[{"positionAmt":"-0.1"}]')
        with patch.object(module, "_open_fixed_private_authority", authority), \
                patch.object(module, "open_fixed_v3_installed_sources", installed), \
                patch.object(module, "build_binance_order_intent_from_opportunity",
                             return_value={"opportunity_id": self.OPPORTUNITY}), \
                patch.object(module, "prepare_binance_order_attempt",
                             return_value=attempt), \
                patch.object(module, "_runtime_projection", return_value={}), \
                patch.object(module, "_query", return_value=position) as query, \
                patch.object(module, "_emergency_flatten",
                             return_value={"status": "FLAT"}) as flatten:
            result = module.run_fixed_binance_emergency_stop(self.OPPORTUNITY)
        self.assertEqual(result, {"status": "FLAT"})
        query.assert_called_once()
        self.assertEqual(query.call_args.args[:2], (
            "FUTURES_POSITION", {"symbol": "ETHUSDT"},
        ))
        flatten.assert_called_once_with(state, attempt, position.body,
                                        flatten.call_args.args[3])

    def test_account_preflight_uses_only_frozen_queries_and_redacted_output(self):
        from crypto_quant import challenger_replacement_binance_e0_orchestration as module
        build = {"release_tag": "v0.78.1"}
        activation = object()
        credential = SimpleNamespace(identity={"credential_id": "redacted"},
                                     close=lambda: None)

        @contextmanager
        def installed():
            yield {"build_identity": build}

        artifacts = iter((b"activation", b'{}', b"approval"))
        request_endpoints = []

        def build_request(endpoint, parameters, **_kwargs):
            request_endpoints.append((endpoint, parameters))
            return SimpleNamespace(endpoint_id=endpoint)

        response = SimpleNamespace(response_class="QUERY_SUCCEEDED",
                                   body=b"{}")
        receipt = {
            "status": "BINANCE_ACCOUNT_PREFLIGHT_VERIFIED_FLAT",
            "preflight_id": "binance_account_preflight_" + "a" * 64,
        }
        with patch.object(module, "open_fixed_v3_installed_sources", installed), \
                patch.object(module, "_open_directory",
                             return_value=(7, object())), \
                patch.object(module, "_read_published_exact",
                             side_effect=lambda *_args: (next(artifacts), object())), \
                patch.object(module, "load_binance_private_activation_bytes",
                             return_value=activation), \
                patch.object(module, "open_binance_credential_capability",
                             return_value=credential), \
                patch.object(module, "load_binance_account_approval_bytes",
                             return_value={}), \
                patch.object(module, "observe_binance_server_time",
                             return_value=SimpleNamespace(server_time_ms=1)), \
                patch.object(module, "build_binance_private_request",
                             side_effect=build_request), \
                patch.object(module, "execute_binance_private_request",
                             return_value=response), \
                patch.object(module, "evaluate_binance_account_preflight",
                             return_value=json.dumps(receipt).encode()), \
                patch.object(module, "_publish_contract_exact",
                             return_value=("PUBLISHED", object())), \
                patch.object(module, "_close_descriptor"):
            result = module.run_fixed_binance_account_preflight()

        self.assertEqual(
            set(endpoint for endpoint, _ in request_endpoints),
            set(module._PREFLIGHT_ENDPOINTS),
        )
        self.assertEqual(len(request_endpoints), len(module._PREFLIGHT_ENDPOINTS))
        self.assertEqual(result, {
            "status": "BINANCE_ACCOUNT_PREFLIGHT_VERIFIED_FLAT",
            "preflight_id": receipt["preflight_id"],
            "publication": "PUBLISHED",
        })
        self.assertNotIn("credential", result)


if __name__ == "__main__":
    unittest.main()
