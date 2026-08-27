"""Pure strict evaluation of frozen Binance account-preflight responses."""
from decimal import Decimal, InvalidOperation
import hashlib, ipaddress, json, os, stat
from pathlib import Path
from types import MappingProxyType
from typing import Mapping
from .canonical import canonical_json
from .challenger_replacement_binance_credential import BinanceCredentialIdentity
from .challenger_replacement_binance_private_contract import (
    BinanceAccountApproval, BinancePrivateActivation, _canonical_time,
    _is_loaded_binance_private_activation, _validator, load_binance_account_approval_bytes,
)
_ENDPOINTS = frozenset("API_RESTRICTIONS API_TRADING_STATUS SPOT_ACCOUNT SPOT_OPEN_ORDERS FUTURES_POSITION_MODE FUTURES_MULTI_ASSET_MODE FUTURES_SYMBOL_CONFIG FUTURES_ACCOUNT FUTURES_POSITION FUTURES_OPEN_ORDERS FUTURES_OPEN_ALGO_ORDERS".split())
_HASHES = frozenset("0123456789abcdef")
_PERMISSION_KEYS = frozenset("ipRestrict createTime enableReading enableWithdrawals enableInternalTransfer enableMargin enableFutures permitsUniversalTransfer enableVanillaOptions enableFixApiTrade enableFixReadOnly enableSpotAndMarginTrading enablePortfolioMarginTrading".split())
_SPOT_KEYS = frozenset("makerCommission takerCommission buyerCommission sellerCommission commissionRates canTrade canWithdraw canDeposit brokered requireSelfTradePrevention preventSor updateTime accountType balances permissions uid".split())
_FUTURES_ACCOUNT_KEYS = frozenset("totalInitialMargin totalMaintMargin totalWalletBalance totalUnrealizedProfit totalMarginBalance totalPositionInitialMargin totalOpenOrderInitialMargin totalCrossWalletBalance totalCrossUnPnl availableBalance maxWithdrawAmount assets positions".split())
_FUTURES_ASSET_KEYS = frozenset("asset walletBalance unrealizedProfit marginBalance maintMargin initialMargin positionInitialMargin openOrderInitialMargin crossWalletBalance crossUnPnl availableBalance maxWithdrawAmount updateTime".split())
_POSITION_KEYS = frozenset("symbol positionSide positionAmt entryPrice breakEvenPrice markPrice unRealizedProfit liquidationPrice isolatedMargin notional marginAsset isolatedWallet initialMargin maintMargin positionInitialMargin openOrderInitialMargin adl bidNotional askNotional updateTime".split())
_PERMISSIONS = {"ip_restricted": True, "read": True, "spot_trade": True, "futures_trade": True, "withdraw": False, "transfer": False, "margin": False}
_FLATNESS = {"spot_open_orders": 0, "futures_open_orders": 0, "futures_open_algo_orders": 0, "futures_positions": 0, "non_usdt_spot_exposure": "0"}
_COUNTS = {"network_requests": 0, "mutating_requests": 0, "orders": 0, "fund_movements": 0, "state_writes": 0}
_CAPABILITY_TOKEN = object()
class BinanceAccountPreflightError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code); self.reason_code = reason_code
def _fail(reason, error=None):
    failure = BinanceAccountPreflightError(reason)
    if error is None: raise failure
    raise failure from error
def _strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result: _fail("BINANCE_ACCOUNT_PREFLIGHT_INPUT_INVALID")
        result[key] = value
    return result
def _parse_responses(responses):
    if not isinstance(responses, Mapping) or frozenset(responses) != _ENDPOINTS:
        _fail("BINANCE_ACCOUNT_PREFLIGHT_INPUT_INVALID")
    parsed, hashes = {}, {}
    try:
        for name in sorted(_ENDPOINTS):
            body = responses[name]
            if not isinstance(body, bytes) or not 1 <= len(body) <= 1_048_576:
                _fail("BINANCE_ACCOUNT_PREFLIGHT_INPUT_INVALID")
            parsed[name] = json.loads(body.decode("utf-8"), object_pairs_hook=_strict_pairs)
            hashes[name] = hashlib.sha256(body).hexdigest()
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
        _fail("BINANCE_ACCOUNT_PREFLIGHT_INPUT_INVALID", error)
    return parsed, hashes
