"""Exact public-only fixtures shared by System Paper contract tests."""

import json
from datetime import datetime, timedelta, timezone

from crypto_quant.offline_paper import (
    OfflinePaperPlan,
    PublicPaperHttpResponse,
    capture_offline_paper,
    offline_paper_requests,
)


UTC = timezone.utc
DEFAULT_SCHEDULED_FOR = "2026-08-02T12:00:00.000Z"


def utc_text(value):
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def utc_value(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def kline_row(open_time, close):
    start_ms = int(open_time.timestamp() * 1000)
    return [
        start_ms,
        close,
        close,
        close,
        close,
        "10",
        start_ms + 14_400_000 - 1,
        "20000",
        20,
        "5",
        "10000",
        "0",
    ]


def warmup_body(scheduled_for, *, latest="110", prior="100"):
    boundary = utc_value(scheduled_for)
    first = boundary - timedelta(hours=4 * 22)
    rows = [
        kline_row(
            first + timedelta(hours=4 * index),
            prior if index < 21 else latest,
        )
        for index in range(22)
    ]
    return json.dumps(rows, separators=(",", ":")).encode("utf-8")


def exchange_info_body():
    return json.dumps(
        {
            "timezone": "UTC",
            "serverTime": 1785100000000,
            "rateLimits": [],
            "exchangeFilters": [],
            "symbols": [
                {
                    "symbol": "ETHUSDT",
                    "status": "TRADING",
                    "baseAsset": "ETH",
                    "baseAssetPrecision": 8,
                    "quoteAsset": "USDT",
                    "quotePrecision": 8,
                    "quoteAssetPrecision": 8,
                    "baseCommissionPrecision": 8,
                    "quoteCommissionPrecision": 8,
                    "orderTypes": [
                        "LIMIT",
                        "LIMIT_MAKER",
                        "MARKET",
                        "STOP_LOSS",
                        "STOP_LOSS_LIMIT",
                        "TAKE_PROFIT_LIMIT",
                    ],
                    "icebergAllowed": True,
                    "ocoAllowed": True,
                    "otoAllowed": True,
                    "quoteOrderQtyMarketAllowed": True,
                    "allowTrailingStop": True,
                    "cancelReplaceAllowed": True,
                    "amendAllowed": True,
                    "isSpotTradingAllowed": True,
                    "isMarginTradingAllowed": True,
                    "filters": [
                        {
                            "filterType": "PRICE_FILTER",
                            "minPrice": "0.01",
                            "maxPrice": "1000000",
                            "tickSize": "0.01",
                        },
                        {
                            "filterType": "LOT_SIZE",
                            "minQty": "0.0001",
                            "maxQty": "9000",
                            "stepSize": "0.0001",
                        },
                        {
                            "filterType": "MIN_NOTIONAL",
                            "minNotional": "5",
                            "applyToMarket": True,
                            "avgPriceMins": 5,
                        },
                        {
                            "filterType": "NOTIONAL",
                            "minNotional": "10",
                            "applyMinToMarket": True,
                            "maxNotional": "9000000",
                            "applyMaxToMarket": False,
                            "avgPriceMins": 5,
                        },
                    ],
                    "permissions": [],
                    "permissionSets": [["SPOT"]],
                    "defaultSelfTradePreventionMode": "EXPIRE_MAKER",
                    "allowedSelfTradePreventionModes": ["EXPIRE_MAKER"],
                }
            ],
            "sors": None,
        },
        separators=(",", ":"),
    ).encode("utf-8")


class FixturePaperTransport:
    """Specific four-response transport; production parsing remains real."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def get(self, request):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("unexpected fifth public request")
        return self.responses.pop(0)


def http_response(request, body, started_at, received_at):
    return PublicPaperHttpResponse(
        status=200,
        final_url=request.url,
        headers={"Date": "Sun, 02 Aug 2026 12:05:00 GMT"},
        body=body,
        request_started_at=utc_text(started_at),
        response_received_at=utc_text(received_at),
    )


def valid_public_transport(
    *,
    scheduled_for=DEFAULT_SCHEDULED_FOR,
    market_boundary_or_none=None,
    latest="110",
    prior="100",
    bid="109.99",
    ask="110.01",
    ask_quantity="10",
    recorded_at_or_none=None,
):
    plan = OfflinePaperPlan.create("ETHUSDT")
    requests = offline_paper_requests(plan)
    boundary = utc_value(scheduled_for)
    due = boundary + timedelta(minutes=5)
    responses = [
        http_response(
            requests[0],
            warmup_body(
                market_boundary_or_none or scheduled_for,
                latest=latest,
                prior=prior,
            ),
            due,
            due + timedelta(milliseconds=100),
        ),
        http_response(
            requests[1],
            exchange_info_body(),
            due + timedelta(milliseconds=110),
            due + timedelta(milliseconds=200),
        ),
        http_response(
            requests[2],
            json.dumps(
                {
                    "symbol": "ETHUSDT",
                    "bidPrice": bid,
                    "bidQty": "8",
                    "askPrice": ask,
                    "askQty": ask_quantity,
                },
                separators=(",", ":"),
            ).encode("utf-8"),
            due + timedelta(milliseconds=210),
            due + timedelta(milliseconds=250),
        ),
        http_response(
            requests[3],
            json.dumps(
                [
                    {
                        "a": 100,
                        "p": "110",
                        "q": "0.1",
                        "f": 200,
                        "l": 200,
                        "T": int(
                            (due + timedelta(milliseconds=230)).timestamp()
                            * 1000
                        ),
                        "m": False,
                        "M": True,
                    }
                ],
                separators=(",", ":"),
            ).encode("utf-8"),
            due + timedelta(milliseconds=260),
            due + timedelta(milliseconds=300),
        ),
    ]
    recorded_at = recorded_at_or_none or utc_text(due + timedelta(seconds=1))
    return FixturePaperTransport(responses), lambda: recorded_at


def valid_public_capture(
    *,
    scheduled_for=DEFAULT_SCHEDULED_FOR,
    market_boundary_or_none=None,
    latest="110",
    prior="100",
    bid="109.99",
    ask="110.01",
    ask_quantity="10",
    recorded_at_or_none=None,
):
    plan = OfflinePaperPlan.create("ETHUSDT")
    transport, clock = valid_public_transport(
        scheduled_for=scheduled_for,
        market_boundary_or_none=market_boundary_or_none,
        latest=latest,
        prior=prior,
        bid=bid,
        ask=ask,
        ask_quantity=ask_quantity,
        recorded_at_or_none=recorded_at_or_none,
    )
    capture = capture_offline_paper(
        plan,
        transport,
        recorded_at=clock,
    )
    return capture, transport
