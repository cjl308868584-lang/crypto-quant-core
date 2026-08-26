from collections.abc import Mapping
from dataclasses import dataclass
import hashlib, json, os, stat
from pathlib import Path
from .canonical import canonical_json
from .challenger_replacement_binance_private_protocol import BinancePrivateRequest, sign_binance_private_request
_KEYS = frozenset({"$schema", "schema_version", "absolute_path", "parent_device", "parent_inode", "file_device", "file_inode", "file_sha256"})
_SCHEMA = "./challenger-replacement-binance-credential-reference-v1.schema.json"
_TOKEN = object()
class BinanceCredentialError(ValueError):
    def __init__(self, reason_code):
        super().__init__(reason_code); self.reason_code = reason_code
        self.close_failure_reason_code = None
@dataclass(frozen=True)
class BinanceCredentialIdentity:
    device: int; inode: int; owner_uid: int; file_sha256: str; key_fingerprint: str
def _fail(reason, error=None):
    failure = BinanceCredentialError(reason)
    if error is None:
        raise failure
    raise failure from error
def _open_flag(name):
    value = getattr(os, name, None)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None
def _close(descriptor, primary=None):
    try:
        os.close(descriptor)
    except OSError as error:
        if primary is None:
            _fail("BINANCE_CREDENTIAL_CLOSE_FAILED", error)
        try:
            primary.close_failure_reason_code = "BINANCE_CREDENTIAL_CLOSE_FAILED"
        except (AttributeError, TypeError):
            pass
def _identity(entry):
    return (entry.st_dev, entry.st_ino, entry.st_uid, entry.st_mode, entry.st_nlink, entry.st_size)
def _valid_reference(reference):
    if not isinstance(reference, Mapping) or frozenset(reference) != _KEYS:
        return False
    path, digest = reference.get("absolute_path"), reference.get("file_sha256")
    numbers = tuple(reference.get(key) for key in ("parent_device", "parent_inode", "file_device", "file_inode"))
    return (reference.get("$schema") == _SCHEMA
            and reference.get("schema_version") == "1.0.0"
            and isinstance(path, str) and Path(path).is_absolute()
            and Path(path).name not in ("", ".", "..")
            and all(isinstance(value, int) and not isinstance(value, bool)
                    and 0 <= value <= (1 << 53) - 1 for value in numbers)
            and numbers[1] > 0 and numbers[3] > 0
            and isinstance(digest, str) and len(digest) == 64
            and not set(digest) - frozenset("0123456789abcdef"))
def _read(descriptor, size):
    body = bytearray()
    while len(body) < size:
        try:
            chunk = os.read(descriptor, min(4096, size - len(body)))
        except InterruptedError:
            continue
        if not chunk:
            break
        body.extend(chunk)
    if len(body) != size or os.read(descriptor, 1):
        _fail("BINANCE_CREDENTIAL_FILE_UNTRUSTED")
    return body
def _decode(body):
    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                _fail("BINANCE_CREDENTIAL_FORMAT_INVALID")
            result[key] = value
        return result
    try:
        document = json.loads(bytes(body).decode("utf-8"), object_pairs_hook=pairs)
        exact = (canonical_json(document) + "\n").encode()
    except (UnicodeDecodeError, ValueError, TypeError) as error:
        if isinstance(error, BinanceCredentialError):
            raise
        _fail("BINANCE_CREDENTIAL_FORMAT_INVALID", error)
    if (not isinstance(document, dict) or frozenset(document) != {"api_key", "hmac_secret"}
            or exact != bytes(body) or any(not isinstance(document[key], str)
            or not 16 <= len(document[key]) <= 256
            or any(not 33 <= ord(character) <= 126 for character in document[key])
            for key in ("api_key", "hmac_secret"))):
        _fail("BINANCE_CREDENTIAL_FORMAT_INVALID")
    return tuple(bytearray(document[key].encode("ascii"))
                 for key in ("api_key", "hmac_secret"))
def _wipe(buffer):
    buffer[:] = b"\0" * len(buffer)
class BinanceAuthorization:
    __slots__ = ("_request", "_api_key", "_parameters", "_closed", "_used")
    def __init__(self, request, api_key, parameters, token):
        if token is not _TOKEN:
            raise TypeError("BinanceAuthorization is capability-issued")
        self._request, self._api_key, self._parameters = request, api_key, parameters
        self._closed = self._used = False
    def _consume(self, token):
        if token is not _TOKEN or self._closed or self._used:
            _fail("BINANCE_CREDENTIAL_AUTHORIZATION_ALREADY_USED")
        self._used = True
        return self._request, memoryview(self._api_key), memoryview(self._parameters)
    def close(self):
        if not self._closed:
            _wipe(self._api_key); _wipe(self._parameters); self._closed = True
    def __enter__(self):
        if self._closed:
            _fail("BINANCE_CREDENTIAL_AUTHORIZATION_ALREADY_USED")
        return self
    def __exit__(self, *_args):
        self.close()
    def __repr__(self):
        return "BinanceAuthorization(redacted=True,closed={!r})".format(self._closed)
    def __reduce_ex__(self, _protocol):
        raise TypeError("BinanceAuthorization cannot be serialized")
def _consume_binance_authorization(authorization):
    if not isinstance(authorization, BinanceAuthorization):
        _fail("BINANCE_CREDENTIAL_AUTHORIZATION_INVALID")
    return authorization._consume(_TOKEN)
