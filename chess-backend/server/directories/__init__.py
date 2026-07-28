"""
directories/ — abstract seams for ephemeral, in-memory state.

Phase 0 of the cloud-scale migration (see .github/Server_Design_Implementation_Plan.md).
Each interface here has exactly one in-memory implementation today and will
gain a Redis-backed implementation in Phase 1, without changing any call
site in the services that depend on it.
"""
from __future__ import annotations
