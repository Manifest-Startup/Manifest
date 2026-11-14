from app.utils.logger import logger
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger.info("customer_routes.py loaded")

router = APIRouter()


class ContactForm(BaseModel):
    first_name: str
    last_name: str
    email: str
    message: str


import asyncio
import datetime
import os
from uuid import uuid4

from app.db.database import get_database_url, get_db_connection
from app.services.privacy_consent_service import analytics_enabled_for_request
from fastapi import Request, Response


def log_visitor(data: dict):
    """
    Insert visitor data into the 'customers' table in PostgreSQL.
    """
    if not get_database_url():
        logger.debug("Skipping visitor log insert: DATABASE_URL is not configured.")
        return False

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO customers (
                        email, first_name, middle_name, last_name, company_name,
                        role, location, linkedin_url, source, referrer_id,
                        landing_page, intent_level, tags, summary, is_interested,
                        has_opted_out, have_we_answered, visitor_id, ip_address,
                        user_agent, referer, created_at
                    ) VALUES (
                        %(email)s, %(first_name)s, %(middle_name)s, %(last_name)s, %(company_name)s,
                        %(role)s, %(location)s, %(linkedin_url)s, %(source)s, %(referrer_id)s,
                        %(landing_page)s, %(intent_level)s, %(tags)s, %(summary)s, %(is_interested)s,
                        %(has_opted_out)s, %(have_we_answered)s, %(visitor_id)s, %(ip_address)s,
                        %(user_agent)s, %(referer)s, %(created_at)s
                    )
                """,
                    data,
                )
                conn.commit()
        return True
    except Exception as e:
        logger.error(f"Failed to log visitor: {e}")
        return False


async def track_visitors_middleware(request: Request, call_next):
    logger.debug(f"Request cookies: {request.cookies}")
    if not analytics_enabled_for_request(request):
        response: Response = await call_next(request)
        if request.cookies.get("visitor_id"):
            response.delete_cookie("visitor_id", samesite="Lax")
        return response

    visitor_id = request.cookies.get("visitor_id")
    logger.info(
        f"Visitor cookie found: {visitor_id}"
        if visitor_id
        else "No visitor_id cookie found; will generate new."
    )
    if not visitor_id:
        visitor_id = str(uuid4())
        logger.info(f"Generated new visitor_id: {visitor_id}")
        new_visitor = True
    else:
        new_visitor = False

    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else "unknown"
    referer = request.headers.get("referer", "direct")

    visitor_log_data = None
    if new_visitor:
        logger.debug(
            f"Logging visitor data: {{'visitor_id': {visitor_id}, 'ip': {ip_address}, 'user_agent': {user_agent}}}"
        )
        visitor_log_data = {
            "email": None,
            "first_name": None,
            "middle_name": None,
            "last_name": None,
            "company_name": None,
            "role": None,
            "location": None,
            "linkedin_url": None,
            "source": "website_visit",
            "referrer_id": str(uuid4()),
            "landing_page": str(request.url),
            "intent_level": "low",
            "tags": "anonymous, visitor",
            "summary": f"Visitor from {ip_address} using {user_agent}",
            "is_interested": False,
            "has_opted_out": False,
            "have_we_answered": False,
            "visitor_id": visitor_id,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "referer": referer,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    response: Response = await call_next(request)

    if new_visitor:
        response.set_cookie(
            key="visitor_id",
            value=visitor_id,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite="Lax",
        )
        logger.info(f"Set visitor_id cookie for visitor: {visitor_id}")

    if visitor_log_data:
        if os.getenv("PYTEST_CURRENT_TEST"):
            logged = log_visitor(visitor_log_data)
            if logged:
                logger.info(
                    f"Logged new visitor to database: visitor_id={visitor_id}, ip={ip_address}"
                )
        else:

            async def _log_after_response() -> None:
                logged = await asyncio.to_thread(log_visitor, visitor_log_data)
                if logged:
                    logger.info(
                        f"Logged new visitor to database: visitor_id={visitor_id}, ip={ip_address}"
                    )

            asyncio.create_task(_log_after_response())

    return response


@router.post("/api/contact")
async def contact(request: Request, form: ContactForm):
    """
    API endpoint to handle contact form submissions.
    Stores contact information in the database.
    """
    try:
        with get_db_connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                    INSERT INTO customers (
                        email, first_name, last_name, source, summary, created_at
                    ) VALUES (%s, %s, %s, %s, %s, NOW())
                """,
                (form.email, form.first_name, form.last_name, "contact_form", form.message),
            )
            conn.commit()
        logger.info(f"Contact form submitted by {form.email}")
        return {"success": True, "message": "Thank you for your message!"}
    except Exception as e:
        logger.error(f"Failed to store contact form: {e}")
        raise HTTPException(status_code=500, detail="Failed to store contact form") from e
