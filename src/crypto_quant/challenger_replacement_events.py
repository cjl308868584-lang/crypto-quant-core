"""Capability-safe immutable events for the replacement Challenger only."""

import base64
import ctypes
import errno
import hashlib
import json
import os
import re
import secrets
import stat
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Tuple

from .canonical import canonical_json, utc_datetime


_MAX_CANONICAL_EVENT_BYTES = 4_194_304
_MAX_CANONICAL_EVENT_SEQUENCE = (1 << 53) - 1
_EVENT_HASH_DOMAIN = b"CHALLENGER_REPLACEMENT_EVENT_V1\x00"
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_CANONICAL_NAME_PATTERN = re.compile(r"^(?P<sequence>[0-9]{20})\.event\.json$")
_STAGING_NAME_PATTERN = re.compile(
    r"^\.stage-[0-9]{20}-[0-9a-f]{64}-[0-9a-f]{32}\.tmp$"
)
_EVENT_CORE_KEYS = frozenset(
    {
        "schema_version",
        "sequence",
        "event_type",
        "slot_id",
        "worker_id",
        "recorded_at",
        "previous_event_hash",
        "payload_encoding",
        "payload_bytes_base64",
        "payload_sha256",
        "plan_hash",
        "build_identity_hash",
        "event_root_device",
        "event_root_inode",
    }
)


class ChallengerReplacementEventError(ValueError):
    """Replacement event storage failed closed."""

    def __init__(self, reason_code):
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.close_failure_reason_code = None
        self.close_failure = None


@dataclass(frozen=True)
class ChallengerReplacementEventRootIdentity:
    absolute_path: str
    device: int
    inode: int
    uid: int
    mode_octal: str


@dataclass(frozen=True)
class ChallengerReplacementCanonicalEvent:
    sequence: int
    event_hash: str
    previous_event_hash: str
    final_bytes: bytes


@dataclass(frozen=True)
class ChallengerReplacementEventPublication:
    outcome: str
    sequence: int
    event_hash: str
    absolute_path: str
    device: int
    inode: int
    size: int


@dataclass(frozen=True)
class ChallengerReplacementEventReplay:
    events: Tuple[ChallengerReplacementCanonicalEvent, ...]
    last_event_hash: str
    next_sequence: int
    orphan_staging_count: int
    orphan_staging_bytes: int


def _event_bytes_invalid(error=None):
    failure = ChallengerReplacementEventError(
        "CHALLENGER_REPLACEMENT_EVENT_BYTES_INVALID"
    )
    if error is None:
        raise failure
    raise failure from error


def _hash_valid(value):
    return isinstance(value, str) and _HASH_PATTERN.fullmatch(value) is not None


