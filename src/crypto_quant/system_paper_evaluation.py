"""Tail-blind authority and fixed-tail evaluation for System Paper."""

import hashlib
import json
import os
import stat
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from .canonical import canonical_json, utc_datetime
from .system_paper_evidence import publish_owner_exact
from .system_paper_install import load_system_paper_install_receipt
from .system_paper_launchd import load_system_paper_launchd_contract
from .system_paper_plan import load_system_paper_plan
from .system_paper_scheduler import (
    SystemPaperSchedulePolicy,
    load_system_paper_schedule_event_metadata,
)
from .system_paper_start_receipt import (
    load_system_paper_start_receipt,
    load_system_paper_start_receipt_metadata,
)


_MAX_INSTALL_PREVIEW_BYTES = 2 * 1024 * 1024
_MAX_AUTHORITY_BYTES = 32 * 1024 * 1024
_PRIVATE_TMP = Path("/private/tmp")
_TAIL_SETTLE_DELAY = timedelta(minutes=5)


class SystemPaperEvaluationError(ValueError):
    """The evaluator failed closed before producing a research claim."""

    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


def _utc(value: object) -> Tuple[datetime, str]:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.endswith("Z"):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_TIME_INVALID"
            ) from error
    else:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_TIME_INVALID"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_TIME_INVALID"
        )
    parsed = parsed.astimezone(timezone.utc)
    if parsed.microsecond % 1000:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_TIME_INVALID"
        )
    text = utc_datetime(parsed)
    if isinstance(value, str) and value != text:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_TIME_INVALID"
        )
    return parsed, text


def _now() -> str:
    return utc_datetime(datetime.now(timezone.utc))


def _stat_identity(entry: os.stat_result) -> Tuple[int, ...]:
    return (
        entry.st_dev,
        entry.st_ino,
        entry.st_mode,
        entry.st_uid,
        entry.st_nlink,
        entry.st_size,
        entry.st_mtime_ns,
        entry.st_ctime_ns,
    )


class _RetainedAuthorityFile:
    """One no-follow owner-only file retained through the full observation."""

    def __init__(self, path, descriptor, entry, body, maximum_bytes):
        self.path = path
        self.descriptor = descriptor
        self.entry = entry
        self.body = body
        self.maximum_bytes = maximum_bytes

    @staticmethod
    def _read(descriptor: int, maximum_bytes: int) -> bytes:
        os.lseek(descriptor, 0, os.SEEK_SET)
        chunks = []
        total = 0
        while total <= maximum_bytes:
            chunk = os.read(
                descriptor, min(64 * 1024, maximum_bytes + 1 - total)
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        return b"".join(chunks)

    @classmethod
    def open(
        cls,
        path: Path,
        *,
        maximum_bytes: int = _MAX_AUTHORITY_BYTES,
        allow_empty: bool = False,
    ) -> "_RetainedAuthorityFile":
        path = Path(path)
        descriptor = None
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            flags |= getattr(os, "O_CLOEXEC", 0)
            descriptor = os.open(path, flags)
            entry = os.fstat(descriptor)
            if (
                not stat.S_ISREG(entry.st_mode)
                or entry.st_uid != os.getuid()
                or entry.st_nlink != 1
                or stat.S_IMODE(entry.st_mode) != 0o600
                or entry.st_size > maximum_bytes
                or (entry.st_size == 0 and not allow_empty)
            ):
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
                )
            body = cls._read(descriptor, maximum_bytes)
            retained = os.fstat(descriptor)
            current = os.stat(path, follow_symlinks=False)
            if (
                len(body) != entry.st_size
                or len(body) > maximum_bytes
                or _stat_identity(entry) != _stat_identity(retained)
                or _stat_identity(retained) != _stat_identity(current)
            ):
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
                )
            return cls(path, descriptor, entry, body, maximum_bytes)
        except SystemPaperEvaluationError:
            if descriptor is not None:
                os.close(descriptor)
            raise
        except OSError as error:
            if descriptor is not None:
                os.close(descriptor)
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            ) from error

    def verify(self) -> None:
        try:
            retained = os.fstat(self.descriptor)
            current = os.stat(self.path, follow_symlinks=False)
            body = self._read(self.descriptor, self.maximum_bytes)
        except OSError as error:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            ) from error
        if (
            body != self.body
            or _stat_identity(self.entry) != _stat_identity(retained)
            or _stat_identity(retained) != _stat_identity(current)
        ):
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            )

    def close(self) -> None:
        os.close(self.descriptor)