def _keys(value, expected, reason="BINANCE_ACCOUNT_PREFLIGHT_INPUT_INVALID"):
    if not isinstance(value, dict) or frozenset(value) != expected: _fail(reason)
    return value
def _number(value, reason="BINANCE_ACCOUNT_PREFLIGHT_INPUT_INVALID"):
    if not isinstance(value, str): _fail(reason)
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        _fail(reason, error)
    if not number.is_finite(): _fail(reason)
    return number
def _hash(value, length=64):
    return (isinstance(value, str) and len(value) == length
            and not set(value) - _HASHES)
def _ipv4(value):
    try: address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.version == 4 and str(address) == value
def _require_permissions(document):
    value = _keys(document["API_RESTRICTIONS"], _PERMISSION_KEYS)
    if (isinstance(value["createTime"], bool) or not isinstance(value["createTime"], int)
            or not 0 <= value["createTime"] <= (1 << 53) - 1 or any(not isinstance(item, bool) for key, item in value.items() if key != "createTime")):
        _fail("BINANCE_ACCOUNT_PREFLIGHT_INPUT_INVALID")
    required_true = {"ipRestrict", "enableReading", "enableFutures", "enableSpotAndMarginTrading"}
    if any(value[key] is not True for key in required_true) or any(value[key] is not False for key in _PERMISSION_KEYS - required_true - {"createTime"}):
        _fail("BINANCE_ACCOUNT_PREFLIGHT_PERMISSION_BLOCKED")
    status = _keys(document["API_TRADING_STATUS"], {"data"})["data"]
    status = _keys(status, {"isLocked", "plannedRecoverTime", "triggerCondition", "updateTime"})
    _keys(status["triggerCondition"], {"GCR", "IFER", "UFR"})
    if status["isLocked"] is not False: _fail("BINANCE_ACCOUNT_PREFLIGHT_ACCOUNT_LOCKED")
    if any(isinstance(status[key], bool) or not isinstance(status[key], int) for key in ("plannedRecoverTime", "updateTime")) or any(isinstance(value, bool) or not isinstance(value, int) for value in status["triggerCondition"].values()):
        _fail("BINANCE_ACCOUNT_PREFLIGHT_INPUT_INVALID")
    return value
def _require_configuration(document):
    position_mode = _keys(document["FUTURES_POSITION_MODE"], {"dualSidePosition"})
    asset_mode = _keys(document["FUTURES_MULTI_ASSET_MODE"], {"multiAssetsMargin"})
    config = document["FUTURES_SYMBOL_CONFIG"]
    if not isinstance(config, list) or len(config) != 1: _fail("BINANCE_ACCOUNT_PREFLIGHT_CONFIGURATION_BLOCKED")
    symbol = _keys(config[0], {"symbol", "marginType", "isAutoAddMargin", "leverage", "maxNotionalValue"})
    if (position_mode["dualSidePosition"] is not False or asset_mode["multiAssetsMargin"] is not False
            or symbol["symbol"] != "ETHUSDT" or symbol["marginType"] != "ISOLATED"
            or symbol["isAutoAddMargin"] is not False or isinstance(symbol["leverage"], bool)
            or symbol["leverage"] not in (1, 2) or _number(symbol["maxNotionalValue"]) <= 0):
        _fail("BINANCE_ACCOUNT_PREFLIGHT_CONFIGURATION_BLOCKED")
    return {"position_mode": "ONE_WAY", "asset_mode": "SINGLE_ASSET", "symbol": "ETHUSDT", "margin_type": "ISOLATED", "leverage": symbol["leverage"], "auto_add_margin": False}