def _recorded_at_valid(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return (
        parsed.tzinfo is not None
        and parsed.utcoffset() is not None
        and parsed.microsecond % 1000 == 0
        and utc_datetime(parsed.astimezone(timezone.utc)) == value
    )


def _strict_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _event_bytes_invalid()
        result[key] = value
    return result


def _reject_json_number(_value):
    _event_bytes_invalid()


def _event_from_core(core):
    core_bytes = canonical_json(core).encode("utf-8")
    event_hash = hashlib.sha256(_EVENT_HASH_DOMAIN + core_bytes).hexdigest()
    final_bytes = canonical_json({**core, "event_hash": event_hash}).encode("utf-8")
    if not 0 < len(final_bytes) <= _MAX_CANONICAL_EVENT_BYTES:
        _event_bytes_invalid()
    return ChallengerReplacementCanonicalEvent(
        sequence=core["sequence"],
        event_hash=event_hash,
        previous_event_hash=core["previous_event_hash"],
        final_bytes=final_bytes,
    )


def build_challenger_replacement_event(
    *,
    sequence,
    event_type,
    slot_id,
    worker_id,
    recorded_at,
    previous_event_hash,
    payload_bytes,
    plan_hash,
    build_identity_hash,
    event_root,
):
    """Build one frozen event without touching the event directory."""

    try:
        if not isinstance(event_root, ChallengerReplacementEventRoot):
            _event_bytes_invalid()
        event_root.validate()
        text_values = (event_type, slot_id, worker_id, recorded_at)
        if (
            any(not isinstance(value, str) or not value for value in text_values)
            or not _recorded_at_valid(recorded_at)
        ):
            _event_bytes_invalid()
        if (
            isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence < 1
            or sequence > _MAX_CANONICAL_EVENT_SEQUENCE
            or not isinstance(payload_bytes, bytes)
            or not all(
                _hash_valid(value)
                for value in (previous_event_hash, plan_hash, build_identity_hash)
            )
        ):
            _event_bytes_invalid()
        encoded_payload = base64.b64encode(payload_bytes).decode("ascii")
        core = {
            "schema_version": "challenger_replacement_event_v1",
            "sequence": sequence,
            "event_type": event_type,
            "slot_id": slot_id,
            "worker_id": worker_id,
            "recorded_at": recorded_at,
            "previous_event_hash": previous_event_hash,
            "payload_encoding": "base64_rfc4648",
            "payload_bytes_base64": encoded_payload,
            "payload_sha256": hashlib.sha256(payload_bytes).hexdigest(),
            "plan_hash": plan_hash,
            "build_identity_hash": build_identity_hash,
            "event_root_device": event_root.device,
            "event_root_inode": event_root.inode,
        }
        return _event_from_core(core)
    except ChallengerReplacementEventError:
        raise
    except (TypeError, ValueError, UnicodeError) as error:
        _event_bytes_invalid(error)


def load_challenger_replacement_event_bytes(data):
    """Strictly replay and byte-for-byte rebuild one canonical event."""

    try:
        if not isinstance(data, bytes) or not 0 < len(data) <= _MAX_CANONICAL_EVENT_BYTES:
            _event_bytes_invalid()
        parsed = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_strict_pairs,
            parse_float=_reject_json_number,
            parse_constant=_reject_json_number,
        )
        if not isinstance(parsed, dict) or set(parsed) != _EVENT_CORE_KEYS | {"event_hash"}:
            _event_bytes_invalid()
        event_hash = parsed.pop("event_hash")
        if (
            parsed.get("schema_version") != "challenger_replacement_event_v1"
            or parsed.get("payload_encoding") != "base64_rfc4648"
            or isinstance(parsed.get("sequence"), bool)
            or not isinstance(parsed.get("sequence"), int)
            or parsed["sequence"] < 1
            or parsed["sequence"] > _MAX_CANONICAL_EVENT_SEQUENCE
            or isinstance(parsed.get("event_root_device"), bool)
            or not isinstance(parsed.get("event_root_device"), int)
            or parsed["event_root_device"] < 0
            or isinstance(parsed.get("event_root_inode"), bool)
            or not isinstance(parsed.get("event_root_inode"), int)
            or parsed["event_root_inode"] < 1
            or any(
                not isinstance(parsed.get(key), str) or not parsed[key]
                for key in ("event_type", "slot_id", "worker_id", "recorded_at")
            )
            or not _recorded_at_valid(parsed.get("recorded_at"))
            or not all(
                _hash_valid(parsed.get(key))
                for key in (
                    "previous_event_hash",
                    "payload_sha256",
                    "plan_hash",
                    "build_identity_hash",
                )
            )
            or not _hash_valid(event_hash)
        ):
            _event_bytes_invalid()
        encoded = parsed["payload_bytes_base64"]
        if not isinstance(encoded, str) or not encoded.isascii():
            _event_bytes_invalid()
        payload = base64.b64decode(encoded, validate=True)
        if base64.b64encode(payload).decode("ascii") != encoded:
            _event_bytes_invalid()
        if hashlib.sha256(payload).hexdigest() != parsed["payload_sha256"]:
            _event_bytes_invalid()
        rebuilt = _event_from_core(parsed)
        if rebuilt.event_hash != event_hash or rebuilt.final_bytes != data:
            _event_bytes_invalid()
        return rebuilt
    except ChallengerReplacementEventError:
        raise
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as error:
        _event_bytes_invalid(error)


def _require_open_flag(name):
    value = getattr(os, name, None)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ChallengerReplacementEventError(
            "CHALLENGER_REPLACEMENT_EVENT_PLATFORM_UNSUPPORTED"
        )
    return value


def _write_all(descriptor, data):
    view = memoryview(data)
    while view:
        try:
            written = os.write(descriptor, view)
        except InterruptedError:
            continue
        except OSError as error:
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_IO_FAILED"
            ) from error
        if written <= 0:
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_WRITE_FAILED"
            )
        view = view[written:]


