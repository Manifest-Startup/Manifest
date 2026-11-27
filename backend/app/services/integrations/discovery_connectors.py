"""Connectors for customer discovery, addressed by capability rather than by vendor.

The discovery agent (``app.services.ideas.customer_discovery``) asks for a capability and
this module picks the provider, so adding a vendor never means rewriting the agent:

==================  ==========================================  ==============================
Capability          Provider                                    Needs
==================  ==========================================  ==============================
web.search          OpenAI search models (``AIRouter``)         the person's OpenAI key (BYOK)
web.read            ``app.security.safe_http`` page fetch        nothing
prospects.search    Apollo.io organization + people search      their Apollo.io key, else ``APOLLO_API_KEY``
prospects.enrich    Apollo.io people match                      their Apollo.io key, else ``APOLLO_API_KEY``
email.createDraft   Gmail API ``users.drafts.create``           the person's Gmail connection
email.getDraft      Gmail API ``users.drafts.get``              the person's Gmail connection
==================  ==========================================  ==============================

There is deliberately no ``email.send``: Manifest prepares drafts and the founder sends them
from Gmail. Credentials never leave the server, and everything a provider returns (web pages
above all) is untrusted data, never instructions.

``DEMO_*`` fixtures exist so the flow can be shown without any provider. They are obviously
fictional (``example.com`` domains, "(demo)" names) and callers keep them out of saved work.
"""

from __future__ import annotations

import base64
import html
import os
import re
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any

import requests
from app.utils.logger import logger

CAPABILITIES = (
    "web.search",
    "web.read",
    "prospects.search",
    "prospects.enrich",
    "email.createDraft",
    "email.getDraft",
)

APOLLO_BASE = "https://api.apollo.io/api/v1"
GMAIL_SERVICE_ID = "gmail"
GMAIL_DRAFTS_URL = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
HTTP_TIMEOUT = 20.0
MAX_PAGE_TEXT = 12_000


class ConnectorUnavailable(RuntimeError):
    """The capability has no configured provider; the message says how to enable it."""


class ProviderError(RuntimeError):
    """The provider answered with an error (rate limit, auth, bad request)."""


def _http_error(provider: str, response: requests.Response) -> ProviderError:
    status = response.status_code
    if status == 429:
        return ProviderError(f"{provider} is rate limiting requests; try again in a minute.")
    if status in (401, 403):
        return ProviderError(f"{provider} refused the credentials (HTTP {status}).")
    return ProviderError(f"{provider} returned HTTP {status}.")


# ---- web.search -------------------------------------------------------------------------


def web_search_json(ai_layer: Any, query: str, system_prompt: str) -> dict[str, Any]:
    """Grounded web search that answers JSON: ``{"content": dict, "citations": [url, …]}``."""
    router = getattr(ai_layer, "router", None)
    if router is None or not router.is_available():
        raise ConnectorUnavailable(
            "Web research needs your OpenAI key (Account → AI settings), or an agent with its "
            "own web search can do the research and save it with save_customer_discovery."
        )
    result = router.web_search_json(query, system_prompt=system_prompt)
    content = result.get("content")
    return {
        "content": content if isinstance(content, dict) else {},
        "citations": [str(u) for u in result.get("citations") or [] if u],
    }


# ---- web.read ---------------------------------------------------------------------------