class _RetainedAuthorityAbsence:
    """Retain a directory attachment and prove one child stays absent."""

    def __init__(self, path, descriptor, parent_entry):
        self.path = path
        self.descriptor = descriptor
        self.parent_entry = parent_entry

    @classmethod
    def open(cls, path: Path) -> "_RetainedAuthorityAbsence":
        path = Path(path)
        descriptor = None
        try:
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            flags |= getattr(os, "O_CLOEXEC", 0)
            descriptor = os.open(path.parent, flags)
            before = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(before.st_mode)
                or before.st_uid != os.getuid()
                or stat.S_IMODE(before.st_mode) != 0o700
            ):
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
                )
            try:
                os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
                )
            retained = os.fstat(descriptor)
            current = os.stat(path.parent, follow_symlinks=False)
            if (
                _stat_identity(before) != _stat_identity(retained)
                or _stat_identity(retained) != _stat_identity(current)
            ):
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
                )
            return cls(path, descriptor, before)
        except SystemPaperEvaluationError:
            if descriptor is not None:
                os.close(descriptor)
            raise
        except OSError as error:
            if descriptor is not None:
                os.close(descriptor)
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            ) from error

    def verify(self) -> None:
        try:
            retained = os.fstat(self.descriptor)
            current = os.stat(self.path.parent, follow_symlinks=False)
            try:
                os.stat(
                    self.path.name,
                    dir_fd=self.descriptor,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                pass
            else:
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
                )
        except SystemPaperEvaluationError:
            raise
        except OSError as error:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            ) from error
        if (
            _stat_identity(self.parent_entry) != _stat_identity(retained)
            or _stat_identity(retained) != _stat_identity(current)
        ):
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_SOURCE_CHANGED"
            )

    def close(self) -> None:
        os.close(self.descriptor)


class _RetainedAuthoritySet:
    def __init__(self):
        self.files = []

    def capture(self, path: Path, **kwargs) -> _RetainedAuthorityFile:
        retained = _RetainedAuthorityFile.open(path, **kwargs)
        self.files.append(retained)
        return retained

    def capture_absent(self, path: Path) -> None:
        retained = _RetainedAuthorityAbsence.open(path)
        self.files.append(retained)

    def capture_optional(
        self, path: Path, **kwargs
    ) -> Optional[_RetainedAuthorityFile]:
        try:
            return self.capture(path, **kwargs)
        except SystemPaperEvaluationError:
            self.capture_absent(path)
            return None

    def verify(self) -> None:
        for retained in self.files:
            retained.verify()

    def close(self) -> None:
        for retained in self.files:
            retained.close()


def _absolute_paths(values: Mapping[str, Path]) -> Dict[str, Path]:
    result = {}
    for name, value in values.items():
        if not isinstance(value, (str, Path)) or "\x00" in str(value):
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_PATH_INVALID"
            )
        path = Path(value)
        if not path.is_absolute() or ".." in path.parts:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_PATH_INVALID"
            )
        result[name] = path
    return result


def _derive_plist_path(contract_path: Path) -> Path:
    descriptor = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
        descriptor = os.open(contract_path.parent, flags)
        before = os.fstat(descriptor)
        names = set(os.listdir(descriptor))
        after = os.fstat(descriptor)
    except OSError as error:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (
        not stat.S_ISDIR(before.st_mode)
        or before.st_uid != os.getuid()
        or stat.S_IMODE(before.st_mode) != 0o700
        or _stat_identity(before) != _stat_identity(after)
        or contract_path.name not in names
        or len(names) != 2
    ):
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID"
        )
    other = next(iter(names - {contract_path.name}))
    if not other.endswith(".plist") or "/" in other:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID"
        )
    return contract_path.parent / other


