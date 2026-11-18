"""GraphQL types and mappers for universal search across ideas, people and the web."""

from datetime import datetime

import strawberry


@strawberry.type
class UniversalSearchIdeaResult:
    idea_id: str
    title: str
    snippet: str
    matched_in: str | None = None
    created_at: datetime
    user_id: str
    is_published: bool = False
    creator_name: str | None = None
    creator_avatar: str | None = None


@strawberry.type
class UniversalSearchWebSource:
    title: str
    url: str
    hostname: str | None = None


@strawberry.type
class UniversalSearchResults:
    query: str
    my_ideas: list[UniversalSearchIdeaResult]
    published_ideas: list[UniversalSearchIdeaResult]
    assistant_summary: str | None = None
    web_summary: str | None = None
    web_sources: list[UniversalSearchWebSource]
