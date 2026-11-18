"""GraphQL resolvers for your account, sessions, guest sessions and privacy status."""

import asyncio
import os
import uuid

import strawberry
from app.auth.current_user import (
    DEMO_MODE,
    get_current_session_id_optional,
    get_current_user_id,
    get_current_user_id_optional,
)
from app.graphql.resolvers.shared import _request_ip, _require_full_account, _user_agent
from app.graphql.types.account import (
    AccountUpdateInput,
    GuestSessionResult,
    PrivacyStatus,
    SessionInfo,
    User,
)
from app.security.cookies import clear_auth_cookies, set_auth_cookies
from app.services.compliance.security_audit import record_security_event
from app.services.identity.sessions import (
    list_user_sessions,
    revoke_all_other_sessions,
    revoke_session,
)
from app.utils.logger import logger

# Session configuration - uses PostgreSQL for user storage
SESSION_SECRET = os.getenv("SESSION_SECRET", "")


# Canonical skills taxonomy for the Manifest platform.
AVAILABLE_SKILLS: list[str] = [
    # Engineering
    "Full Stack Development",
    "Frontend Development",
    "Backend Development",
    "Mobile Development",
    "iOS Development",
    "Android Development",
    "DevOps / Cloud",
    "Data Engineering",
    "Machine Learning / AI",
    "Cybersecurity",
    "Blockchain / Web3",
    "Embedded Systems",
    # Product & Design
    "Product Management",
    "UX / UI Design",
    "Product Strategy",
    "Quality Assurance",
    "Technical Writing",
    # Business
    "Business Development",
    "Sales",
    "Marketing",
    "Growth Hacking",
    "Operations",
    "Finance / Accounting",
    "Fundraising",
    "Legal",
    "Human Resources",
    # Creative
    "Graphic Design",
    "Brand Design",
    "Video Production",
    "Copywriting",
    "Content Marketing",
    "SEO / SEM",
    "Social Media",
    # Data & Research
    "Data Analysis",
    "Data Science",
    "Market Research",
    "User Research",
]


def _set_browser_auth_session(info: strawberry.Info, token: str) -> None:
    response = info.context.get("response")
    request = info.context.get("request")
    if not response:
        return
    try:
        set_auth_cookies(response, token, request)
    except Exception as cookie_error:
        logger.warning("[auth_session] Failed to set auth cookies: %s", cookie_error)


