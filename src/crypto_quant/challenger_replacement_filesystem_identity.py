"""Strict filesystem identities for replacement activation contracts."""

_MAX_FILESYSTEM_IDENTITY = 2**64 - 1


class FilesystemIdentityError(ValueError):
    pass


def _encode_filesystem_identity(value, *, allow_zero):
    if (isinstance(value, bool) or not isinstance(value, int)
            or value < (0 if allow_zero else 1)
            or value > _MAX_FILESYSTEM_IDENTITY):
        raise FilesystemIdentityError(
            "CHALLENGER_REPLACEMENT_FILESYSTEM_IDENTITY_INVALID")
    return str(value)


def _decode_filesystem_identity(value, *, allow_zero):
    if (not isinstance(value, str) or not 1 <= len(value) <= 20
            or not value.isascii() or not value.isdecimal()
            or (len(value) > 1 and value.startswith("0"))):
        raise FilesystemIdentityError(
            "CHALLENGER_REPLACEMENT_FILESYSTEM_IDENTITY_INVALID")
    decoded = int(value)
    if not (0 if allow_zero else 1) <= decoded <= _MAX_FILESYSTEM_IDENTITY:
        raise FilesystemIdentityError(
            "CHALLENGER_REPLACEMENT_FILESYSTEM_IDENTITY_INVALID")
    return decoded


def _serialize_filesystem_identity(value, device_key="device", inode_key="inode"):
    result = dict(value)
    result[device_key] = _encode_filesystem_identity(
        result[device_key], allow_zero=True)
    result[inode_key] = _encode_filesystem_identity(
        result[inode_key], allow_zero=False)
    return result


def _deserialize_filesystem_identity(value, device_key="device", inode_key="inode"):
    result = dict(value)
    result[device_key] = _decode_filesystem_identity(
        result[device_key], allow_zero=True)
    result[inode_key] = _decode_filesystem_identity(
        result[inode_key], allow_zero=False)
    return result


def _filesystem_identity_pair(value, device_key="device", inode_key="inode"):
    decoded = _deserialize_filesystem_identity(value, device_key, inode_key)
    return decoded[device_key], decoded[inode_key]


def _serialize_activation_filesystem_identities(snapshot, event, python):
    return (
        _serialize_filesystem_identity(snapshot, "root_device", "root_inode"),
        _serialize_filesystem_identity(event),
        _serialize_filesystem_identity(python),
    )


def _validate_activation_filesystem_identities(value):
    _deserialize_filesystem_identity(
        value["snapshot"], "root_device", "root_inode")
    _deserialize_filesystem_identity(value["event_root"])
    _deserialize_filesystem_identity(value["python"])


def _event_root_identity(value):
    from .challenger_replacement_events import ChallengerReplacementEventRootIdentity

    device, inode = _filesystem_identity_pair(value)
    return ChallengerReplacementEventRootIdentity(
        value["path"], device, inode, value["owner_uid"], "0700")