def _fsync_retry(descriptor):
    while True:
        try:
            os.fsync(descriptor)
            return
        except InterruptedError:
            continue
        except OSError as error:
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_FSYNC_FAILED"
            ) from error


def _read_descriptor_exact(descriptor, size):
    chunks = []
    remaining = size
    while remaining:
        try:
            chunk = os.read(descriptor, remaining)
        except InterruptedError:
            continue
        except OSError as error:
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_IO_FAILED"
            ) from error
        if not chunk:
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_FINAL_UNTRUSTED"
            )
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _close_descriptor(descriptor, primary_error=None):
    try:
        os.close(descriptor)
    except OSError as error:
        close_failure = ChallengerReplacementEventError(
            "CHALLENGER_REPLACEMENT_EVENT_CLOSE_FAILED"
        )
        if primary_error is None:
            raise close_failure from error
        try:
            primary_error.close_failure_reason_code = close_failure.reason_code
            primary_error.close_failure = error
        except (AttributeError, TypeError):
            pass


def _trusted_file_stat(entry, root, expected_size=None):
    return (
        stat.S_ISREG(entry.st_mode)
        and entry.st_uid == root.uid == os.getuid()
        and stat.S_IMODE(entry.st_mode) == 0o600
        and entry.st_nlink == 1
        and 0 < entry.st_size <= _MAX_CANONICAL_EVENT_BYTES
        and (expected_size is None or entry.st_size == expected_size)
    )


def _trusted_empty_staging_stat(entry, root):
    return (
        stat.S_ISREG(entry.st_mode)
        and entry.st_uid == root.uid == os.getuid()
        and stat.S_IMODE(entry.st_mode) == 0o600
        and entry.st_nlink == 1
        and entry.st_size == 0
    )


def _same_identity(left, right):
    return (
        left.st_dev,
        left.st_ino,
        left.st_uid,
        left.st_mode,
        left.st_nlink,
        left.st_size,
    ) == (
        right.st_dev,
        right.st_ino,
        right.st_uid,
        right.st_mode,
        right.st_nlink,
        right.st_size,
    )


def _read_final(root, name):
    nofollow = _require_open_flag("O_NOFOLLOW")
    nonblock = _require_open_flag("O_NONBLOCK")
    descriptor = -1
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | nofollow | nonblock,
            dir_fd=root.descriptor,
        )
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ChallengerReplacementEventError(
            "CHALLENGER_REPLACEMENT_EVENT_FINAL_UNTRUSTED"
        ) from error
    primary_error = None
    try:
        opened = os.fstat(descriptor)
        if not _trusted_file_stat(opened, root):
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_FINAL_UNTRUSTED"
            )
        body = _read_descriptor_exact(descriptor, opened.st_size)
        after = os.fstat(descriptor)
        attached = os.stat(name, dir_fd=root.descriptor, follow_symlinks=False)
        if not _same_identity(opened, after) or not _same_identity(after, attached):
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_FINAL_UNTRUSTED"
            )
        try:
            loaded = load_challenger_replacement_event_bytes(body)
        except ChallengerReplacementEventError as error:
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_FINAL_UNTRUSTED"
            ) from error
        return loaded, after
    except ChallengerReplacementEventError as error:
        primary_error = error
        raise
    except OSError as error:
        primary_error = ChallengerReplacementEventError(
            "CHALLENGER_REPLACEMENT_EVENT_IO_FAILED"
        )
        raise primary_error from error
    except BaseException as error:
        primary_error = error
        raise
    finally:
        if descriptor >= 0:
            _close_descriptor(descriptor, primary_error)


def _rename_noreplace(directory_descriptor, source_name, destination_name):
    library = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    destination = os.fsencode(destination_name)
    if sys.platform == "darwin":
        try:
            primitive = library.renameatx_np
        except AttributeError as error:
            raise OSError(errno.ENOSYS, "renameatx_np unavailable") from error
        primitive.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        result = primitive(
            directory_descriptor,
            source,
            directory_descriptor,
            destination,
            0x00000004,
        )
    elif sys.platform.startswith("linux"):
        try:
            primitive = library.renameat2
        except AttributeError as error:
            raise OSError(errno.ENOSYS, "renameat2 unavailable") from error
        primitive.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        result = primitive(
            directory_descriptor,
            source,
            directory_descriptor,
            destination,
            1,
        )
    else:
        raise OSError(errno.ENOSYS, "no supported no-replace primitive")
    if result != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))