def _require_spot_flat(document):
    account = _keys(document["SPOT_ACCOUNT"], _SPOT_KEYS)
    rates = _keys(account["commissionRates"], {"maker", "taker", "buyer", "seller"})
    integer_fields = {"makerCommission", "takerCommission", "buyerCommission", "sellerCommission", "updateTime", "uid"}
    boolean_fields = {"canTrade", "canWithdraw", "canDeposit", "brokered", "requireSelfTradePrevention", "preventSor"}
    if (any(isinstance(account[key], bool) or not isinstance(account[key], int) or account[key] < 0 for key in integer_fields)
            or any(not isinstance(account[key], bool) for key in boolean_fields) or any(_number(value) < 0 for value in rates.values())):
        _fail("BINANCE_ACCOUNT_PREFLIGHT_INPUT_INVALID")
    if account["canTrade"] is not True or account["accountType"] != "SPOT" or account["permissions"] != ["SPOT"] or account["uid"] <= 0:
        _fail("BINANCE_ACCOUNT_PREFLIGHT_PERMISSION_BLOCKED")
    balances = account["balances"]
    if not isinstance(balances, list) or not balances: _fail("BINANCE_ACCOUNT_PREFLIGHT_INPUT_INVALID")
    seen = set()
    for balance in balances:
        balance = _keys(balance, {"asset", "free", "locked"})
        if not isinstance(balance["asset"], str) or balance["asset"] in seen: _fail("BINANCE_ACCOUNT_PREFLIGHT_INPUT_INVALID")
        seen.add(balance["asset"])
        free, locked = _number(balance["free"]), _number(balance["locked"])
        if free < 0 or locked < 0: _fail("BINANCE_ACCOUNT_PREFLIGHT_INPUT_INVALID")
        if ((balance["asset"] != "USDT" and (free != 0 or locked != 0))
                or (balance["asset"] == "USDT" and locked != 0)):
            _fail("BINANCE_ACCOUNT_PREFLIGHT_NOT_FLAT")
    if not {"ETH", "USDT"}.issubset(seen) or document["SPOT_OPEN_ORDERS"] != []:
        _fail("BINANCE_ACCOUNT_PREFLIGHT_NOT_FLAT")
    return account
def _require_futures_flat(document):
    account = _keys(document["FUTURES_ACCOUNT"], _FUTURES_ACCOUNT_KEYS)
    zero_fields = {"totalInitialMargin", "totalMaintMargin", "totalUnrealizedProfit", "totalPositionInitialMargin", "totalOpenOrderInitialMargin", "totalCrossWalletBalance", "totalCrossUnPnl"}
    numeric = _FUTURES_ACCOUNT_KEYS - {"assets", "positions"}
    values = {key: _number(account[key]) for key in numeric}
    if any(value < 0 for value in values.values()): _fail("BINANCE_ACCOUNT_PREFLIGHT_INPUT_INVALID")
    if any(values[key] != 0 for key in zero_fields) or account["positions"] != []:
        _fail("BINANCE_ACCOUNT_PREFLIGHT_NOT_FLAT")
    if not isinstance(account["assets"], list) or len(account["assets"]) != 1: _fail("BINANCE_ACCOUNT_PREFLIGHT_INPUT_INVALID")
    for asset in account["assets"]:
        _keys(asset, _FUTURES_ASSET_KEYS)
        asset_numbers = _FUTURES_ASSET_KEYS - {"asset", "updateTime"}
        parsed = {key: _number(asset[key]) for key in asset_numbers}
        if not isinstance(asset["updateTime"], int) or isinstance(asset["updateTime"], bool) or any(value < 0 for value in parsed.values()):
            _fail("BINANCE_ACCOUNT_PREFLIGHT_INPUT_INVALID")
        if asset["asset"] != "USDT" or any(parsed[key] != 0 for key in {"unrealizedProfit", "maintMargin", "initialMargin", "positionInitialMargin", "openOrderInitialMargin", "crossWalletBalance", "crossUnPnl"}):
            _fail("BINANCE_ACCOUNT_PREFLIGHT_NOT_FLAT")
    positions = document["FUTURES_POSITION"]
    if not isinstance(positions, list) or len(positions) != 1: _fail("BINANCE_ACCOUNT_PREFLIGHT_INPUT_INVALID")
    position = _keys(positions[0], _POSITION_KEYS)
    position_numbers = _POSITION_KEYS - {"symbol", "positionSide", "marginAsset", "adl", "updateTime"}
    parsed_position = {key: _number(position[key]) for key in position_numbers}
    if (position["symbol"] != "ETHUSDT" or position["positionSide"] != "BOTH" or position["marginAsset"] != "USDT"
            or any(isinstance(position[key], bool) or not isinstance(position[key], int) for key in ("adl", "updateTime"))
            or any(parsed_position[key] != 0 for key in {"positionAmt", "unRealizedProfit", "isolatedMargin", "notional", "isolatedWallet", "initialMargin", "maintMargin", "positionInitialMargin", "openOrderInitialMargin", "bidNotional", "askNotional"})):
        _fail("BINANCE_ACCOUNT_PREFLIGHT_NOT_FLAT")
    if document["FUTURES_OPEN_ORDERS"] != [] or document["FUTURES_OPEN_ALGO_ORDERS"] != []:
        _fail("BINANCE_ACCOUNT_PREFLIGHT_NOT_FLAT")
