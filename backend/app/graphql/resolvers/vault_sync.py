"""Sync the person's own vault files (notes, their writing in idea files) to their account."""

import asyncio

import strawberry
from app.auth.current_user import get_current_user_id
from app.graphql.types.vault_sync import VaultPutResult, VaultSyncPage, to_sync_file
from app.services.ideas import vault_sync


@strawberry.type
class VaultSyncQuery:
    @strawberry.field
    async def vault_files(
        self, info: strawberry.Info, since_updated_at: str | None = None
    ) -> VaultSyncPage:
        """Your own vault files kept in your account (notes and your writing around Manifest's
        generated blocks), changed after sinceUpdatedAt, with deletions. The vault sync in
        manifest_vault.py uses this to keep every computer's vault the same."""
        user_id = get_current_user_id(info.context["request"])
        page = await asyncio.to_thread(
            vault_sync.list_files, info.context["db"], str(user_id), since_updated_at
        )
        return VaultSyncPage(
            server_time=page["server_time"],
            files=[to_sync_file(f) for f in page["files"]],
        )


@strawberry.type
class VaultSyncMutation:
    @strawberry.mutation
    async def put_vault_file(
        self,
        info: strawberry.Info,
        path: str,
        content: str | None = None,
        base_sha256: str | None = None,
        delete: bool = False,
        device: str | None = None,
    ) -> VaultPutResult:
        """Save one vault file to your account (or delete it with delete: true). Pass the
        sha256 you last synced as baseSha256; if the account changed since, nothing is written
        and status is "conflict" with the account's version, so you can keep both."""
        user_id = get_current_user_id(info.context["request"])
        if not delete and content is None:
            raise ValueError("Send content, or delete: true.")
        try:
            result = await asyncio.to_thread(
                vault_sync.put_file,
                info.context["db"],
                str(user_id),
                path,
                None if delete else content,
                base_sha256,
                device=device,
            )
        except vault_sync.VaultSyncError as exc:
            raise ValueError(str(exc)) from None
        return VaultPutResult(status=result["status"], file=to_sync_file(result["file"]))