def _publication(outcome, root, event, name, entry):
    return ChallengerReplacementEventPublication(
        outcome=outcome,
        sequence=event.sequence,
        event_hash=event.event_hash,
        absolute_path=str(root.path / name),
        device=entry.st_dev,
        inode=entry.st_ino,
        size=entry.st_size,
    )


def verify_challenger_replacement_event_publication(root, record):
    """Read one canonical event only when its exact publication still exists."""

    reason = "CHALLENGER_REPLACEMENT_EVENT_PUBLICATION_UNTRUSTED"
    try:
        keys = {"sequence", "event_hash", "device", "inode", "size"}
        if (not isinstance(root, ChallengerReplacementEventRoot)
                or not isinstance(record, Mapping)
                or frozenset(record) != keys
                or isinstance(record["sequence"], bool)
                or not isinstance(record["sequence"], int)
                or not 1 <= record["sequence"] <= _MAX_CANONICAL_EVENT_SEQUENCE
                or not _hash_valid(record["event_hash"])
                or any(isinstance(record[key], bool) or not isinstance(record[key], int)
                       for key in ("device", "inode", "size"))
                or record["device"] < 0 or record["inode"] < 1
                or not 1 <= record["size"] <= _MAX_CANONICAL_EVENT_BYTES):
            raise ChallengerReplacementEventError(reason)
        root.validate()
        loaded = _read_final(root, "%020d.event.json" % record["sequence"])
        if loaded is None:
            raise ChallengerReplacementEventError(reason)
        event, entry = loaded
        if ((event.sequence, event.event_hash, entry.st_dev, entry.st_ino,
             entry.st_size) != (record["sequence"], record["event_hash"],
                                record["device"], record["inode"], record["size"])):
            raise ChallengerReplacementEventError(reason)
        root.validate()
        return event
    except ChallengerReplacementEventError as error:
        if error.reason_code == reason:
            raise
        raise ChallengerReplacementEventError(reason) from error
    except (KeyError, TypeError, ValueError) as error:
        raise ChallengerReplacementEventError(reason) from error


def _confirm_already_committed(root, event, final_name, existing):
    loaded, _entry = existing
    if loaded != event:
        raise ChallengerReplacementEventError(
            "CHALLENGER_REPLACEMENT_EVENT_SEQUENCE_CONFLICT"
        )
    _fsync_retry(root.descriptor)
    replayed = _read_final(root, final_name)
    if replayed is None or replayed[0] != event:
        raise ChallengerReplacementEventError(
            "CHALLENGER_REPLACEMENT_EVENT_FINAL_UNTRUSTED"
        )
    root.validate()
    return _publication("ALREADY_COMMITTED", root, event, final_name, replayed[1])


