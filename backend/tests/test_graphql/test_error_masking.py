"""Infrastructure errors are masked; user-facing resolver errors are not."""

import psycopg2
from app.graphql.error_masking import GENERIC_ERROR_MESSAGE, should_mask_error
from graphql import GraphQLError


def _wrap(exc: Exception) -> GraphQLError:
    return GraphQLError(str(exc), original_error=exc)


def test_database_errors_are_masked():
    assert should_mask_error(_wrap(psycopg2.OperationalError("password authentication failed")))
    assert should_mask_error(_wrap(RuntimeError("DATABASE_URL environment variable is not set")))
    assert should_mask_error(_wrap(Exception('invalid dsn: missing "=" after "x"')))
    assert should_mask_error(_wrap(ConnectionError("refused")))


def test_user_facing_errors_pass_through():
    assert not should_mask_error(_wrap(Exception("Invalid email or password")))
    assert not should_mask_error(GraphQLError("Cannot query field"))


def test_generic_message_reveals_nothing():
    assert "DATABASE" not in GENERIC_ERROR_MESSAGE and "@" not in GENERIC_ERROR_MESSAGE