def _install_preview(retained: _RetainedAuthorityFile) -> Mapping[str, Any]:
    try:
        value = json.loads(retained.body.decode("utf-8"))
        if (
            not isinstance(value, Mapping)
            or canonical_json(value).encode("utf-8") != retained.body
            or not isinstance(value["preflight_receipt"]["receipt_path"], str)
        ):
            raise ValueError("invalid preview")
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_INSTALL_PREVIEW_INVALID"
        ) from error
    return value


def _copy_event_metadata(
    state_files: Mapping[str, Optional[_RetainedAuthorityFile]],
    *,
    plan: Mapping[str, Any],
    temporary_parent: Path,
) -> Mapping[str, Any]:
    main = state_files["main"]
    if main is None:
        return {"events": (), "projection": {}}
    policy = SystemPaperSchedulePolicy.create(plan)
    try:
        with tempfile.TemporaryDirectory(
            prefix="system-paper-evaluation-", dir=str(temporary_parent)
        ) as directory:
            root = Path(directory)
            root.chmod(0o700)
            copy_path = root / "system-paper.sqlite"
            for suffix, retained in state_files.items():
                if retained is None:
                    continue
                target = (
                    copy_path
                    if suffix == "main"
                    else Path(str(copy_path) + suffix)
                )
                target.write_bytes(retained.body)
                target.chmod(0o600)
            replay = load_system_paper_schedule_event_metadata(copy_path, policy)
    except SystemPaperEvaluationError:
        raise
    except Exception as error:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_STATE_REPLAY_INVALID"
        ) from error
    return replay


def _evaluate_complete_cohort(*_args, **_kwargs):
    raise SystemPaperEvaluationError(
        "SYSTEM_PAPER_EVALUATION_FINAL_NOT_IMPLEMENTED"
    )