_TAG = re.compile(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", re.S | re.I)
_ANY_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


_MAILTO = re.compile(r"mailto:([^\"'?>\s]+@[^\"'?>\s]+)", re.I)


def web_read(url: str) -> dict[str, str]:
    """Fetch one public page as plain text (SSRF-safe). The text is untrusted data."""
    from app.security.safe_http import safe_get

    response = safe_get(
        url,
        timeout=HTTP_TIMEOUT,
        max_response_bytes=2_000_000,
        headers={"User-Agent": "Manifest-Research/1.0", "Accept": "text/html,text/plain"},
    )
    if response.status_code >= 400:
        raise ProviderError(f"{url} returned HTTP {response.status_code}.")
    raw = response.text or ""
    title_match = _TITLE.search(raw)
    text = _SPACE.sub(" ", html.unescape(_ANY_TAG.sub(" ", _TAG.sub(" ", raw)))).strip()
    # A "Get in touch" link shows its address only in the link; keep those addresses too.
    mailto = sorted({m.lower() for m in _MAILTO.findall(raw)})
    if mailto:
        text = f"Email links: {' '.join(mailto)}. {text}"
    return {
        "url": response.url or url,
        "title": _SPACE.sub(" ", html.unescape(title_match.group(1))).strip()
        if title_match
        else "",
        "text": text[:MAX_PAGE_TEXT],
    }


def website_resolves(url: str) -> bool:
    """True when a prospect's website exists (a cheap check against invented companies).

    Any answer counts except "not found": bot walls (403/429/503) and pages bigger than the
    read cap still prove the site is there. Unknown domains and refused connections don't."""
    from app.security.safe_http import SSRFError, safe_request

    try:
        response = safe_request(
            "GET",
            url,
            timeout=8.0,
            max_response_bytes=200_000,
            headers={"User-Agent": "Manifest-Research/1.0"},
        )
        return response.status_code not in (404, 410)
    except SSRFError as exc:
        return "exceeded" in str(
            exc
        )  # it answered, with a big page; other SSRF refusals don't count
    except Exception as exc:
        logger.debug("[discovery] website check failed for %s: %s", url, exc)
        return False


# ---- prospects.search / prospects.enrich (Apollo.io) ------------------------------------


APOLLO_SERVICE_ID = "apollo"
APOLLO_SERVICE_NAME = "Apollo.io"
APOLLO_HEALTH_URL = "https://api.apollo.io/v1/auth/health"


class InvalidApolloKeyError(ValueError):
    """The key is malformed or Apollo.io rejected it."""


def platform_apollo_key() -> str | None:
    """The operator's Apollo.io key (``APOLLO_API_KEY``), for people who'd rather not set up
    their own: the seamless hosted setup. Their own key always comes first."""
    return (os.getenv("APOLLO_API_KEY") or "").strip() or None


def apollo_key_source(user_id: str) -> tuple[str | None, str]:
    """(key, "user" | "platform" | "none"): the person's own Apollo.io key, else the operator's."""
    from app.services.ai.user_keys import load_user_key

    try:
        own = load_user_key(user_id, APOLLO_SERVICE_ID)
    except Exception as exc:  # lookup or decryption trouble: don't block, fall back
        logger.warning("[discovery] apollo key lookup failed: %s", type(exc).__name__)
        own = None
    if own:
        return own, "user"
    platform = platform_apollo_key()
    return (platform, "platform") if platform else (None, "none")


def apollo_key_for(user_id: str) -> str | None:
    return apollo_key_source(user_id)[0]


def validate_apollo_key(raw: str) -> str:
    key = (raw or "").strip()
    if len(key) < 16 or any(c.isspace() for c in key):
        raise InvalidApolloKeyError("That doesn't look like an Apollo.io API key.")
    try:
        response = requests.get(
            APOLLO_HEALTH_URL, headers={"X-Api-Key": key, "Cache-Control": "no-cache"}, timeout=15
        )
    except requests.RequestException as exc:
        raise InvalidApolloKeyError(
            "Couldn't reach Apollo.io to check the key. Try again."
        ) from exc
    data = (
        response.json()
        if response.headers.get("content-type", "").startswith("application/json")
        else {}
    )
    if response.status_code >= 400 or not (isinstance(data, dict) and data.get("is_logged_in")):
        raise InvalidApolloKeyError("Apollo.io rejected this key. Check it and try again.")
    return key


def save_apollo_key(user_id: str, raw: str) -> str:
    """Verify with Apollo.io, then store encrypted like the OpenAI key. Returns the last four."""
    from app.services.ai.user_keys import store_key

    return store_key(
        user_id,
        validate_apollo_key(raw),
        service_id=APOLLO_SERVICE_ID,
        service_name=APOLLO_SERVICE_NAME,
    )


def apollo_key_last4(user_id: str) -> str | None:
    from app.services.ai.user_keys import key_last4

    return key_last4(user_id, APOLLO_SERVICE_ID)


def remove_apollo_key(user_id: str) -> None:
    from app.services.ai.user_keys import delete_user_key

    delete_user_key(user_id, APOLLO_SERVICE_ID)


def _apollo_post(path: str, body: dict[str, Any], key: str | None) -> dict[str, Any]:
    if not key:
        raise ConnectorUnavailable("Add your Apollo.io key in Account → AI settings.")
    response = requests.post(
        f"{APOLLO_BASE}/{path}",
        json=body,
        headers={"X-Api-Key": key, "Content-Type": "application/json", "Cache-Control": "no-cache"},
        timeout=HTTP_TIMEOUT,
    )
    if response.status_code >= 400:
        raise _http_error("Apollo.io", response)
    data = response.json()
    return data if isinstance(data, dict) else {}


def apollo_search_organizations(
    *,
    key: str | None,
    keywords: list[str],
    locations: list[str],
    employee_ranges: list[str],
    per_page: int = 15,
) -> list[dict[str, Any]]:
    """Companies matching an ideal customer profile, as provider-neutral prospect seeds."""
    body: dict[str, Any] = {"page": 1, "per_page": max(1, min(per_page, 25))}
    if keywords:
        body["q_organization_keyword_tags"] = keywords[:5]
    if locations:
        body["organization_locations"] = locations[:3]
    if employee_ranges:
        body["organization_num_employees_ranges"] = employee_ranges[:3]
    data = _apollo_post("mixed_companies/search", body, key)
    out: list[dict[str, Any]] = []
    for org in (data.get("organizations") or []) + (data.get("accounts") or []):
        if not isinstance(org, dict) or not org.get("name"):
            continue
        website = org.get("website_url") or (
            f"https://{org['primary_domain']}" if org.get("primary_domain") else None
        )
        out.append(
            {
                "name": str(org["name"]),
                "website": website,
                "domain": org.get("primary_domain"),
                "industry": org.get("industry"),
                "description": org.get("short_description") or org.get("seo_description"),
                "employees": org.get("estimated_num_employees"),
                "linkedin_url": org.get("linkedin_url"),
                "source": "apollo",
            }
        )
    return out


def apollo_find_decision_maker(
    *, key: str | None, domain: str, titles: list[str]
) -> dict[str, Any] | None:
    """The most senior matching person at a company (no email; enrichment reveals that)."""
    if not domain:
        return None
    data = _apollo_post(
        "mixed_people/api_search",
        {
            "q_organization_domains_list": [domain],
            "person_titles": titles[:6],
            "page": 1,
            "per_page": 3,
        },
        key,
    )
    for person in data.get("people") or []:
        if isinstance(person, dict) and (person.get("name") or person.get("first_name")):
            return {
                "apollo_id": person.get("id"),
                # Apollo's free people search hides the surname ("Ho***e") until enrichment.
                "name": person.get("name")
                or " ".join(
                    filter(
                        None,
                        [
                            person.get("first_name"),
                            person.get("last_name") or person.get("last_name_obfuscated"),
                        ],
                    )
                ),
                "has_email": bool(person.get("has_email")),
                "title": person.get("title"),
                "linkedin_url": person.get("linkedin_url"),
                "source": "apollo",
            }
    return None


def apollo_enrich_email(key: str | None, apollo_id: str) -> str | None:
    """A verified work email for one person, or None. Uses Apollo credits; call on request."""
    data = _apollo_post("people/match", {"id": apollo_id, "reveal_personal_emails": False}, key)
    person = data.get("person") or {}
    if person.get("email") and person.get("email_status") == "verified":
        return str(person["email"])
    return None


# ---- email.createDraft / email.getDraft (Gmail) -----------------------------------------


@dataclass(frozen=True)
class GmailConnection:
    access_token: str
    refresh_token: str | None


def gmail_connection(db: Any, user_id: str) -> GmailConnection | None:
    """The person's Gmail connection (Account → Integrations → Gmail), if any."""
    from app.services.integrations.token_crypto import decrypt_integration_tokens

    rows = (
        db.table("integrations")
        .select("*")
        .eq("user_id", user_id)
        .eq("service_id", GMAIL_SERVICE_ID)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        return None
    access, refresh = decrypt_integration_tokens(rows[0])
    if not access and not refresh:
        return None
    return GmailConnection(access_token=access or "", refresh_token=refresh)


def _refresh_google_token(refresh_token: str) -> str:
    client_id, secret = os.getenv("GOOGLE_CLIENT_ID"), os.getenv("GOOGLE_CLIENT_SECRET")
    if not (client_id and secret):
        raise ConnectorUnavailable("Gmail sign-in is not set up on this Manifest server.")
    response = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=HTTP_TIMEOUT,
    )
    if response.status_code >= 400:
        raise ProviderError("Gmail sign-in expired; connect Gmail again in Account → Integrations.")
    return str(response.json().get("access_token") or "")


def _gmail_call(conn: GmailConnection, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
    token = conn.access_token
    for attempt in range(2):
        response = requests.request(
            method,
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=HTTP_TIMEOUT,
            **kwargs,
        )
        if response.status_code == 401 and attempt == 0 and conn.refresh_token:
            token = _refresh_google_token(conn.refresh_token)
            continue
        if response.status_code >= 400:
            raise _http_error("Gmail", response)
        data = response.json()
        return data if isinstance(data, dict) else {}
    raise ProviderError("Gmail refused the connection.")


def gmail_create_draft(conn: GmailConnection, *, to: str | None, subject: str, body: str) -> str:
    """Create one draft (never sends). Returns the Gmail draft id."""
    message = EmailMessage()
    if to:
        message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    data = _gmail_call(conn, "POST", GMAIL_DRAFTS_URL, json={"message": {"raw": raw}})
    draft_id = data.get("id")
    if not draft_id:
        raise ProviderError("Gmail did not return a draft id.")
    return str(draft_id)


def gmail_compose_url(*, to: str | None, subject: str, body: str) -> str:
    """A link that opens Gmail's compose window, pre-filled, in whoever's Gmail opens it.

    Needs no Google sign-in setup or scope: the person saves or sends it themselves."""
    from urllib.parse import urlencode

    query = {"view": "cm", "fs": "1", "su": subject, "body": body}
    if to:
        query["to"] = to
    return "https://mail.google.com/mail/?" + urlencode(query)


def gmail_get_draft(conn: GmailConnection, draft_id: str) -> dict[str, Any] | None:
    try:
        return _gmail_call(
            conn, "GET", f"{GMAIL_DRAFTS_URL}/{draft_id}", params={"format": "minimal"}
        )
    except ProviderError:
        return None


# ---- status -----------------------------------------------------------------------------


def capability_status(db: Any, user_id: str, ai_layer: Any) -> dict[str, dict[str, Any]]:
    """Which capabilities work right now for this person, and how to enable the rest."""
    router = getattr(ai_layer, "router", None)
    has_ai = bool(router is not None and router.is_available())
    apollo_source = apollo_key_source(user_id)[1]
    has_apollo = apollo_source != "none"
    # Whose Apollo account searches run on: the person's own, or Manifest's (seamless setup).
    apollo_provider = {"user": "apollo (your account)", "platform": "apollo (Manifest's)"}.get(
        apollo_source, "apollo"
    )
    try:
        has_gmail = gmail_connection(db, user_id) is not None
    except Exception as exc:  # decryption or lookup failure: report, don't crash
        logger.warning("[discovery] gmail lookup failed: %s", exc)
        has_gmail = False
    gmail_hint = (
        "Each prepared email has an Open in Gmail link (a pre-filled compose window); "
        "saving drafts straight into Gmail isn't switched on for this server."
    )
    return {
        "web.search": {
            "available": has_ai,
            "provider": "openai-search",
            "hint": None if has_ai else "Add your OpenAI key in Account → AI settings.",
        },
        "web.read": {"available": True, "provider": "safe-http", "hint": None},
        "prospects.search": {
            # Without Apollo, prospects come from web search, which needs the OpenAI key.
            "available": has_apollo or has_ai,
            "provider": apollo_provider if has_apollo else "web-search",
            "hint": None
            if has_apollo or has_ai
            else "Add your OpenAI key (or your Apollo.io key) in Account → AI settings.",
        },
        "prospects.enrich": {
            "available": has_apollo,
            "provider": apollo_provider,
            "hint": None
            if has_apollo
            else "Add your Apollo.io key in Account → AI settings; contacts stay unverified.",
        },
        "email.createDraft": {
            "available": has_gmail,
            "provider": "gmail",
            "hint": None if has_gmail else gmail_hint,
        },
        "email.getDraft": {
            "available": has_gmail,
            "provider": "gmail",
            "hint": None if has_gmail else gmail_hint,
        },
    }


# ---- demo fixtures (never saved, always labelled) ---------------------------------------

DEMO_NOTICE = "Demo data: fictional examples to show the flow. Not real research."

DEMO_PROSPECTS: list[dict[str, Any]] = [
    {
        "name": f"Example Agency {letter} (demo)",
        "website": f"https://agency-{letter.lower()}.example.com",
        "industry": "Social media marketing agency",
        "description": "Fictional agency used to demonstrate the flow.",
        "why_fit": "Fictional: manages social accounts for several clients.",
        "need_evidence": [],
        "decision_maker": None,
        "sources": [],
        "scores": {
            "problem_relevance": 3,
            "profile_fit": 3,
            "need_evidence": 0,
            "purchasing": 2,
        },
    }
    for letter in "ABCDE"
]
