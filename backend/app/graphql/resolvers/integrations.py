"""GraphQL resolvers for third-party integrations and your own OpenAI key."""

import asyncio
from datetime import datetime

import strawberry
from app.auth.current_user import get_current_user_id
from app.graphql.types.integrations import (
    AiKeyStatus,
    ConnectIntegrationInput,
    Integration,
    IntegrationConnection,
)
from app.utils.logger import logger


def _visible_integrations(rows: list[dict]) -> list[dict]:
    """Integrations shown in the UI; the BYOK OpenAI key is exposed only via aiKeyStatus."""
    return [row for row in rows if row.get("service_id") != "openai"]


def _ai_key_status(user_id: str) -> AiKeyStatus:
    from app.services.ai.credentials import platform_key
    from app.services.ai.user_keys import key_last4

    last4 = key_last4(user_id)
    if last4:
        return AiKeyStatus(configured=True, source="user", last4=last4)
    if platform_key():
        return AiKeyStatus(configured=True, source="platform")
    return AiKeyStatus(configured=False, source="none")


@strawberry.type
class IntegrationsQuery:
    @strawberry.field
    async def ai_key_status(self, info: strawberry.Info) -> AiKeyStatus:
        """Whether you have your own OpenAI key saved (never the key itself)."""
        user_id = get_current_user_id(info.context["request"])
        return await asyncio.to_thread(_ai_key_status, str(user_id))

    @strawberry.field
    async def integrations(self, info: strawberry.Info) -> list[Integration]:
        """Your connected integrations (GitHub, Google and others); credentials are never returned."""
        user_id = get_current_user_id(info.context["request"])
        response = (
            info.context["db"].table("integrations").select("*").eq("user_id", user_id).execute()
        )
        if not response.data:
            return []
        integrations = []
        for integration_data in _visible_integrations(response.data):
            integration_fields = {field.name for field in Integration.__dataclass_fields__.values()}
            filtered_data = {k: v for k, v in integration_data.items() if k in integration_fields}
            # Don't expose sensitive tokens in the response
            if "access_token" in filtered_data:
                filtered_data["access_token"] = "***" if filtered_data["access_token"] else None
            if "refresh_token" in filtered_data:
                filtered_data["refresh_token"] = "***" if filtered_data["refresh_token"] else None
            # Convert connected_at from string to datetime if needed
            if "connected_at" in filtered_data:
                val = filtered_data["connected_at"]
                if isinstance(val, str):
                    try:
                        filtered_data["connected_at"] = datetime.fromisoformat(
                            val.replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError) as e:
                        logger.warning(f"[integrations] Failed to parse connected_at '{val}': {e}")
                        filtered_data["connected_at"] = datetime.utcnow()
                elif val is None:
                    filtered_data["connected_at"] = datetime.utcnow()
            else:
                filtered_data["connected_at"] = datetime.utcnow()
            # Also handle expires_at if it's a string
            if "expires_at" in filtered_data and filtered_data["expires_at"] is not None:
                val = filtered_data["expires_at"]
                if isinstance(val, str):
                    try:
                        filtered_data["expires_at"] = datetime.fromisoformat(
                            val.replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError):
                        filtered_data["expires_at"] = None
            integrations.append(Integration(**filtered_data))
        return integrations

    @strawberry.field
    async def integration(self, info: strawberry.Info, service_id: str) -> Integration | None:
        """One connected integration by serviceId; credentials are never returned."""
        user_id = get_current_user_id(info.context["request"])
        response = (
            info.context["db"]
            .table("integrations")
            .select("*")
            .eq("user_id", user_id)
            .eq("service_id", service_id)
            .single()
            .execute()
        )
        if not response.data:
            return None
        integration_fields = {field.name for field in Integration.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in response.data.items() if k in integration_fields}
        # Don't expose sensitive tokens in the response
        if "access_token" in filtered_data:
            filtered_data["access_token"] = "***" if filtered_data["access_token"] else None
        if "refresh_token" in filtered_data:
            filtered_data["refresh_token"] = "***" if filtered_data["refresh_token"] else None
        # Convert connected_at from string to datetime if needed
        if "connected_at" in filtered_data:
            val = filtered_data["connected_at"]
            if isinstance(val, str):
                try:
                    filtered_data["connected_at"] = datetime.fromisoformat(
                        val.replace("Z", "+00:00")
                    )
                except (ValueError, TypeError) as e:
                    logger.warning(f"[integration] Failed to parse connected_at '{val}': {e}")
                    filtered_data["connected_at"] = datetime.utcnow()
            elif val is None:
                filtered_data["connected_at"] = datetime.utcnow()
        else:
            filtered_data["connected_at"] = datetime.utcnow()
        # Also handle expires_at if it's a string
        if "expires_at" in filtered_data and filtered_data["expires_at"] is not None:
            val = filtered_data["expires_at"]
            if isinstance(val, str):
                try:
                    filtered_data["expires_at"] = datetime.fromisoformat(val.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    filtered_data["expires_at"] = None
        return Integration(**filtered_data)


@strawberry.type
class IntegrationsMutation:
    @strawberry.mutation
    async def save_openai_api_key(self, info: strawberry.Info, api_key: str) -> AiKeyStatus:
        """Store the customer's own OpenAI key (validated, encrypted at rest)."""
        from app.services.ai.user_keys import InvalidOpenAIKeyError, save_user_key

        user_id = str(get_current_user_id(info.context["request"]))
        try:
            await asyncio.to_thread(save_user_key, user_id, api_key)
        except InvalidOpenAIKeyError as exc:
            raise Exception(str(exc)) from None
        info.context["request"].state.openai_key = None  # re-resolve on next AI call
        return await asyncio.to_thread(_ai_key_status, user_id)

    @strawberry.mutation
    async def remove_openai_api_key(self, info: strawberry.Info) -> AiKeyStatus:
        """Remove your saved OpenAI key; AI features stop until you add one again."""
        from app.services.ai.user_keys import delete_user_key

        user_id = str(get_current_user_id(info.context["request"]))
        await asyncio.to_thread(delete_user_key, user_id)
        return await asyncio.to_thread(_ai_key_status, user_id)

    @strawberry.mutation
    async def connect_integration(
        self, info: strawberry.Info, input: ConnectIntegrationInput
    ) -> Integration:
        """Connect an integration with provider tokens."""
        user_id = get_current_user_id(info.context["request"])

        # Service name mapping (you can expand this)
        service_names = {
            "google": "Google",
            "apple": "Apple",
            "meta": "Meta",
            "reddit": "Reddit",
            "x": "X (Twitter)",
            "zapier": "Zapier",
            "n8n": "n8n",
            "canva": "Canva",
            "figma": "Figma",
            "openai": "OpenAI",
            "github": "GitHub",
            "microsoft": "Microsoft",
            "asana": "Asana",
            "notion": "Notion",
        }

        service_name = service_names.get(input.service_id, input.service_id.title())

        integration_data = {
            "user_id": user_id,
            "service_id": input.service_id,
            "service_name": service_name,
            "access_token": input.access_token,
            "refresh_token": input.refresh_token,
            "expires_at": input.expires_at.isoformat() if input.expires_at else None,
            "connected_at": datetime.utcnow().isoformat(),
            "metadata": input.metadata,
        }

        # Check if integration already exists
        existing = (
            info.context["db"]
            .table("integrations")
            .select("*")
            .eq("user_id", user_id)
            .eq("service_id", input.service_id)
            .execute()
        )

        if existing.data and len(existing.data) > 0:
            # Update existing integration
            response = (
                info.context["db"]
                .table("integrations")
                .update(integration_data)
                .eq("user_id", user_id)
                .eq("service_id", input.service_id)
                .execute()
            )
        else:
            # Create new integration
            import uuid

            integration_data["integration_id"] = str(uuid.uuid4())
            response = info.context["db"].table("integrations").insert(integration_data).execute()

        if not response.data:
            raise Exception("Failed to connect integration")

        # Handle both single object and array responses
        result_data = (
            response.data[0]
            if isinstance(response.data, list) and len(response.data) > 0
            else response.data
        )
        integration_fields = {field.name for field in Integration.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in result_data.items() if k in integration_fields}
        # Don't expose sensitive tokens in the response
        if "access_token" in filtered_data:
            filtered_data["access_token"] = "***" if filtered_data["access_token"] else None
        if "refresh_token" in filtered_data:
            filtered_data["refresh_token"] = "***" if filtered_data["refresh_token"] else None
        if "connected_at" in filtered_data and isinstance(filtered_data["connected_at"], str):
            filtered_data["connected_at"] = datetime.fromisoformat(
                filtered_data["connected_at"].replace("Z", "+00:00")
            )
        if "expires_at" in filtered_data and isinstance(filtered_data["expires_at"], str):
            filtered_data["expires_at"] = datetime.fromisoformat(
                filtered_data["expires_at"].replace("Z", "+00:00")
            )
        return Integration(**filtered_data)

    @strawberry.mutation
    async def start_integration_connection(
        self, info: strawberry.Info, service_id: str, name: str | None = None
    ) -> IntegrationConnection:
        """Connect a partner (Notion, Stripe, any service) so it appears in Key Partners.
        Partners with their own sign-in return a connectUrl to approve in a browser."""
        import os

        from app.routes.oauth_routes import OAUTH_PROVIDERS
        from app.services.integrations.connections import start_connection
        from app.services.web.agent_content import SITE_ORIGIN

        user_id = get_current_user_id(info.context["request"])
        normalized = (service_id or "").strip().lower()
        config = OAUTH_PROVIDERS.get(normalized)
        oauth_ready = bool(config and os.getenv(config["client_id_env"]))
        try:
            result = await asyncio.to_thread(
                start_connection,
                info.context["db"],
                str(user_id),
                service_id,
                oauth_ready=oauth_ready,
                site_origin=os.getenv("PUBLIC_SITE_ORIGIN", SITE_ORIGIN),
                name=name,
            )
        except ValueError as exc:
            raise Exception(str(exc)) from exc
        return IntegrationConnection(
            service_id=result.service_id,
            status=result.status,
            message=result.message,
            connect_url=result.connect_url,
        )

    @strawberry.mutation
    async def disconnect_integration(self, info: strawberry.Info, service_id: str) -> bool:
        """Disconnect an integration (GitHub, Google and others) by serviceId."""
        user_id = get_current_user_id(info.context["request"])

        (
            info.context["db"]
            .table("integrations")
            .delete()
            .eq("user_id", user_id)
            .eq("service_id", service_id)
            .execute()
        )

        return True
