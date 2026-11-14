"""
Data residency / region pinning enforcement.

Each user (and SSO tenant) carries a ``data_region`` column. When a tenant
selects e.g. ``eu`` as their region, every write that lands their data in
storage MUST happen against the EU-pinned database. Today we deploy a single
primary database in ``us``; this module is the enforcement seam so:

1. We can refuse to silently write EU-pinned tenant data to a US DB once a
   second region is provisioned.
2. We can audit every cross-region write attempt before it happens.

Set ``MANIFEST_DATA_REGION`` to the region the *current process* is serving
(``us`` by default). ``assert_region_match()`` raises ``RegionMismatchError``
when a tenant's pinned region differs from this process's region.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

from app.utils.logger import logger

DEFAULT_REGION = "us"
SUPPORTED_REGIONS: tuple[str, ...] = ("us", "eu", "uk", "apac", "ca")


class RegionMismatchError(RuntimeError):
    """Raised when a write would violate the tenant's data-residency pin."""


def current_region() -> str:
    return (os.getenv("MANIFEST_DATA_REGION") or DEFAULT_REGION).strip().lower() or DEFAULT_REGION


def normalize_region(value: str | None) -> str:
    if not value:
        return DEFAULT_REGION
    cleaned = value.strip().lower()
    if cleaned not in SUPPORTED_REGIONS:
        raise ValueError(f"Unsupported data_region: {value!r}")
    return cleaned


def assert_region_match(tenant_region: str | None, *, context: str = "write") -> None:
    """Raise if the tenant's pinned region differs from this process's region.

    Use this as the gate at the top of any write path that persists tenant
    data (idea creation, integration save, etc.) when residency is in scope
    for the table.
    """
    cur = current_region()
    pinned = normalize_region(tenant_region) if tenant_region else cur
    if pinned != cur:
        logger.warning(
            "[data_residency] BLOCKED %s: tenant pinned to region=%s but process serving region=%s",
            context,
            pinned,
            cur,
        )
        raise RegionMismatchError(
            f"Refusing {context}: tenant data_region={pinned!r} but process region={cur!r}"
        )


def filter_to_current_region(rows: Iterable[dict], region_field: str = "data_region") -> list[dict]:
    """Defence-in-depth: drop rows from a query result whose region doesn't
    match the current process. Useful if a misconfigured replica returns
    foreign-region rows."""
    cur = current_region()
    out = []
    for row in rows:
        row_region = normalize_region(str(row.get(region_field) or DEFAULT_REGION))
        if row_region == cur:
            out.append(row)
        else:
            logger.warning(
                "[data_residency] dropping cross-region row (row_region=%s, current=%s)",
                row_region,
                cur,
            )
    return out


__all__ = [
    "DEFAULT_REGION",
    "SUPPORTED_REGIONS",
    "RegionMismatchError",
    "assert_region_match",
    "current_region",
    "filter_to_current_region",
    "normalize_region",
]