def _require_approval(approval, credential_identity, permission, spot, now):
    if not isinstance(approval, BinanceAccountApproval) or not isinstance(credential_identity, BinanceCredentialIdentity):
        _fail("BINANCE_ACCOUNT_PREFLIGHT_APPROVAL_INVALID")
    identity_numbers = (credential_identity.device, credential_identity.inode, credential_identity.owner_uid, credential_identity.mtime_ns, credential_identity.ctime_ns)
    if (any(isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= (1 << 53) - 1 for value in identity_numbers)
            or credential_identity.inode <= 0 or not _hash(credential_identity.file_sha256) or not _hash(credential_identity.key_fingerprint)):
        _fail("BINANCE_ACCOUNT_PREFLIGHT_APPROVAL_INVALID")
    document = {
        "$schema": "./challenger-replacement-binance-account-approval-v1.schema.json",
        "schema_version": "1.0.0", **approval.__dict__,
    }
    try: loaded = load_binance_account_approval_bytes((canonical_json(document) + "\n").encode(), now=now)
    except ValueError as error:
        _fail("BINANCE_ACCOUNT_PREFLIGHT_APPROVAL_INVALID", error)
    account_hash = hashlib.sha256(canonical_json({"api_key_create_time": permission["createTime"], "spot_uid": spot["uid"], "venue": "BINANCE"}).encode()).hexdigest()
    if (loaded != approval or approval.key_fingerprint != credential_identity.key_fingerprint
            or approval.reviewer_uid != credential_identity.owner_uid
            or approval.account_identity_sha256 != account_hash):
        _fail("BINANCE_ACCOUNT_PREFLIGHT_APPROVAL_INVALID")
def _identity(document):
    core = dict(document); core.pop("preflight_id", None)
    return "binance_account_preflight_" + hashlib.sha256(
        canonical_json(core).encode()
    ).hexdigest()
