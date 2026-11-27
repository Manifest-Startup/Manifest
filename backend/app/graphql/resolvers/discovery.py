"""GraphQL resolvers for customer discovery: research, prospects, outreach, Gmail drafts.

Thin on purpose: the rules live in ``app.services.ideas.customer_discovery``. Every field
works on an idea the caller owns or edits; the work is saved in the caller's own vault.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import strawberry
from app.auth.current_user import get_current_user_id
from app.graphql.types.discovery import (
    ApolloKeyStatus,
    CustomerDiscovery,
    DiscoveryCapability,
    map_discovery,
)
from strawberry.scalars import JSON


async def _idea_for(info: strawberry.Info, idea_id: str, *, write: bool) -> tuple[str, dict]:
    from app.services.ideas.collaboration import CollaborationService

    user_id = str(get_current_user_id(info.context["request"]))
    db = info.context["db"]
    role = await CollaborationService(db).get_user_role(idea_id, user_id)
    allowed = ("owner", "editor") if write else ("owner", "editor", "viewer", "commenter")
    if role not in allowed:
        raise Exception("Idea not found or you don't have permission to work on it")
    rows = (
        db.table("ideas")
        .select("idea_id, title, description")
        .eq("idea_id", idea_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise Exception("Idea not found or you don't have permission to work on it")
    return user_id, dict(rows[0])


def _enforce_cap(db: Any, user_id: str) -> None:
    from app.services.ai import cost_tracking

    try:
        cost_tracking.enforce_cap_or_raise(db=db, user_id=user_id, agent_kind="customer_discovery")
    except cost_tracking.CapBlockedError as exc:
        raise Exception(str(exc)) from exc


async def _run(
    info: strawberry.Info,
    idea_id: str,
    stage: str,
    step: Callable[[Any, str, dict], dict],
    *,
    uses_ai: bool,
) -> CustomerDiscovery:
    from app.services.ideas import customer_discovery as cd
    from app.services.integrations import discovery_connectors as connectors

    user_id, idea = await _idea_for(info, idea_id, write=True)
    db = info.context["db"]
    if uses_ai:
        _enforce_cap(db, user_id)

    def work() -> dict:
        if uses_ai:
            return cd.run_tracked(
                db=db, user_id=user_id, idea_id=idea_id, stage=stage,
                work=lambda: step(db, user_id, idea),
            )  # fmt: skip
        return step(db, user_id, idea)

    try:
        result = await asyncio.to_thread(work)
    except (cd.DiscoveryError, connectors.ConnectorUnavailable, connectors.ProviderError) as exc:
        raise Exception(str(exc)) from exc
    return map_discovery(idea_id, cd.view(result["state"], limitations=result.get("limitations")))


def _ai_layer() -> Any:
    from app.managers.manifest_manager import manifest_manager

    return manifest_manager.ai_layer


async def _apollo_status(user_id: str) -> ApolloKeyStatus:
    from app.services.integrations import discovery_connectors as connectors

    last4 = await asyncio.to_thread(connectors.apollo_key_last4, user_id)
    return ApolloKeyStatus(connected=bool(last4), last4=last4)


@strawberry.type
class DiscoveryQuery:
    @strawberry.field
    async def apollo_key_status(self, info: strawberry.Info) -> ApolloKeyStatus:
        """Whether you saved your own Apollo.io key for finding prospects (never the key)."""
        return await _apollo_status(str(get_current_user_id(info.context["request"])))

    @strawberry.field
    async def customer_discovery(self, info: strawberry.Info, idea_id: str) -> CustomerDiscovery:
        """Read the customer discovery saved for an idea: research, segments, prospects and
        prepared emails. Cheap; call it before redoing any step."""
        from app.services.ideas import customer_discovery as cd

        user_id, idea = await _idea_for(info, idea_id, write=False)
        state = await asyncio.to_thread(cd.load_state, info.context["db"], user_id, idea)
        return map_discovery(idea_id, cd.view(state))

    @strawberry.field
    async def discovery_capabilities(self, info: strawberry.Info) -> list[DiscoveryCapability]:
        """Which research and email connectors work right now (web search, Apollo.io, Gmail)
        and how to enable the rest."""
        from app.services.integrations import discovery_connectors as connectors

        user_id = str(get_current_user_id(info.context["request"]))
        status = await asyncio.to_thread(
            connectors.capability_status, info.context["db"], user_id, _ai_layer()
        )
        return [
            DiscoveryCapability(
                name=name, available=s["available"], provider=s["provider"], hint=s["hint"]
            )
            for name, s in status.items()
        ]


@strawberry.type
class DiscoveryMutation:
    @strawberry.mutation
    async def save_apollo_api_key(self, info: strawberry.Info, api_key: str) -> ApolloKeyStatus:
        """Save your own Apollo.io API key (verified with Apollo, encrypted at rest). Prospect
        searches then use your Apollo account and credits. Never ask for it in chat: the person
        adds it in Account → AI settings."""
        from app.services.integrations import discovery_connectors as connectors

        user_id = str(get_current_user_id(info.context["request"]))
        try:
            await asyncio.to_thread(connectors.save_apollo_key, user_id, api_key)
        except connectors.InvalidApolloKeyError as exc:
            raise Exception(str(exc)) from None
        return await _apollo_status(user_id)

    @strawberry.mutation
    async def remove_apollo_api_key(self, info: strawberry.Info) -> ApolloKeyStatus:
        """Remove your saved Apollo.io key; prospects then come from web search only."""
        from app.services.integrations import discovery_connectors as connectors

        user_id = str(get_current_user_id(info.context["request"]))
        await asyncio.to_thread(connectors.remove_apollo_key, user_id)
        return await _apollo_status(user_id)

    @strawberry.mutation
    async def research_market(
        self,
        info: strawberry.Info,
        idea_id: str,
        notes: str | None = None,
        website: str | None = None,
        refresh: bool = False,
    ) -> CustomerDiscovery:
        """Research the idea's market on the live web: competitors and their gaps, customer
        complaints, willingness to pay, three customer segments with a recommended first one, and
        a business model (as hypotheses). Pass what the founder just said as notes, and the
        product's site as website. Reuses research under a week old unless refresh is true.
        Uses your OpenAI key; takes about a minute."""
        from app.services.ideas import customer_discovery as cd

        return await _run(
            info,
            idea_id,
            "research",
            lambda db, uid, idea: cd.research_market(
                db=db,
                ai_layer=_ai_layer(),
                user_id=uid,
                idea=idea,
                notes=notes,
                website=website,
                refresh=refresh,
            ),  # fmt: skip
            uses_ai=True,
        )

    @strawberry.mutation
    async def find_prospects(
        self,
        info: strawberry.Info,
        idea_id: str,
        segment: str | None = None,
        count: int = 5,
        exclude: list[str] | None = None,
        more: bool = False,
    ) -> CustomerDiscovery:
        """Find real companies that might buy, for the chosen segment (default: the recommended
        one), each with evidence of need, an explainable score and what is still unverified.
        Uses Apollo.io when the server has it, otherwise web search; websites are checked.
        more=true adds to the current list; exclude skips companies by name. About a minute."""
        from app.services.ideas import customer_discovery as cd

        return await _run(
            info,
            idea_id,
            "prospects",
            lambda db, uid, idea: cd.find_prospects(
                db=db,
                ai_layer=_ai_layer(),
                user_id=uid,
                idea=idea,
                segment=segment,
                count=count,
                exclude=exclude,
                more=more,
            ),  # fmt: skip
            uses_ai=True,
        )

    @strawberry.mutation
    async def exclude_prospects(
        self, info: strawberry.Info, idea_id: str, names: list[str]
    ) -> CustomerDiscovery:
        """Drop prospects by name (or id) and never suggest them again for this idea."""
        from app.services.ideas import customer_discovery as cd

        return await _run(
            info,
            idea_id,
            "exclude",
            lambda db, uid, idea: cd.exclude_prospects(db=db, user_id=uid, idea=idea, names=names),
            uses_ai=False,
        )

    @strawberry.mutation
    async def draft_outreach(
        self,
        info: strawberry.Info,
        idea_id: str,
        prospects: list[str] | None = None,
        sender_name: str | None = None,
    ) -> CustomerDiscovery:
        """Write one short, honest customer-discovery message per prospect (all of them, or the
        names/ids given), from the evidence only and checked against the outreach rules. Those
        with a verified address wait in Messages for the person's yes; nothing is sent. Uses
        your OpenAI key."""
        from app.services.ideas import customer_discovery as cd

        return await _run(
            info,
            idea_id,
            "outreach",
            lambda db, uid, idea: cd.draft_outreach(
                db=db,
                ai_layer=_ai_layer(),
                user_id=uid,
                idea=idea,
                prospect_ids=prospects,
                sender_name=sender_name,
            ),  # fmt: skip
            uses_ai=True,
        )

    @strawberry.mutation
    async def save_customer_discovery(
        self, info: strawberry.Info, idea_id: str, work: JSON
    ) -> CustomerDiscovery:
        """Save customer discovery you researched yourself (use this when the person has no
        OpenAI key and you have web search). work may hold research, segment, icp, prospects
        (append: true to add), outreach and sender_name, in the shapes customer_discovery
        returns. Every prospect needs a source URL; kind "person" for an individual (creator,
        freelancer, consumer). contact.source must be the public page that shows the address
        (it is read to check), or contact.verified_by "apollo"/"person". Outreach that breaks
        the rules (see the manifest-customers skill) comes back in limitations to rewrite;
        the rest waits in Messages for the person's yes (queue: false to hold it)."""
        from app.services.ideas import customer_discovery as cd

        payload = work if isinstance(work, dict) else {}
        return await _run(
            info,
            idea_id,
            "agent",
            lambda db, uid, idea: cd.save_agent_work(db=db, user_id=uid, idea=idea, work=payload),
            uses_ai=False,
        )

    @strawberry.mutation
    async def queue_outreach(
        self, info: strawberry.Info, idea_id: str, prospects: list[str] | None = None
    ) -> CustomerDiscovery:
        """Put the prepared messages (all, or the names/ids given) in Messages, each waiting for
        the person's yes; one already waiting is updated, one already sent is left alone.
        Drafting and saving already do this, so call it only to retry. Nothing is sent."""
        from app.services.ideas import customer_discovery as cd

        return await _run(
            info,
            idea_id,
            "queue",
            lambda db, uid, idea: cd.queue_outreach(
                db=db, user_id=uid, idea=idea, prospect_ids=prospects
            ),
            uses_ai=False,
        )

    @strawberry.mutation
    async def set_outreach_recipient(
        self, info: strawberry.Info, idea_id: str, prospect: str, address: str
    ) -> CustomerDiscovery:
        """Use the email address or Open Media @handle the person gave for a prospect (name or
        id). Only an address the person said; never one you guessed. Its message then waits in
        Messages for their yes."""
        from app.services.ideas import customer_discovery as cd

        return await _run(
            info,
            idea_id,
            "recipient",
            lambda db, uid, idea: cd.set_recipient(
                db=db, user_id=uid, idea=idea, prospect=prospect, address=address
            ),
            uses_ai=False,
        )

    @strawberry.mutation
    async def create_outreach_email_drafts(
        self, info: strawberry.Info, idea_id: str, prospects: list[str] | None = None
    ) -> CustomerDiscovery:
        """Save the prepared emails (all, or the names/ids given) as drafts in the person's
        connected Gmail. Never sends; emails already in Gmail are not duplicated. Ask first.
        Without a Gmail connection nothing is saved: every email in customer_discovery has a
        compose_url ("Open in Gmail") that opens it pre-filled in the person's own Gmail."""
        from app.services.ideas import customer_discovery as cd

        return await _run(
            info,
            idea_id,
            "gmail",
            lambda db, uid, idea: cd.create_gmail_drafts(
                db=db, user_id=uid, idea=idea, prospect_ids=prospects
            ),
            uses_ai=False,
        )
