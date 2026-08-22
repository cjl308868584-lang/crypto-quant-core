"""Deterministic, fail-closed core for the crypto quant project."""

from .canonical import business_hash, canonical_json, stable_id

__all__ = ["business_hash", "canonical_json", "stable_id"]
__version__ = "0.67.0"