def _file_identity(value):
    return (value.st_dev, value.st_ino, value.st_uid, value.st_mode,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
def _flag(name):
    value = getattr(os, name, None)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None
def _read_exact(descriptor, size):
    body = bytearray()
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        while len(body) < size:
            try: chunk = os.read(descriptor, min(4096, size - len(body)))
            except InterruptedError: continue
            if not chunk: break
            body.extend(chunk)
        if len(body) != size or os.read(descriptor, 1): raise OSError
        return bytes(body)
    except OSError as error: _fail("BINANCE_ACCOUNT_PREFLIGHT_FILE_UNTRUSTED", error)
class BinanceAccountPreflightCapability:
    __slots__ = ("_path", "_parent_fd", "_file_fd", "_parent_stat",
                 "_file_stat", "_build", "_closed")
    def __init__(self, values, token):
        if token is not _CAPABILITY_TOKEN:
            raise TypeError("BinanceAccountPreflightCapability is loader-issued")
        (self._path, self._parent_fd, self._file_fd, self._parent_stat,
         self._file_stat, self._build) = values
        self._closed = False
    def _validate(self):
        if self._closed: _fail("BINANCE_ACCOUNT_PREFLIGHT_CAPABILITY_CLOSED")
        try:
            current = (os.fstat(self._parent_fd),
                       os.stat(self._path.parent, follow_symlinks=False),
                       os.fstat(self._file_fd), os.stat(
                           self._path.name, dir_fd=self._parent_fd,
                           follow_symlinks=False))
        except OSError as error:
            _fail("BINANCE_ACCOUNT_PREFLIGHT_ATTACHMENT_CHANGED", error)
        expected = (self._parent_stat, self._parent_stat,
                    self._file_stat, self._file_stat)
        if any(_file_identity(a) != _file_identity(b)
               for a, b in zip(current, expected)):
            _fail("BINANCE_ACCOUNT_PREFLIGHT_ATTACHMENT_CHANGED")
    def load(self, *, activation, credential_identity, now):
        self._validate()
        try:
            data = _read_exact(self._file_fd, self._file_stat.st_size)
            document = load_binance_account_preflight_bytes(
                data, build_identity=self._build)
            self._validate()
            if (not _is_loaded_binance_private_activation(activation)
                    or not isinstance(credential_identity, BinanceCredentialIdentity)
                    or activation.production_activation is not True
                    or document["build_identity"] != dict(activation.build_identity)
                    or document["account_approval_sha256"] != activation.account_approval_sha256
                    or document["configuration_sha256"] != activation.configuration_sha256
                    or document["account_approval"]["key_fingerprint"] != credential_identity.key_fingerprint
                    or _canonical_time(document["expires_at"]) <= _canonical_time(now)
                    or _canonical_time(activation.expires_at) <= _canonical_time(now)
                    or _canonical_time(activation.expires_at) > _canonical_time(document["expires_at"])):
                raise ValueError
            return document
        except BinanceAccountPreflightError:
            raise
        except (KeyError, TypeError, ValueError) as error:
            _fail("BINANCE_ACCOUNT_PREFLIGHT_AUTHORITY_INVALID", error)
    def close(self):
        if self._closed: return
        self._closed = True; failure = None
        for descriptor in (self._file_fd, self._parent_fd):
            try: os.close(descriptor)
            except OSError as error: failure = failure or error
        self._file_fd = self._parent_fd = -1
        if failure is not None: _fail("BINANCE_ACCOUNT_PREFLIGHT_CLOSE_FAILED", failure)
    def __enter__(self): self._validate(); return self
    def __exit__(self, *_args): self.close()
    def __repr__(self): return "BinanceAccountPreflightCapability(redacted=True)"
def evaluate_binance_account_preflight(*, responses, account_approval,
                                        credential_identity, build_identity, now):
    parsed, hashes = _parse_responses(responses)
    permission = _require_permissions(parsed)
    configuration = _require_configuration(parsed)
    spot = _require_spot_flat(parsed)
    _require_futures_flat(parsed)
    _require_approval(account_approval, credential_identity, permission, spot, now)
    approval_bytes = (canonical_json({
        "$schema": "./challenger-replacement-binance-account-approval-v1.schema.json",
        "schema_version": "1.0.0", **account_approval.__dict__,
    }) + "\n").encode("utf-8")
    document = {
        "$schema": "./challenger-replacement-binance-account-preflight-v1.schema.json",
        "schema_version": "1.0.0",
        "status": "BINANCE_ACCOUNT_PREFLIGHT_VERIFIED_FLAT",
        "observed_at": now,
        "expires_at": account_approval.expires_at,
        "build_identity": dict(build_identity),
        "account_approval_sha256": hashlib.sha256(approval_bytes).hexdigest(),
        "account_approval": {
            "account_identity_sha256": account_approval.account_identity_sha256,
            "key_fingerprint": account_approval.key_fingerprint,
            "reviewed_egress_ip_attestation": account_approval.reviewed_egress_ip,
            "reviewer_uid": account_approval.reviewer_uid,
        },
        "permissions": _PERMISSIONS,
        "configuration": configuration,
        "configuration_sha256": hashlib.sha256(
            canonical_json(configuration).encode("utf-8")
        ).hexdigest(),
        "flatness": _FLATNESS,
        "response_sha256": hashes,
        "authority_counts": _COUNTS,
    }
    document["preflight_id"] = _identity(document)
    if tuple(_validator(
        "challenger-replacement-binance-account-preflight-v1.schema.json"
    ).iter_errors(document)):
        _fail("BINANCE_ACCOUNT_PREFLIGHT_INPUT_INVALID")
    return (canonical_json(document) + "\n").encode("utf-8")
def load_binance_account_preflight_bytes(data, *, build_identity):
    try:
        if not isinstance(data, bytes) or not data.endswith(b"\n"):
            raise ValueError
        document = json.loads(data[:-1].decode("utf-8"), object_pairs_hook=_strict_pairs)
        if ((canonical_json(document) + "\n").encode() != data
                or tuple(_validator(
                    "challenger-replacement-binance-account-preflight-v1.schema.json"
                ).iter_errors(document))
                or document["build_identity"] != build_identity
                or document["preflight_id"] != _identity(document)):
            raise ValueError
        if not _ipv4(document["account_approval"][
            "reviewed_egress_ip_attestation"
        ]):
            raise ValueError
        _canonical_time(document["observed_at"])
        return MappingProxyType({key: MappingProxyType(value) if isinstance(value, dict) else value for key, value in document.items()})
    except (KeyError, TypeError, UnicodeDecodeError, ValueError) as error:
        if isinstance(error, BinanceAccountPreflightError):
            raise
        _fail("BINANCE_ACCOUNT_PREFLIGHT_ARTIFACT_INVALID", error)
def open_binance_account_preflight_capability(*, reference_bytes,
                                                expected_uid, build_identity):
    keys = frozenset({"schema_version", "absolute_path", "parent_device",
                      "parent_inode", "file_device", "file_inode", "file_sha256"})
    flags = tuple(_flag(name) for name in
                  ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK"))
    parent_fd = file_fd = -1; primary = None
    try:
        if any(value is None for value in flags):
            _fail("BINANCE_ACCOUNT_PREFLIGHT_PLATFORM_UNSUPPORTED")
        if (not isinstance(reference_bytes, bytes)
                or not reference_bytes.endswith(b"\n")
                or isinstance(expected_uid, bool) or expected_uid != os.getuid()):
            raise ValueError
        reference = json.loads(reference_bytes[:-1].decode("utf-8"),
                               object_pairs_hook=_strict_pairs)
        numbers = tuple(reference.get(key) for key in
                        ("parent_device", "parent_inode", "file_device", "file_inode"))
        path = Path(reference.get("absolute_path", ""))
        if (frozenset(reference) != keys or reference["schema_version"] != "1.0.0"
                or (canonical_json(reference) + "\n").encode() != reference_bytes
                or not path.is_absolute() or path.name in ("", ".", "..")
                or any(isinstance(value, bool) or not isinstance(value, int)
                       or not 0 <= value <= (1 << 53) - 1 for value in numbers)
                or numbers[1] <= 0 or numbers[3] <= 0
                or not _hash(reference["file_sha256"])):
            raise ValueError
        nofollow, directory, nonblock = flags
        parent_fd = os.open(path.parent, os.O_RDONLY | nofollow | directory | nonblock)
        parent = os.fstat(parent_fd)
        attached_parent = os.stat(path.parent, follow_symlinks=False)
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != expected_uid
                or stat.S_IMODE(parent.st_mode) != 0o700
                or (parent.st_dev, parent.st_ino) != numbers[:2]
                or _file_identity(parent) != _file_identity(attached_parent)):
            _fail("BINANCE_ACCOUNT_PREFLIGHT_PARENT_CHANGED")
        file_fd = os.open(path.name, os.O_RDONLY | nofollow | nonblock,
                          dir_fd=parent_fd)
        opened = os.fstat(file_fd)
        attached = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_uid != expected_uid
                or stat.S_IMODE(opened.st_mode) != 0o600 or opened.st_nlink != 1
                or not 1 <= opened.st_size <= 1_048_576
                or (opened.st_dev, opened.st_ino) != numbers[2:]
                or _file_identity(opened) != _file_identity(attached)):
            _fail("BINANCE_ACCOUNT_PREFLIGHT_FILE_UNTRUSTED")
        data = _read_exact(file_fd, opened.st_size)
        if (hashlib.sha256(data).hexdigest() != reference["file_sha256"]
                or _file_identity(opened) != _file_identity(os.fstat(file_fd))):
            _fail("BINANCE_ACCOUNT_PREFLIGHT_FILE_UNTRUSTED")
        load_binance_account_preflight_bytes(data, build_identity=build_identity)
        result = BinanceAccountPreflightCapability(
            (path, parent_fd, file_fd, parent, opened, dict(build_identity)),
            _CAPABILITY_TOKEN)
        parent_fd = file_fd = -1
        return result
    except BinanceAccountPreflightError as error:
        primary = error; raise
    except (KeyError, TypeError, UnicodeDecodeError, ValueError, OSError) as error:
        primary = BinanceAccountPreflightError(
            "BINANCE_ACCOUNT_PREFLIGHT_REFERENCE_INVALID")
        raise primary from error
    finally:
        for descriptor in (file_fd, parent_fd):
            if descriptor >= 0:
                try: os.close(descriptor)
                except OSError:
                    if primary is None: _fail("BINANCE_ACCOUNT_PREFLIGHT_CLOSE_FAILED")
