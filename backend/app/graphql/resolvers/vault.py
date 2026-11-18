"""The person's Manifest as linked Markdown files for a local vault (ADR 0005)."""

import asyncio

import strawberry
from app.auth.current_user import get_current_user_id
from app.graphql.types.vault import VaultExport, VaultFile
from app.services.ideas import vault as vault_service


@strawberry.type
class VaultQuery:
    @strawberry.field
    async def vault_export(
        self, info: strawberry.Info, since_updated_at: str | None = None
    ) -> VaultExport:
        """Your ideas, documents, canvas, interviews and skills as Obsidian-ready Markdown files with
        frontmatter and [[wiki-links]] (a knowledge graph). Write them into a local vault with the
        plugin's manifest_vault.py; pass sinceUpdatedAt to get only ideas changed since then."""
        user_id = get_current_user_id(info.context["request"])
        data = await asyncio.to_thread(
            vault_service.build_vault, info.context["db"], str(user_id), since_updated_at
        )
        return VaultExport(
            generated_at=data["generated_at"],
            root=data["root"],
            idea_count=data["idea_count"],
            files=[
                VaultFile(path=f["path"], content=f["content"], updated_at=f["updated_at"])
                for f in data["files"]
            ],
        )
