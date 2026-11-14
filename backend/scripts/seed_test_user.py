import json
import os
import sys
import uuid
from pathlib import Path
from urllib import error, request

from dotenv import load_dotenv

script_dir = Path(__file__).resolve().parent
backend_root = script_dir.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.db.database import get_db_connection
from app.utils.password_utils import hash_password

repo_root = script_dir.parent.parent
root_env = repo_root / ".env"
backend_env = script_dir.parent / ".env"
cwd_env = Path.cwd() / ".env"
parent_env = Path.cwd().parent / ".env"
personas_path = repo_root / "frontend" / "cypress" / "fixtures" / "e2ePersonas.json"

env_paths = [root_env, backend_env, cwd_env, parent_env]

env_loaded = False
for env_path in env_paths:
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
        print(f"✓ Loaded .env from: {env_path}", file=sys.stderr)
        env_loaded = True
        break

if not env_loaded:
    print("⚠ Warning: No .env file found in expected locations, trying load_dotenv()", file=sys.stderr)
    print(f"  Checked paths: {[str(p) for p in env_paths]}", file=sys.stderr)
    load_dotenv()

# GitHub Actions E2E uses an empty Postgres service without Supabase migrations;
# seed via the running backend's GraphQL signup instead of direct SQL inserts.
if os.environ.get("E2E_USE_GRAPHQL_SEED", "").strip().lower() in {"1", "true", "yes"}:
    os.environ.pop("DATABASE_URL", None)

DATABASE_URL = os.environ.get("DATABASE_URL")
GRAPHQL_URL = os.environ.get("E2E_GRAPHQL_URL", "http://localhost:8000/graphql")
DEFAULT_PASSWORD = os.environ.get("E2E_PASSWORD", "Mnfst_E2e_CI_9x!")

SIGNUP_MUTATION = """
mutation SignupUser($email: String!, $password: String!) {
  signupUser(email: $email, password: $password) {
    userId
    email
  }
}
"""


def load_personas() -> list[dict]:
    with personas_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_user_specs() -> list[dict]:
    legacy_user = {
        "displayName": "Legacy Default User",
        "email": "hello@manifeststartup.com",
        "password": DEFAULT_PASSWORD,
        "persona": "Backward-compatible default account for existing Cypress specs.",
    }

    persona_specs = [
        {
            **persona,
            "password": persona.get("password") or DEFAULT_PASSWORD,
        }
        for persona in load_personas()
    ]

    return [legacy_user, *persona_specs]


def create_user(user_spec: dict) -> None:
    if not DATABASE_URL:
        create_user_via_backend(user_spec)
        return

    email = user_spec["email"].lower()
    display_name = user_spec.get("displayName", "")
    first_name, _, last_name = display_name.partition(" ")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM users WHERE email = %s", (email,))
            existing = cur.fetchone()
            if existing:
                print(f"• Already exists: {email}")
                return

            cur.execute(
                """
                INSERT INTO users (
                    user_id,
                    email,
                    password_hash,
                    auth_provider,
                    first_name,
                    last_name,
                    username,
                    bio,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                """,
                (
                    str(uuid.uuid4()),
                    email,
                    hash_password(user_spec["password"]),
                    "email",
                    first_name or None,
                    last_name or None,
                    user_spec.get("slug"),
                    user_spec.get("persona"),
                ),
            )

    print(f"✓ Created {email}")


def create_user_via_backend(user_spec: dict) -> None:
    email = user_spec["email"].lower()
    payload = json.dumps(
        {
            "operationName": "SignupUser",
            "query": SIGNUP_MUTATION,
            "variables": {
                "email": email,
                "password": user_spec["password"],
            },
        }
    ).encode("utf-8")

    req = request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = json.loads(exc.read().decode("utf-8"))
    except Exception as exc:
        print(f"Failed to create {email} via backend signup: {exc}", file=sys.stderr)
        raise

    errors = body.get("errors") or []
    if errors:
        message = errors[0].get("message", "")
        if "already exists" in message.lower():
            print(f"• Already exists: {email}")
            return
        raise RuntimeError(f"Failed to create {email} via backend signup: {message}")

    print(f"✓ Created {email} via backend signup")


def main() -> None:
    print(f"Seeding E2E users from {personas_path}")
    for user_spec in build_user_specs():
        create_user(user_spec)


if __name__ == "__main__":
    main()