def _load_user_auth_record(user_id: str) -> dict[str, object] | None:
    if not user_id:
        return None
    from app.db.database import get_db_connection

    with get_db_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
                SELECT user_id, email, auth_provider,
                       COALESCE(is_guest, FALSE) AS is_guest,
                       deletion_requested_at
                FROM users
                WHERE user_id = %s
                """,
            (user_id,),
        )
        return cur.fetchone()


@strawberry.type
class AccountQuery:
    @strawberry.field
    async def me(self, info: strawberry.Info) -> User:
        """Your profile: name, username, email, bio, location, skills and picture."""
        user_id = get_current_user_id(info.context["request"])

        # Sync DB call moved off the event loop (Phase 2): this resolver runs
        # on every page load, and a blocking .execute() here stalls every
        # in-flight request on the worker for the query's duration.
        def _load() -> User:
            response = (
                info.context["db"]
                .table("users")
                .select("*")
                .eq("user_id", user_id)
                .single()
                .execute()
            )
            if not response.data:
                raise Exception("User not found")
            user_data = response.data
            user_fields = {field.name for field in User.__dataclass_fields__.values()}
            filtered_user_data = {k: v for k, v in user_data.items() if k in user_fields}
            return User(**filtered_user_data)

        return await asyncio.to_thread(_load)

    @strawberry.field
    async def account(self, info: strawberry.Info) -> User:
        """Your account settings (same fields as me), for editing with update_account."""
        user_id = get_current_user_id(info.context["request"])

        # Off-loop for the same reason as `me` (fetched eagerly at app boot).
        def _load() -> User:
            response = (
                info.context["db"]
                .table("users")
                .select("*")
                .eq("user_id", user_id)
                .single()
                .execute()
            )
            if not response.data:
                raise Exception("User not found")
            user_data = response.data
            user_fields = {field.name for field in User.__dataclass_fields__.values()}
            filtered_user_data = {k: v for k, v in user_data.items() if k in user_fields}
            return User(**filtered_user_data)

        return await asyncio.to_thread(_load)

    @strawberry.field
    async def my_sessions(self, info: strawberry.Info) -> list[SessionInfo]:
        """Every signed-in session on your account (browsers, CLI, agents), with the current one marked."""
        user_id = get_current_user_id(info.context["request"])
        current_session_id = get_current_session_id_optional(info.context["request"])
        sessions = list_user_sessions(user_id, current_session_id)
        return [
            SessionInfo(
                session_id=str(item.get("session_id") or ""),
                current=bool(item.get("current")),
                created_at=item.get("created_at"),
                expires_at=item.get("expires_at"),
                revoked_at=item.get("revoked_at"),
                last_seen_at=item.get("last_seen_at"),
                request_ip=item.get("request_ip"),
                user_agent=item.get("user_agent"),
                kind=str(item.get("kind") or "browser"),
            )
            for item in sessions
        ]

    @strawberry.field
    async def privacy_status(self, info: strawberry.Info) -> PrivacyStatus:
        """Your privacy choices and any pending data requests."""
        user_id = get_current_user_id(info.context["request"])
        user_row = _load_user_auth_record(user_id) or {}
        return PrivacyStatus(
            export_available=True,
            deletion_requested_at=user_row.get("deletion_requested_at"),
            guest_retention_days=30,
        )

    @strawberry.field
    def available_skills(self) -> list[str]:
        """Return the canonical list of skills available on the platform."""
        return AVAILABLE_SKILLS


@strawberry.type
class AccountMutation:
    @strawberry.mutation
    async def update_account(self, info: strawberry.Info, input: AccountUpdateInput) -> User:
        """Update your profile: name, username, bio, location, skills or picture URL."""
        user_id = get_current_user_id(info.context["request"])
        update_data = {k: v for k, v in vars(input).items() if v is not None}
        if not update_data:
            raise Exception("No valid fields provided for update")

        # Filter out fields that don't exist in the users table
        allowed_fields = [
            "email",
            "username",
            "first_name",
            "last_name",
            "country",
            "bio",
            "address",
            "state",
            "gravatar_hash",
            "profile_picture_url",
            "skills",
        ]
        filtered_update_data = {k: v for k, v in update_data.items() if k in allowed_fields}

        if not filtered_update_data:
            raise Exception("No updatable fields provided")

        response = (
            info.context["db"]
            .table("users")
            .update(filtered_update_data)
            .eq("user_id", user_id)
            .execute()
        )
        if not response.data or len(response.data) == 0:
            raise Exception("User not found or not updated")
        user_fields = {field.name for field in User.__dataclass_fields__.values()}
        return User(**{k: v for k, v in response.data[0].items() if k in user_fields})

    @strawberry.mutation
    async def start_guest_session(self, info: strawberry.Info) -> GuestSessionResult:
        """Create a server-backed guest user, set session cookie, return one-time merge secret."""
        if DEMO_MODE:
            raise Exception("Guest sessions are not available in demo mode.")

        import secrets

        from app.auth.current_user import create_session_token
        from app.db.database import get_db_connection
        from app.services.identity.guest_workspace import check_guest_start_rate_limit

        request = info.context["request"]
        client = getattr(request, "client", None)
        try:
            check_guest_start_rate_limit(getattr(client, "host", None) if client else None)
        except Exception:
            raise

        # Two attempts with fresh identifiers each time: this is the landing
        # page's try-before-signup CTA, and production shows intermittent
        # transient DB failures on the first insert (subsequent attempts
        # succeed). A fresh UUID per attempt keeps retries conflict-free; a
        # half-completed first attempt at worst leaves one orphan guest row
        # that the 30-day TTL cleans up.
        last_error: Exception | None = None
        for attempt in range(2):
            guest_id = str(uuid.uuid4())
            merge_secret = secrets.token_urlsafe(32)
            email = f"guest+{guest_id}@guest.manifest"

            try:
                with get_db_connection() as conn, conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO users (
                            user_id, email, auth_provider, is_guest,
                            guest_merge_secret, guest_created_at, guest_expires_at, created_at
                        )
                        VALUES (%s, %s, 'guest', TRUE, %s, NOW(), NOW() + INTERVAL '30 days', NOW())
                        """,
                        (guest_id, email.lower(), merge_secret),
                    )
                token = create_session_token(
                    guest_id, email=email.lower(), request=info.context.get("request")
                )
                _set_browser_auth_session(info, token)

                logger.info("[start_guest_session] Created guest user_id=%s", guest_id)
                record_security_event(
                    "guest_session_started",
                    user_id=guest_id,
                    request_ip=_request_ip(info),
                    actor_id=guest_id,
                    actor_type="guest",
                    action="guest_session_start",
                    target_type="user",
                    target_id=guest_id,
                    outcome="success",
                    user_agent=_user_agent(info),
                )
                return GuestSessionResult(
                    user_id=guest_id,
                    email=email,
                    token=token,
                    merge_secret=merge_secret,
                )
            except Exception as e:
                last_error = e
                logger.error(
                    "[start_guest_session] Attempt %s failed (%s): %s",
                    attempt + 1,
                    type(e).__name__,
                    e,
                )

        raise Exception("Could not start guest session") from last_error

    @strawberry.mutation
    async def logout_user(self, info: strawberry.Info) -> bool:
        """Clear auth cookies so the client is fully logged out.

        Session tokens are stateless JWTs, so we don't need to revoke them
        server-side – simply removing the cookie (and any client-side storage)
        is enough to end the session from the browser's perspective.
        """
        request = info.context["request"]
        user_id = get_current_user_id_optional(request)
        current_session_id = get_current_session_id_optional(request)
        if user_id and current_session_id:
            revoke_session(current_session_id, user_id)
            record_security_event(
                "logout",
                user_id=user_id,
                request_ip=_request_ip(info),
                session_id=current_session_id,
                actor_id=user_id,
                actor_type="user",
                action="logout",
                target_type="session",
                target_id=str(current_session_id) if current_session_id else None,
                outcome="success",
                user_agent=_user_agent(info),
            )
        response = info.context["response"]
        clear_auth_cookies(response, request)
        return True

    @strawberry.mutation
    async def revoke_account_session(self, info: strawberry.Info, session_id: str) -> bool:
        """Sign out one session (a browser, the CLI or an agent) by sessionId."""
        user_id = get_current_user_id(info.context["request"])
        current_session_id = get_current_session_id_optional(info.context["request"])
        if current_session_id and session_id == current_session_id:
            raise Exception("Use logout to end the current session.")
        revoked = revoke_session(session_id, user_id)
        if revoked:
            record_security_event(
                "session_revoked",
                user_id=user_id,
                request_ip=_request_ip(info),
                actor_id=user_id,
                actor_type="user",
                action="session_revoke",
                target_type="session",
                target_id=str(session_id),
                outcome="success",
                user_agent=_user_agent(info),
                metadata={"target_session_id": session_id},
            )
        return revoked

    @strawberry.mutation
    async def revoke_other_account_sessions(self, info: strawberry.Info) -> int:
        """Sign out every session except the current one; returns how many."""
        user_id = get_current_user_id(info.context["request"])
        current_session_id = get_current_session_id_optional(info.context["request"])
        revoked = revoke_all_other_sessions(user_id, current_session_id)
        record_security_event(
            "other_sessions_revoked",
            user_id=user_id,
            request_ip=_request_ip(info),
            session_id=current_session_id,
            actor_id=user_id,
            actor_type="user",
            action="session_revoke_others",
            target_type="user",
            target_id=user_id,
            outcome="success",
            user_agent=_user_agent(info),
            metadata={"revoked_count": revoked},
        )
        return revoked

    @strawberry.mutation
    async def request_account_deletion(
        self,
        info: strawberry.Info,
        confirm_email: str,
    ) -> bool:
        """Request permanent deletion of your account; confirmEmail must be your account email."""
        user_id = _require_full_account(info.context["db"], info.context["request"])
        user_row = _load_user_auth_record(user_id)
        if not user_row:
            raise Exception("User not found.")
        expected_email = str(user_row.get("email") or "").strip().lower()
        if (confirm_email or "").strip().lower() != expected_email:
            raise Exception("Enter your account email to confirm deletion.")

        from app.db.database import get_db_connection

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET deletion_requested_at = NOW() WHERE user_id = %s",
                    (user_id,),
                )
            conn.commit()
        revoke_all_other_sessions(user_id, None)
        clear_auth_cookies(info.context["response"], info.context.get("request"))
        record_security_event(
            "account_deletion_requested",
            user_id=user_id,
            request_ip=_request_ip(info),
            action="account_deletion_request",
            target_type="user",
            target_id=user_id,
            outcome="success",
            user_agent=_user_agent(info),
        )
        return True