def observe_system_paper_evaluation_readiness(
    *,
    plan_path: Path,
    start_receipt_path: Path,
    install_receipt_path: Path,
    contract_path: Path,
    slot_root: Path,
    runtime_root: Path,
    output_root: Path,
    _clock=None,
    _machine_probe=None,
    _filesystem_probe=None,
) -> Mapping[str, Any]:
    """Observe readiness without reading any slot economic artifact pre-tail."""

    paths = _absolute_paths(
        {
            "plan": plan_path,
            "start": start_receipt_path,
            "install": install_receipt_path,
            "contract": contract_path,
            "slot_root": slot_root,
            "runtime_root": runtime_root,
            "output_root": output_root,
        }
    )
    observed, observed_at = _utc((_clock or _now)())
    retained = _RetainedAuthoritySet()
    state_retained = _RetainedAuthoritySet()
    try:
        try:
            install_source = retained.capture(
                paths["install"], maximum_bytes=_MAX_INSTALL_PREVIEW_BYTES
            )
        except SystemPaperEvaluationError as error:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_INSTALL_PREVIEW_INVALID"
            ) from error
        preview = _install_preview(install_source)
        plist_path = _derive_plist_path(paths["contract"])
        preflight_path = Path(preview["preflight_receipt"]["receipt_path"])
        if not preflight_path.is_absolute() or ".." in preflight_path.parts:
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_INSTALL_PREVIEW_INVALID"
            )
        retained.capture(paths["plan"])
        retained.capture(paths["contract"])
        retained.capture(plist_path)
        retained.capture(preflight_path)
        retained.capture(paths["start"], maximum_bytes=4 * 1024 * 1024)

        plan = load_system_paper_plan(paths["plan"])
        contract = load_system_paper_launchd_contract(
            contract_path=paths["contract"], plist_path=plist_path
        )
        if (
            paths["runtime_root"] != Path(contract["runtime_root"])
            or paths["slot_root"]
            != Path(contract["root_paths"]["artifacts"])
            / "system-paper-slots"
        ):
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_ROOT_MISMATCH"
            )
        install = load_system_paper_install_receipt(
            receipt_path=paths["install"],
            contract_path=paths["contract"],
            plist_path=plist_path,
            preflight_receipt_path=preflight_path,
            _machine_probe=_machine_probe,
            _filesystem_probe=_filesystem_probe,
        )
        retained.capture(Path(install["target_path"]))
        start = load_system_paper_start_receipt_metadata(
            receipt_path=paths["start"],
            contract_path=paths["contract"],
            plist_path=plist_path,
            preflight_receipt_path=preflight_path,
            install_receipt_path=paths["install"],
            _machine_probe=_machine_probe,
            _filesystem_probe=_filesystem_probe,
        )
        if (
            plan["plan_hash"] != contract["plan_hash"]
            or install["receipt_hash"]
            != start["source_binding"]["install_receipt_hash"]
        ):
            raise SystemPaperEvaluationError(
                "SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID"
            )

        state_path = (
            Path(contract["root_paths"]["state"])
            / "system-paper.sqlite"
        )
        state_files = {
            "main": state_retained.capture(state_path),
            "-wal": None,
            "-shm": None,
        }
        for suffix in ("-wal", "-shm"):
            candidate = Path(str(state_path) + suffix)
            state_files[suffix] = state_retained.capture_optional(
                candidate, allow_empty=True
            )
        replay = _copy_event_metadata(
            state_files,
            plan=plan,
            temporary_parent=_PRIVATE_TMP,
        )
        start_at, start_text = _utc(start["cohort_started_at"])
        tail_at, tail_text = _utc(start["cohort_tail_end"])
        if observed >= tail_at + _TAIL_SETTLE_DELAY:
            replayed_start = load_system_paper_start_receipt(
                receipt_path=paths["start"],
                contract_path=paths["contract"],
                plist_path=plist_path,
                preflight_receipt_path=preflight_path,
                install_receipt_path=paths["install"],
                _machine_probe=_machine_probe,
                _filesystem_probe=_filesystem_probe,
            )
            if replayed_start != start:
                raise SystemPaperEvaluationError(
                    "SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID"
                )
            complete = _evaluate_complete_cohort(
                plan=plan,
                contract=contract,
                install=install,
                start=start,
                replay=replay,
                observed_at=observed_at,
                slot_root=paths["slot_root"],
            )
            retained.verify()
            state_retained.verify()
            return complete
        projection = replay["projection"]
        incidents = sum(
            event["event_type"] in ("FAILED", "MISSED", "EXPIRED")
            for event in replay["events"]
        )
        successes = sum(
            item["terminal_state"] == "SUCCEEDED"
            for item in projection.values()
        )
        policy = SystemPaperSchedulePolicy.create(plan)
        scheduled = start_at
        next_required = None
        while scheduled < tail_at:
            slot = policy.slot_from_scheduled(scheduled)
            if (
                slot.slot_id not in projection
                or projection[slot.slot_id]["terminal_state"] != "SUCCEEDED"
            ):
                next_required = {
                    "slot_id": slot.slot_id,
                    "scheduled_for": slot.scheduled_for,
                    "due_at": slot.due_at,
                    "expires_at": slot.expires_at,
                }
                break
            scheduled += timedelta(hours=4)
        retained.verify()
        state_retained.verify()
        return {
            "status": "SYSTEM_PAPER_EVALUATION_PENDING_BEFORE_TAIL",
            "observed_at": observed_at,
            "cohort_started_at": start_text,
            "tail_end": tail_text,
            "elapsed_days": max(
                0, int((observed - start_at).total_seconds() // 86_400)
            ),
            "verified_terminal_slot_count": successes,
            "incident_count": incidents,
            "next_required_slot": next_required,
            "evidence_health": (
                "VERIFIED" if incidents == 0 else "INCIDENT_DETECTED"
            ),
        }
    except SystemPaperEvaluationError:
        raise
    except Exception as error:
        raise SystemPaperEvaluationError(
            "SYSTEM_PAPER_EVALUATION_AUTHORITY_INVALID"
        ) from error
    finally:
        state_retained.close()
        retained.close()