class BinanceCredentialCapability:
    __slots__ = ("identity", "_path", "_parent_fd", "_file_fd", "_parent_stat",
                 "_file_stat", "_api_key", "_secret", "_closed")
    def __init__(self, values):
        (self.identity, self._path, self._parent_fd, self._file_fd,
         self._parent_stat, self._file_stat, self._api_key, self._secret) = values
        self._closed = False
    def _validate(self):
        if self._closed:
            _fail("BINANCE_CREDENTIAL_CAPABILITY_CLOSED")
        try:
            current = (os.fstat(self._parent_fd),
                       os.stat(self._path.parent, follow_symlinks=False),
                       os.fstat(self._file_fd),
                       os.stat(self._path.name, dir_fd=self._parent_fd,
                               follow_symlinks=False))
        except OSError as error:
            _fail("BINANCE_CREDENTIAL_ATTACHMENT_CHANGED", error)
        if any(_identity(value) != _identity(expected) for value, expected in
               zip(current, (self._parent_stat, self._parent_stat,
                             self._file_stat, self._file_stat))):
            _fail("BINANCE_CREDENTIAL_ATTACHMENT_CHANGED")
    def authorize(self, request):
        self._validate()
        if (not isinstance(request, BinancePrivateRequest)
                or not {"recvWindow", "timestamp"}.issubset(request.parameter_names)):
            _fail("BINANCE_CREDENTIAL_AUTHORIZATION_INVALID")
        try:
            signature = sign_binance_private_request(request, bytes(self._secret))
        except ValueError as error:
            _fail("BINANCE_CREDENTIAL_AUTHORIZATION_INVALID", error)
        parameters = bytearray(request.encoded_parameters + b"&signature=" + signature.encode())
        return BinanceAuthorization(request, bytearray(self._api_key), parameters, _TOKEN)
    def _shutdown(self, primary=None):
        if self._closed:
            return
        self._closed = True; _wipe(self._secret); _wipe(self._api_key)
        failure = None
        for descriptor in (self._file_fd, self._parent_fd):
            try:
                _close(descriptor, primary or failure)
            except BinanceCredentialError as error:
                failure = failure or error
        self._file_fd = self._parent_fd = -1
        if primary is None and failure is not None:
            raise failure
    def close(self):
        self._shutdown()
    def __enter__(self):
        self._validate(); return self
    def __exit__(self, _kind, error, _traceback):
        self._shutdown(error)
    def __repr__(self):
        return "BinanceCredentialCapability(fingerprint={}...,closed={!r})".format(
            self.identity.key_fingerprint[:12], self._closed)
    def __reduce_ex__(self, _protocol):
        raise TypeError("BinanceCredentialCapability cannot be serialized")
def open_binance_credential_capability(*, reference, expected_owner_uid):
    flags = tuple(_open_flag(name) for name in ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK"))
    if any(value is None for value in flags):
        _fail("BINANCE_CREDENTIAL_PLATFORM_UNSUPPORTED")
    if (not _valid_reference(reference) or isinstance(expected_owner_uid, bool)
            or expected_owner_uid != os.getuid()):
        _fail("BINANCE_CREDENTIAL_REFERENCE_INVALID")
    nofollow, directory, nonblock = flags
    path = Path(reference["absolute_path"]); parent_fd = file_fd = -1
    body = api_key = secret = None; primary = None
    try:
        parent_fd = os.open(path.parent, os.O_RDONLY | nofollow | directory | nonblock)
        parent = os.fstat(parent_fd); attached_parent = os.stat(path.parent, follow_symlinks=False)
        if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != expected_owner_uid
                or stat.S_IMODE(parent.st_mode) != 0o700
                or (parent.st_dev, parent.st_ino) != (reference["parent_device"], reference["parent_inode"])
                or _identity(parent) != _identity(attached_parent)):
            _fail("BINANCE_CREDENTIAL_PARENT_CHANGED")
        file_fd = os.open(path.name, os.O_RDONLY | nofollow | nonblock, dir_fd=parent_fd)
        opened = os.fstat(file_fd); attached = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_uid != expected_owner_uid
                or stat.S_IMODE(opened.st_mode) != 0o600 or opened.st_nlink != 1
                or not 1 <= opened.st_size <= 8192
                or (opened.st_dev, opened.st_ino) != (reference["file_device"], reference["file_inode"])
                or _identity(opened) != _identity(attached)):
            _fail("BINANCE_CREDENTIAL_FILE_UNTRUSTED")
        body = _read(file_fd, opened.st_size)
        if (_identity(opened) != _identity(os.fstat(file_fd))
                or _identity(opened) != _identity(os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False))
                or hashlib.sha256(body).hexdigest() != reference["file_sha256"]):
            _fail("BINANCE_CREDENTIAL_FILE_UNTRUSTED")
        api_key, secret = _decode(body)
        identity = BinanceCredentialIdentity(opened.st_dev, opened.st_ino, opened.st_uid, reference["file_sha256"], hashlib.sha256(api_key).hexdigest())
        result = BinanceCredentialCapability((identity, path, parent_fd, file_fd, parent, opened, api_key, secret))
        parent_fd = file_fd = -1; api_key = secret = None
        return result
    except BinanceCredentialError as error:
        primary = error; raise
    except OSError as error:
        primary = BinanceCredentialError("BINANCE_CREDENTIAL_FILE_INVALID"); raise primary from error
    finally:
        if body is not None: _wipe(body)
        for buffer in (api_key, secret):
            if buffer is not None: _wipe(buffer)
        for descriptor in (file_fd, parent_fd):
            if descriptor >= 0: _close(descriptor, primary)
