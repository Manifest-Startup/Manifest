"""The person's Manifest as linked Markdown files for a local vault (ADR 0005)."""

import asyncio

import strawberry
from app.auth.current_user import get_current_user_id
from app.graphql.types.vault import (
    CitedDocument,
    IdeaKnowledgeGraph,
    KnowledgeConcept,
    KnowledgeIdeaRef,
    KnowledgePassage,
    VaultExport,
    VaultFile,
)
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

    @strawberry.field
    async def idea_knowledge_graph(
        self, info: strawberry.Info, idea_id: str
    ) -> IdeaKnowledgeGraph | None:
        """One of your ideas as a knowledge graph: the note's sentences and your interview
        answers as citable passages, the concepts they share with your other ideas, and every
        document with [[wiki-link]] citations back to the original idea note. Built live, so it
        grows as you answer interview questions and documents are generated. Owner only."""
        user_id = get_current_user_id(info.context["request"])
        graph = await asyncio.to_thread(
            vault_service.idea_knowledge_graph, info.context["db"], str(user_id), idea_id
        )
        if graph is None:
            return None
        titles, targets = graph["titles"], graph["targets"]

        def ref(iid: str, concepts: list[str] | None = None) -> KnowledgeIdeaRef:
            return KnowledgeIdeaRef(
                idea_id=iid, title=titles[iid], path=targets[iid], concepts=concepts or []
            )

        return IdeaKnowledgeGraph(
            idea_id=graph["idea_id"],
            idea_path=graph["idea_target"],
            passages=[KnowledgePassage(**p) for p in graph["passages"]],
            concepts=[
                KnowledgeConcept(
                    label=c["label"],
                    path=c["path"],
                    passage_ids=c["passages"],
                    document_types=c["documents"],
                    ideas=[ref(i) for i in c["ideas"]],
                )
                for c in graph["concepts"]
            ],
            related=[ref(r["idea_id"], r["concepts"]) for r in graph["related"]],
            documents=[
                CitedDocument(document_type=k, markdown=v) for k, v in graph["documents"].items()
            ],
        )