def publish_challenger_replacement_event(root, event):
    """Durably publish one canonical event without overwriting any object."""

    if not isinstance(root, ChallengerReplacementEventRoot) or not isinstance(
        event, ChallengerReplacementCanonicalEvent
    ):
        raise ChallengerReplacementEventError(
            "CHALLENGER_REPLACEMENT_EVENT_BYTES_INVALID"
        )
    if load_challenger_replacement_event_bytes(event.final_bytes) != event:
        _event_bytes_invalid()
    root.validate()
    final_name = f"{event.sequence:020d}.event.json"
    existing = _read_final(root, final_name)
    if existing is not None:
        return _confirm_already_committed(root, event, final_name, existing)

    nofollow = _require_open_flag("O_NOFOLLOW")
    staging_name = (
        f".stage-{event.sequence:020d}-{event.event_hash}-"
        f"{secrets.token_hex(16)}.tmp"
    )
    descriptor = -1
    primary_error = None
    try:
        try:
            descriptor = os.open(
                staging_name,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | nofollow,
                0o600,
                dir_fd=root.descriptor,
            )
        except OSError as error:
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_STAGING_UNTRUSTED"
            ) from error
        created = os.fstat(descriptor)
        if not _trusted_empty_staging_stat(created, root):
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_STAGING_UNTRUSTED"
            )
        _write_all(descriptor, event.final_bytes)
        written = os.fstat(descriptor)
        if not _trusted_file_stat(written, root, len(event.final_bytes)):
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_STAGING_UNTRUSTED"
            )
        os.lseek(descriptor, 0, os.SEEK_SET)
        readback = _read_descriptor_exact(descriptor, written.st_size)
        after_read = os.fstat(descriptor)
        if readback != event.final_bytes or not _same_identity(written, after_read):
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_STAGING_UNTRUSTED"
            )
        _fsync_retry(descriptor)
        attached = os.stat(
            staging_name, dir_fd=root.descriptor, follow_symlinks=False
        )
        if not _same_identity(after_read, attached):
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_STAGING_UNTRUSTED"
            )
        try:
            _rename_noreplace(root.descriptor, staging_name, final_name)
        except OSError as error:
            if error.errno == errno.EEXIST:
                raced = _read_final(root, final_name)
                if raced is not None and raced[0] == event:
                    return _confirm_already_committed(
                        root, event, final_name, raced
                    )
                raise ChallengerReplacementEventError(
                    "CHALLENGER_REPLACEMENT_EVENT_SEQUENCE_CONFLICT"
                ) from error
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_PUBLISH_FAILED"
            ) from error
        published = os.stat(final_name, dir_fd=root.descriptor, follow_symlinks=False)
        if not _same_identity(after_read, published):
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_FINAL_UNTRUSTED"
            )
        _fsync_retry(root.descriptor)
        replayed = _read_final(root, final_name)
        if replayed is None or replayed[0] != event:
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_FINAL_UNTRUSTED"
            )
        root.validate()
        return _publication("COMMITTED", root, event, final_name, replayed[1])
    except ChallengerReplacementEventError as error:
        primary_error = error
        raise
    except OSError as error:
        primary_error = ChallengerReplacementEventError(
            "CHALLENGER_REPLACEMENT_EVENT_IO_FAILED"
        )
        raise primary_error from error
    except BaseException as error:
        primary_error = error
        raise
    finally:
        if descriptor >= 0:
            _close_descriptor(descriptor, primary_error)


def replay_challenger_replacement_events(root):
    """Replay the sole canonical sequence; staging entries have no state meaning."""

    if not isinstance(root, ChallengerReplacementEventRoot):
        raise ChallengerReplacementEventError(
            "CHALLENGER_REPLACEMENT_EVENT_ROOT_INVALID"
        )
    root.validate()
    try:
        names = os.listdir(root.descriptor)
    except OSError as error:
        raise ChallengerReplacementEventError(
            "CHALLENGER_REPLACEMENT_EVENT_DIRECTORY_UNTRUSTED"
        ) from error
    canonical = []
    orphan_count = 0
    orphan_bytes = 0
    for name in names:
        match = _CANONICAL_NAME_PATTERN.fullmatch(name)
        if match is not None:
            canonical.append((int(match.group("sequence")), name))
            continue
        if _STAGING_NAME_PATTERN.fullmatch(name) is not None:
            try:
                entry = os.stat(
                    name, dir_fd=root.descriptor, follow_symlinks=False
                )
            except OSError as error:
                raise ChallengerReplacementEventError(
                    "CHALLENGER_REPLACEMENT_EVENT_DIRECTORY_UNTRUSTED"
                ) from error
            orphan_count += 1
            orphan_bytes += max(entry.st_size, 0)
            continue
        raise ChallengerReplacementEventError(
            "CHALLENGER_REPLACEMENT_EVENT_DIRECTORY_UNTRUSTED"
        )

    events = []
    expected_sequence = 1
    expected_parent = "0" * 64
    for sequence, name in sorted(canonical):
        if sequence != expected_sequence:
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_CONTINUITY_GAP"
            )
        loaded_final = _read_final(root, name)
        if loaded_final is None:
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_FINAL_UNTRUSTED"
            )
        event = loaded_final[0]
        if event.sequence != sequence or event.previous_event_hash != expected_parent:
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_CONTINUITY_GAP"
            )
        decoded = json.loads(event.final_bytes.decode("utf-8"))
        if (
            decoded["event_root_device"] != root.device
            or decoded["event_root_inode"] != root.inode
        ):
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_CONTINUITY_GAP"
            )
        events.append(event)
        expected_sequence += 1
        expected_parent = event.event_hash
    if events:
        _fsync_retry(root.descriptor)
    root.validate()
    return ChallengerReplacementEventReplay(
        events=tuple(events),
        last_event_hash=expected_parent,
        next_sequence=expected_sequence,
        orphan_staging_count=orphan_count,
        orphan_staging_bytes=orphan_bytes,
    )


