"""Hide infrastructure failures from GraphQL clients.

Resolvers raise plain exceptions with user-facing messages ("Invalid email or
password"), so those must reach the client unchanged. Database and connection
failures, however, carry DSNs, hostnames, SQL and sometimes credentials; they
are logged server-side and replaced with a generic message.
"""

from graphql import GraphQLError
from strawberry.extensions import MaskErrors

GENERIC_ERROR_MESSAGE = "Something went wrong on our side. Please try again in a moment."

_INFRA_MARKERS = ("DATABASE_URL", "connection to server", "invalid dsn", "psycopg", "SQL")


def _is_infrastructure_error(error: BaseException) -> bool:
    try:
        import psycopg2

        if isinstance(error, psycopg2.Error):
            return True
    except ImportError:  # pragma: no cover - psycopg2 is a hard dependency in production
        pass
    if isinstance(error, ConnectionError | TimeoutError):
        return True
    return any(marker in str(error) for marker in _INFRA_MARKERS)


def should_mask_error(error: GraphQLError) -> bool:
    original = error.original_error
    return original is not None and _is_infrastructure_error(original)


def infrastructure_error_masker() -> MaskErrors:
    return MaskErrors(should_mask_error=should_mask_error, error_message=GENERIC_ERROR_MESSAGE)
