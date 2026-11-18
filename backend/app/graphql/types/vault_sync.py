"""GraphQL types for syncing the person's own vault files to their account (ADR 0007)."""

import strawberry


@strawberry.type
class VaultSyncFile:
    path: str
    content: str | None
    sha256: str
    deleted: bool
    device: str | None = None
    updated_at: str | None = None


@strawberry.type
class VaultSyncPage:
    server_time: str
    files: list[VaultSyncFile]


@strawberry.type
class VaultPutResult:
    """``saved``, ``unchanged`` or ``conflict`` (then ``file`` is the account's version)."""

    status: str
    file: VaultSyncFile | None = None


def to_sync_file(f: dict | None) -> VaultSyncFile | None:
    return VaultSyncFile(**f) if f else None
