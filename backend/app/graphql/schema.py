"""Manifest GraphQL schema: the root ``Query`` / ``Mutation`` and the auth extension.

Resolvers live in ``app.graphql.resolvers.<domain>`` as ``<Domain>Query`` /
``<Domain>Mutation`` mixins; their types and mappers live in
``app.graphql.types.<domain>``. This module only composes them, enforces
default-deny auth on every top-level field and builds ``schema``.
"""

import os

import strawberry
from app.auth.current_user import get_current_user_id, get_current_user_id_optional
from app.graphql.error_masking import infrastructure_error_masker

# Re-exported for callers that import them from here (worker, tests).
from app.graphql.pitch_reel_types import map_pitch_reel  # noqa: F401
from app.graphql.resolvers.account import (  # noqa: F401
    AVAILABLE_SKILLS,
    AccountMutation,
    AccountQuery,
)
from app.graphql.resolvers.admin import AdminMutation, AdminQuery
from app.graphql.resolvers.canvas import CanvasMutation, CanvasQuery
from app.graphql.resolvers.collaboration import CollaborationMutation, CollaborationQuery
from app.graphql.resolvers.costs import CostsMutation, CostsQuery
from app.graphql.resolvers.discovery import DiscoveryMutation, DiscoveryQuery
from app.graphql.resolvers.documents import (  # noqa: F401
    DocumentsMutation,
    DocumentsQuery,
    _generate_documents_for_idea,
    _get_pitch_deck,
    _get_product_requirements_document,
    _get_provisional_patent,
    _start_background_generation,
)
from app.graphql.resolvers.github import GithubMutation, GithubQuery
from app.graphql.resolvers.goals import GoalsMutation, GoalsQuery
from app.graphql.resolvers.ideas import IdeasMutation, IdeasQuery
from app.graphql.resolvers.integrations import (  # noqa: F401
    IntegrationsMutation,
    IntegrationsQuery,
    _visible_integrations,
)
from app.graphql.resolvers.investments import InvestmentsMutation, InvestmentsQuery
from app.graphql.resolvers.memory import MemoryMutation, MemoryQuery
from app.graphql.resolvers.messaging import MessagingMutation, MessagingQuery
from app.graphql.resolvers.pitch_reels import PitchReelsMutation, PitchReelsQuery
from app.graphql.resolvers.qualification import QualificationMutation, QualificationQuery
from app.graphql.resolvers.search import SearchQuery
from app.graphql.resolvers.shared import _display_name  # noqa: F401
from app.graphql.resolvers.social import SocialMutation, SocialQuery
from app.graphql.resolvers.survey import SurveyMutation, SurveyQuery
from app.graphql.resolvers.vault import VaultQuery
from app.graphql.resolvers.vault_sync import VaultSyncMutation, VaultSyncQuery
from app.graphql.resolvers.voice import VoiceMutation, VoiceQuery
from app.graphql.types.account import AccountUpdateInput  # noqa: F401
from app.graphql.types.integrations import ConnectIntegrationInput, Integration  # noqa: F401
from app.graphql.types.survey import SubmitSurveyInput  # noqa: F401
from app.security.permissions import resolve_principal
from app.utils.logger import logger
from fastapi import HTTPException
from strawberry.extensions import DisableIntrospection as _DisableIntrospection
from strawberry.extensions import MaxAliasesLimiter as _MaxAliasesLimiter
from strawberry.extensions import MaxTokensLimiter as _MaxTokensLimiter
from strawberry.extensions import QueryDepthLimiter as _QueryDepthLimiter
from strawberry.extensions import SchemaExtension

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    logger.warning("DATABASE_URL is not set. Database operations may fail.")


# Mixin order sets the field order of the schema (first domain's fields first).
@strawberry.type
class Query(
    AccountQuery,
    DocumentsQuery,
    IdeasQuery,
    SurveyQuery,
    IntegrationsQuery,
    GithubQuery,
    SocialQuery,
    InvestmentsQuery,
    PitchReelsQuery,
    SearchQuery,
    MessagingQuery,
    CollaborationQuery,
    QualificationQuery,
    CostsQuery,
    CanvasQuery,
    DiscoveryQuery,
    GoalsQuery,
    AdminQuery,
    VoiceQuery,
    VaultQuery,
    VaultSyncQuery,
    MemoryQuery,
):
    pass


