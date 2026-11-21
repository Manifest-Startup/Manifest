"""GraphQL types for customer discovery (``app.services.ideas.customer_discovery``)."""

from typing import Any

import strawberry
from strawberry.scalars import JSON


@strawberry.type
class CustomerDiscovery:
    """Where the founder's customer discovery stands. Say ``summary`` aloud; show the rest."""

    idea_id: str
    stage: str
    summary: str
    segment: str | None
    note_path: str
    demo: bool
    limitations: list[str]
    updated_at: str | None
    speaking_tip: str
    data: JSON


@strawberry.type
class DiscoveryCapability:
    name: str
    available: bool
    provider: str
    hint: str | None = None


@strawberry.type
class ApolloKeyStatus:
    """Whether you saved your own Apollo.io key (never the key itself)."""

    connected: bool
    last4: str | None = None


def map_discovery(idea_id: str, view: dict[str, Any]) -> CustomerDiscovery:
    return CustomerDiscovery(
        idea_id=idea_id,
        stage=view["stage"],
        summary=view["summary"],
        segment=view.get("segment"),
        note_path=view["notePath"],
        demo=bool(view.get("demo")),
        limitations=list(view.get("limitations") or []),
        updated_at=view.get("updatedAt"),
        speaking_tip=view["speakingTip"],
        data=view.get("data") or {},
    )
