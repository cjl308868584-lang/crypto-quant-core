"""Domain exceptions with explicit fail-closed semantics."""


class CryptoQuantError(Exception):
    """Base class for deterministic core failures."""


class CanonicalizationError(CryptoQuantError, ValueError):
    """A value cannot enter a canonical business payload."""


class ContractError(CryptoQuantError, ValueError):
    """A domain contract is invalid."""


class LedgerConflictError(CryptoQuantError):
    """An idempotency key was reused for different economic content."""


class LedgerIntegrityError(CryptoQuantError):
    """The append-only event chain or a stored payload is inconsistent."""


class PolicyError(CryptoQuantError):
    """A release policy, metric, or evidence input cannot be evaluated safely."""