@strawberry.type
class Mutation(
    IdeasMutation,
    IntegrationsMutation,
    GithubMutation,
    AccountMutation,
    SurveyMutation,
    InvestmentsMutation,
    SocialMutation,
    PitchReelsMutation,
    DocumentsMutation,
    MessagingMutation,
    CollaborationMutation,
    AdminMutation,
    QualificationMutation,
    CostsMutation,
    CanvasMutation,
    DiscoveryMutation,
    GoalsMutation,
    VoiceMutation,
    VaultSyncMutation,
    MemoryMutation,
):
    pass


def _request_principal(request, uid):
    """resolve_principal once per request and user (each root field asked)."""
    scope = getattr(request, "scope", None)
    cache = scope.setdefault("manifest.principal_cache", {}) if isinstance(scope, dict) else None
    if cache is not None and uid in cache:
        return cache[uid]
    try:
        principal = resolve_principal(uid)
    except Exception:
        principal = None
    if cache is not None:
        cache[uid] = principal
    return principal


class _DefaultDenyAuthExtension(SchemaExtension):
    """Default-deny authorization for every top-level Query/Mutation field.

    Strawberry doesn't have a notion of a global default permission, so we
    intercept every top-level resolve call here. A resolver listed in
    ``PUBLIC_FIELDS`` is allowed unauthenticated; anything else requires a
    valid session cookie / bearer token. Fields listed in
    ``FIELD_PERMISSIONS`` additionally require the named permission(s)
    from the RBAC catalog (`app.security.permissions`).

    The allowlists are intentionally explicit — every entry here was
    reviewed as an anonymous-safe or scope-bound operation. New fields
    default to authenticated; new sensitive fields should be added to
    ``FIELD_PERMISSIONS`` so they default-deny by RBAC, not just by auth.
    """

    PUBLIC_FIELDS = {
        # guest try-before-signup (signing in goes through /api/auth/open-media/*)
        "start_guest_session",
        "startGuestSession",
        "submit_contact_form",
        "submitContactForm",
        "submit_survey",
        "submitSurvey",
        # platform catalog (static skill pick-list for onboarding / idea forms)
        "available_skills",
        "availableSkills",
        # introspection / playground utility
        "__schema",
        "__type",
        "__typename",
    }

    # Map of top-level field name (snake_case and camelCase forms accepted
    # by Strawberry) -> required permission from the RBAC catalog. A
    # principal must hold the listed permission, or we 403 the field
    # before the resolver runs.
    FIELD_PERMISSIONS = {
        # --- Idea CRUD ---
        "ideas": "ideas.read",
        "idea": "ideas.read",
        "generation_job": "ideas.read",
        "generationJob": "ideas.read",
        "vaultExport": "ideas.read",
        "vault_files": "ideas.read",
        "vaultFiles": "ideas.read",
        "put_vault_file": "ideas.write",
        "putVaultFile": "ideas.write",
        # --- Memory (ADR 0021): the person's own Memory/ and Conversations/ vault files ---
        "recall": "ideas.read",
        "memories": "ideas.read",
        "remember": "ideas.write",
        "update_memory": "ideas.write",
        "updateMemory": "ideas.write",
        "forget_memory": "ideas.write",
        "forgetMemory": "ideas.write",
        "save_voice_conversation": "ideas.write",
        "saveVoiceConversation": "ideas.write",
        # --- Customer discovery (research, prospects, outreach drafts) ---
        "customer_discovery": "ideas.read",
        "customerDiscovery": "ideas.read",
        "discovery_capabilities": "ideas.read",
        "discoveryCapabilities": "ideas.read",
        "research_market": "ideas.write",
        "researchMarket": "ideas.write",
        "find_prospects": "ideas.write",
        "findProspects": "ideas.write",
        "exclude_prospects": "ideas.write",
        "excludeProspects": "ideas.write",
        "draft_outreach": "ideas.write",
        "draftOutreach": "ideas.write",
        "save_customer_discovery": "ideas.write",
        "saveCustomerDiscovery": "ideas.write",
        "create_outreach_email_drafts": "ideas.write",
        "createOutreachEmailDrafts": "ideas.write",
        "ideaKnowledgeGraph": "ideas.read",
        "idea_knowledge_graph": "ideas.read",
        "search_ideas": "ideas.read",
        "searchIdeas": "ideas.read",
        "shared_ideas": "ideas.read",
        "sharedIdeas": "ideas.read",
        "create_idea": "ideas.write",
        "createIdea": "ideas.write",
        "update_idea": "ideas.write",
        "updateIdea": "ideas.write",
        "delete_idea": "ideas.write",
        "deleteIdea": "ideas.write",
        "import_ideas": "ideas.write",
        "importIdeas": "ideas.write",
        "export_ideas": "ideas.read",
        "exportIdeas": "ideas.read",
        # --- Documents ---
        "documents": "documents.read",
        "create_document": "documents.write",
        "createDocument": "documents.write",
        "update_document": "documents.write",
        "updateDocument": "documents.write",
        "delete_document": "documents.write",
        "deleteDocument": "documents.write",
        # --- Account & sessions (self-service; 'sessions.manage' covers it) ---
        "account_sessions": "sessions.manage",
        "accountSessions": "sessions.manage",
        "revoke_account_session": "sessions.manage",
        "revokeAccountSession": "sessions.manage",
        "revoke_other_account_sessions": "sessions.manage",
        "revokeOtherAccountSessions": "sessions.manage",
        # --- MFA self-service ---
        # --- API key management ---
        "api_keys": "api_keys.manage",
        "apiKeys": "api_keys.manage",
        # --- Admin surfaces ---
        "admin_users": "admin.users.read",
        "adminUsers": "admin.users.read",
        "admin_set_user_role": "admin.users.write",
        "adminSetUserRole": "admin.users.write",
        "admin_disable_user": "admin.users.write",
        "adminDisableUser": "admin.users.write",
        "admin_clear_lockout": "admin.lockouts.clear",
        "adminClearLockout": "admin.lockouts.clear",
        "admin_audit_events": "admin.audit.read",
        "adminAuditEvents": "admin.audit.read",
        "sso_tenant_configs": "admin.sso.manage",
        "ssoTenantConfigs": "admin.sso.manage",
        # --- Account / profile / self-service ---
        "account": "account.read",
        "me": "account.read",
        "ai_key_status": "account.read",
        "aiKeyStatus": "account.read",
        "profile": "account.read",
        "privacy_status": "account.read",
        "privacyStatus": "account.read",
        "user_followers": "account.read",
        "userFollowers": "account.read",
        "user_following": "account.read",
        "userFollowing": "account.read",
        "user_social_stats": "account.read",
        "userSocialStats": "account.read",
        "my_sessions": "sessions.manage",
        "mySessions": "sessions.manage",
        # Feedback about Manifest: any signed-in person, viewers included (rate-limited per user).
        "report_feedback": "account.read",
        "reportFeedback": "account.read",
        "update_account": "account.write",
        "updateAccount": "account.write",
        "save_openai_api_key": "account.write",
        "saveOpenaiApiKey": "account.write",
        "remove_openai_api_key": "account.write",
        "removeOpenaiApiKey": "account.write",
        "apollo_key_status": "account.read",
        "apolloKeyStatus": "account.read",
        "save_apollo_api_key": "account.write",
        "saveApolloApiKey": "account.write",
        "remove_apollo_api_key": "account.write",
        "removeApolloApiKey": "account.write",
        "request_account_deletion": "account.write",
        "requestAccountDeletion": "account.write",
        "logout_user": "account.read",
        "logoutUser": "account.read",
        "follow_user": "account.write",
        "followUser": "account.write",
        "unfollow_user": "account.write",
        "unfollowUser": "account.write",
        "toggle_follow": "account.write",
        "toggleFollow": "account.write",
        # --- Idea sub-features (votes, publish, versions, search, similarity) ---
        "find_similar_ideas": "ideas.read",
        "findSimilarIdeas": "ideas.read",
        "check_idea_access": "ideas.read",
        "checkIdeaAccess": "ideas.read",
        "idea_owner": "ideas.read",
        "ideaOwner": "ideas.read",
        "idea_versions": "ideas.read",
        "ideaVersions": "ideas.read",
        "my_shared_ideas": "ideas.read",
        "mySharedIdeas": "ideas.read",
        "universal_search": "ideas.read",
        "universalSearch": "ideas.read",
        "available_skills": "account.read",
        "availableSkills": "account.read",
        "survey_insights": "ideas.read",
        "surveyInsights": "ideas.read",
        "toggle_upvote": "ideas.write",
        "toggleUpvote": "ideas.write",
        "upvote_idea": "ideas.write",
        "upvoteIdea": "ideas.write",
        "remove_vote": "ideas.write",
        "removeVote": "ideas.write",
        "toggle_publish_idea": "ideas.write",
        "togglePublishIdea": "ideas.write",
        "create_idea_version": "ideas.write",
        "createIdeaVersion": "ideas.write",
        "restore_idea_version": "ideas.write",
        "restoreIdeaVersion": "ideas.write",
        "run_background_tasks": "ideas.write",
        "runBackgroundTasks": "ideas.write",
        "enqueue_background_tasks": "ideas.write",
        "enqueueBackgroundTasks": "ideas.write",
        # --- Idea qualification (multi-turn pre-build agent) ---
        "idea_qualification_session": "ideas.read",
        "ideaQualificationSession": "ideas.read",
        "my_idea_qualification_sessions": "ideas.read",
        "myIdeaQualificationSessions": "ideas.read",
        "start_idea_qualification": "ideas.write",
        "startIdeaQualification": "ideas.write",
        "continue_idea_qualification": "ideas.write",
        "continueIdeaQualification": "ideas.write",
        # --- Cost tracking + billing dashboard ---
        "my_cost_dashboard": "account.read",
        "myCostDashboard": "account.read",
        "my_agent_runs": "account.read",
        "myAgentRuns": "account.read",
        "my_cost_preflight": "account.read",
        "myCostPreflight": "account.read",
        "set_variable_cost_cap": "account.write",
        "setVariableCostCap": "account.write",
        # --- BMC per-section agents ---
        "bmc_sections": "ideas.read",
        "bmcSections": "ideas.read",
        "regenerate_bmc_section": "ideas.write",
        "regenerateBmcSection": "ideas.write",
        "saveBmcSection": "ideas.write",
        "regenerate_all_bmc_sections": "ideas.write",
        "regenerateAllBmcSections": "ideas.write",
        # --- Partner discovery agent (Key Partners helper) ---
        "partner_candidates": "ideas.read",
        "partnerCandidates": "ideas.read",
        "run_partner_discovery": "ideas.write",
        "runPartnerDiscovery": "ideas.write",
        "approve_partner_candidate": "ideas.write",
        "approvePartnerCandidate": "ideas.write",
        # --- Admin cost + agent run + production-test analytics ---
        "admin_cost_overview": "admin.cost.read",
        "adminCostOverview": "admin.cost.read",
        "admin_agent_runs": "admin.cost.read",
        "adminAgentRuns": "admin.cost.read",
        "admin_production_test_stats": "admin.cost.read",
        "adminProductionTestStats": "admin.cost.read",
        # --- Voice-platform testing (admin-only) ---
        "admin_voice_test_runs": "admin.voice_testing.read",
        "adminVoiceTestRuns": "admin.voice_testing.read",
        "admin_voice_test_stats": "admin.voice_testing.read",
        "adminVoiceTestStats": "admin.voice_testing.read",
        "admin_run_voice_test_case": "admin.voice_testing.write",
        "adminRunVoiceTestCase": "admin.voice_testing.write",
        # --- Collaboration / invites ---
        "idea_collaborators": "ideas.read",
        "ideaCollaborators": "ideas.read",
        "ideaLivePresence": "ideas.read",
        "my_collaboration_invitations": "ideas.read",
        "myCollaborationInvitations": "ideas.read",
        "invite_collaborator": "ideas.write",
        "inviteCollaborator": "ideas.write",
        "remove_collaborator": "ideas.write",
        "removeCollaborator": "ideas.write",
        "update_collaborator_role": "ideas.write",
        "updateCollaboratorRole": "ideas.write",
        "respond_to_invitation": "ideas.write",
        "respondToInvitation": "ideas.write",
        # --- Investments / cap table / sweat equity ---
        "idea_cap_table": "ideas.read",
        "ideaCapTable": "ideas.read",
        "idea_investments": "ideas.read",
        "ideaInvestments": "ideas.read",
        "my_portfolio": "ideas.read",
        "myPortfolio": "ideas.read",
        "calculate_sweat_equity": "ideas.read",
        "calculateSweatEquity": "ideas.read",
        "create_investment": "ideas.write",
        "createInvestment": "ideas.write",
        "add_investment_contribution": "ideas.write",
        "addInvestmentContribution": "ideas.write",
        "update_investment_status": "ideas.write",
        "updateInvestmentStatus": "ideas.write",
        # --- Generated documents (pitch deck / PRD / provisional patent) ---
        "pitch_deck": "documents.read",
        "pitchDeck": "documents.read",
        "documentGuide": "documents.read",
        "generate_pitch_deck": "documents.write",
        "generatePitchDeck": "documents.write",
        "saveIdeaDocument": "documents.write",
        "product_requirements_document": "documents.read",
        "productRequirementsDocument": "documents.read",
        "generate_product_requirements_document": "documents.write",
        "generateProductRequirementsDocument": "documents.write",
        "provisional_patent": "documents.read",
        "provisionalPatent": "documents.read",
        "generate_provisional_patent": "documents.write",
        "generateProvisionalPatent": "documents.write",
        "patents": "documents.read",
        # --- Pitch reels (public-feed social surfaces still need auth) ---
        "pitch_reels_feed": "ideas.read",
        "pitchReelsFeed": "ideas.read",
        "pitch_reel_comments": "ideas.read",
        "pitchReelComments": "ideas.read",
        "create_pitch_reel_comment": "ideas.write",
        "createPitchReelComment": "ideas.write",
        "reshare_pitch_reel": "ideas.write",
        "resharePitchReel": "ideas.write",
        "toggle_pitch_reel_like": "ideas.write",
        "togglePitchReelLike": "ideas.write",
        # --- Conversations / DMs ---
        "my_conversations": "account.read",
        "myConversations": "account.read",
        "my_inbox": "account.read",
        "myInbox": "account.read",
        "inbox_conversation": "account.read",
        "inboxConversation": "account.read",
        "reply_in_inbox": "account.write",
        "replyInInbox": "account.write",
        "mark_inbox_read": "account.write",
        "markInboxRead": "account.write",
        "conversation_messages": "account.read",
        "conversationMessages": "account.read",
        "unread_message_count": "account.read",
        "unreadMessageCount": "account.read",
        "send_message": "account.write",
        "sendMessage": "account.write",
        "start_conversation": "account.write",
        "startConversation": "account.write",
        "mark_conversation_read": "account.write",
        "markConversationRead": "account.write",
        # --- Goals that run (ADR 0020): plans, approvals, knowledge ---
        "goals": "account.read",
        "goal": "account.read",
        "pending_approvals": "account.read",
        "pendingApprovals": "account.read",
        "goal_capabilities": "account.read",
        "goalCapabilities": "account.read",
        "knowledge_facts": "account.read",
        "knowledgeFacts": "account.read",
        "create_goal": "account.write",
        "createGoal": "account.write",
        "start_outreach_goal": "account.write",
        "startOutreachGoal": "account.write",
        "advance_goal": "account.write",
        "advanceGoal": "account.write",
        "decide_approval": "account.write",
        "decideApproval": "account.write",
        "cancel_goal": "account.write",
        "cancelGoal": "account.write",
        "retry_goal_step": "account.write",
        "retryGoalStep": "account.write",
        "correct_knowledge": "account.write",
        "correctKnowledge": "account.write",
        # --- Open Media account link (messages and pitch shorts) ---
        "open_media_link": "account.read",
        "openMediaLink": "account.read",
        "open_media_realtime_token": "account.read",
        "openMediaRealtimeToken": "account.read",
        # --- Third-party integrations (per-user OAuth links) ---
        "integration": "account.read",
        "integrations": "account.read",
        "connect_integration": "account.write",
        "connectIntegration": "account.write",
        # Your own GitHub (acts with your token, never anyone else's).
        "githubAccount": "account.read",
        "githubRepos": "account.read",
        "githubRepo": "account.read",
        "githubIssues": "account.read",
        "githubIssue": "account.read",
        "githubPullRequests": "account.read",
        "githubPullRequest": "account.read",
        "githubBranches": "account.read",
        "githubCommits": "account.read",
        "githubContents": "account.read",
        "githubWorkflows": "account.read",
        "githubWorkflowRuns": "account.read",
        "githubReleases": "account.read",
        "githubApi": "account.read",
        "connectGithub": "account.write",
        "disconnectGithub": "account.write",
        "githubCreateRepo": "account.write",
        "githubUpdateRepo": "account.write",
        "githubDeleteRepo": "account.write",
        "githubCreateIssue": "account.write",
        "githubUpdateIssue": "account.write",
        "githubComment": "account.write",
        "githubCreatePullRequest": "account.write",
        "githubMergePullRequest": "account.write",
        "githubReviewPullRequest": "account.write",
        "githubCreateBranch": "account.write",
        "githubDeleteBranch": "account.write",
        "githubPutFile": "account.write",
        "githubDeleteFile": "account.write",
        "githubRunWorkflow": "account.write",
        "githubRerunWorkflowRun": "account.write",
        "githubCancelWorkflowRun": "account.write",
        "githubCreateRelease": "account.write",
        "githubApiRequest": "account.write",
        "start_integration_connection": "account.write",
        "startIntegrationConnection": "account.write",
        "disconnect_integration": "account.write",
        "disconnectIntegration": "account.write",
    }

    def resolve(self, _next, root, info: strawberry.Info, *args, **kwargs):  # type: ignore[override]
        parent = getattr(info, "parent_type", None)
        parent_name = getattr(parent, "name", "") if parent else ""
        # Only enforce on the operation root – nested fields inherit the
        # decision from their parent resolve.
        if parent_name in {"Query", "Mutation"}:
            field_name = info.field_name
            if field_name not in self.PUBLIC_FIELDS:
                request = info.context.get("request") if isinstance(info.context, dict) else None
                uid = None
                if request is not None:
                    # Use the same `get_current_user_id` symbol that
                    # individual resolvers use, so existing test mocks
                    # (which patch this module's binding) keep working.
                    try:
                        uid = get_current_user_id(request)
                    except HTTPException:
                        uid = None
                    except Exception:
                        try:
                            uid = get_current_user_id_optional(request)
                        except Exception:
                            uid = None
                if not uid:
                    raise PermissionError(f"Authentication required for {parent_name}.{field_name}")
                required = self.FIELD_PERMISSIONS.get(field_name)
                if required:
                    principal = _request_principal(request, uid)
                    if not principal or not principal.has(required):
                        raise PermissionError(
                            f"Permission '{required}' required for {parent_name}.{field_name}"
                        )
        return _next(root, info, *args, **kwargs)


# SEC-029: harden GraphQL surface — depth + alias + token caps to bound
# query cost, plus introspection lockdown in production.
def _graphql_extensions():
    exts = [
        _DefaultDenyAuthExtension,
        infrastructure_error_masker(),
        _QueryDepthLimiter(max_depth=int(os.getenv("GRAPHQL_MAX_DEPTH", "12"))),
        _MaxAliasesLimiter(max_alias_count=int(os.getenv("GRAPHQL_MAX_ALIASES", "30"))),
        _MaxTokensLimiter(max_token_count=int(os.getenv("GRAPHQL_MAX_TOKENS", "5000"))),
    ]
    env_label = (
        (os.getenv("MANIFEST_ENV") or os.getenv("ENVIRONMENT") or os.getenv("APP_ENV") or "")
        .strip()
        .lower()
    )
    introspection_enabled = (os.getenv("GRAPHQL_INTROSPECTION") or "").strip().lower()
    is_prod = env_label in {"prod", "production", "staging"}
    if introspection_enabled in {"0", "false", "no", "off"} or (
        is_prod and introspection_enabled not in {"1", "true", "yes", "on"}
    ):
        exts.append(_DisableIntrospection())
    return exts


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    extensions=_graphql_extensions(),
)