def _root_stat_valid(entry, identity):
    return (
        stat.S_ISDIR(entry.st_mode)
        and entry.st_uid == identity.uid == os.getuid()
        and stat.S_IMODE(entry.st_mode) == 0o700
        and identity.mode_octal == "0700"
        and (entry.st_dev, entry.st_ino) == (identity.device, identity.inode)
    )


class ChallengerReplacementEventRoot:
    """Retain the exact pre-authorized event directory inode."""

    def __init__(self, path, identity, descriptor):
        self.path = path
        self.device = identity.device
        self.inode = identity.inode
        self.uid = identity.uid
        self.descriptor = descriptor
        self._identity = identity

    def __enter__(self):
        return self

    def __exit__(self, _error_type, error, _traceback):
        self._close(error)

    def validate(self):
        if self.descriptor < 0:
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_ROOT_CHANGED"
            )
        try:
            retained = os.fstat(self.descriptor)
            attached = os.stat(self.path, follow_symlinks=False)
        except OSError as error:
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_ROOT_CHANGED"
            ) from error
        if not _root_stat_valid(retained, self._identity) or (
            retained.st_dev,
            retained.st_ino,
        ) != (attached.st_dev, attached.st_ino):
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_ROOT_CHANGED"
            )

    def close(self):
        self._close(None)

    def _close(self, primary_error):
        if self.descriptor < 0:
            return
        descriptor = self.descriptor
        self.descriptor = -1
        _close_descriptor(descriptor, primary_error)


def open_challenger_replacement_event_root(identity):
    """Open an already-created root only when every identity field matches."""

    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if (
        not isinstance(nofollow, int)
        or isinstance(nofollow, bool)
        or nofollow <= 0
        or not isinstance(directory, int)
        or isinstance(directory, bool)
        or directory <= 0
    ):
        raise ChallengerReplacementEventError(
            "CHALLENGER_REPLACEMENT_EVENT_PLATFORM_UNSUPPORTED"
        )
    if not isinstance(identity, ChallengerReplacementEventRootIdentity):
        raise ChallengerReplacementEventError(
            "CHALLENGER_REPLACEMENT_EVENT_ROOT_INVALID"
        )
    path = Path(identity.absolute_path)
    if (
        not path.is_absolute()
        or path.name in ("", ".", "..")
        or identity.mode_octal != "0700"
        or identity.uid != os.getuid()
        or isinstance(identity.device, bool)
        or not isinstance(identity.device, int)
        or isinstance(identity.inode, bool)
        or not isinstance(identity.inode, int)
    ):
        raise ChallengerReplacementEventError(
            "CHALLENGER_REPLACEMENT_EVENT_ROOT_INVALID"
        )
    descriptor = -1
    primary_error = None
    try:
        if path.parent.resolve(strict=True) != path.parent:
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_ROOT_INVALID"
            )
        lexical = os.lstat(path)
        if not _root_stat_valid(lexical, identity):
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_ROOT_INVALID"
            )
        flags = os.O_RDONLY | directory | nofollow
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        attached = os.stat(path, follow_symlinks=False)
        if (
            not _root_stat_valid(opened, identity)
            or (opened.st_dev, opened.st_ino) != (lexical.st_dev, lexical.st_ino)
            or (opened.st_dev, opened.st_ino)
            != (attached.st_dev, attached.st_ino)
        ):
            raise ChallengerReplacementEventError(
                "CHALLENGER_REPLACEMENT_EVENT_ROOT_CHANGED"
            )
        root = ChallengerReplacementEventRoot(path, identity, descriptor)
        root.validate()
        descriptor = -1
        return root
    except ChallengerReplacementEventError as error:
        primary_error = error
        raise
    except OSError as error:
        primary_error = ChallengerReplacementEventError(
            "CHALLENGER_REPLACEMENT_EVENT_ROOT_INVALID"
        )
        raise primary_error from error
    finally:
        if descriptor >= 0:
            _close_descriptor(descriptor, primary_error)
