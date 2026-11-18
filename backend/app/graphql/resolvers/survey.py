"""GraphQL resolvers for the survey and the contact form."""

import json
import uuid
from datetime import datetime

import strawberry
from app.auth.current_user import (
    get_current_user_id,
    get_current_user_id_optional,
)
from app.graphql.types.survey import (
    ContactFormInput,
    SubmitSurveyInput,
    SurveyInsights,
    _build_survey_insights,
)
from app.services.operations.survey_ops import survey_ops_service
from app.utils.logger import logger


@strawberry.type
class SurveyQuery:
    @strawberry.field
    async def survey_insights(self, info: strawberry.Info, window_days: int = 90) -> SurveyInsights:
        """Aggregated survey results (research and product feedback) over the last windowDays days."""
        get_current_user_id(info.context["request"])
        summary = survey_ops_service.get_summary(info.context["db"], window_days=window_days)
        return _build_survey_insights(summary)


@strawberry.type
class SurveyMutation:
    @strawberry.mutation
    async def submit_contact_form(self, info: strawberry.Info, input: ContactFormInput) -> bool:
        """Send a message to the Manifest team."""
        data = {
            "first_name": input.first_name,
            "last_name": input.last_name,
            "email": input.email,
            "summary": input.message,
            "source": "contact_form",
            "created_at": datetime.utcnow().isoformat(),
        }
        info.context["db"].table("customers").insert(data).execute()
        return True

    @strawberry.mutation
    async def submit_survey(self, info: strawberry.Info, input: SubmitSurveyInput) -> bool:
        """Persist research (public) or product-feedback (authenticated) survey answers to Postgres."""
        raw_type = (input.survey_type or "").strip().lower()
        if raw_type not in ("research", "product_feedback"):
            raise Exception("Invalid survey type")

        payload = (input.answers_json or "").strip()
        if len(payload) > 120_000:
            raise Exception("Survey answers are too large")

        try:
            answers = json.loads(payload if payload else "{}")
        except json.JSONDecodeError as exc:
            raise Exception("Invalid answers JSON") from exc

        if not isinstance(answers, dict):
            raise Exception("Answers must be a JSON object")

        answers_payload = json.dumps(answers)

        if raw_type == "research":
            if not answers.get("consent_required"):
                raise Exception("You must agree before submitting")
        else:
            user_required = get_current_user_id_optional(info.context["request"])
            if not user_required:
                raise Exception("Sign in to submit product feedback")

        user_id = get_current_user_id_optional(info.context["request"])
        email = (input.contact_email or "").strip() or None

        row = {
            "response_id": str(uuid.uuid4()),
            "survey_type": raw_type,
            "user_id": user_id,
            "contact_email": email,
            "answers": answers_payload,
            "created_at": datetime.utcnow().isoformat(),
        }
        try:
            info.context["db"].table("survey_responses").insert(row).execute()
        except Exception as exc:
            logger.error(
                "[submit_survey] Failed to save survey response (survey_type=%s, user_id=%s): %s",
                raw_type,
                user_id,
                exc,
            )
            raise Exception("Could not save survey response") from exc
        return True
