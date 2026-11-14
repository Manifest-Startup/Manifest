#!/usr/bin/env python3
"""Copy Manifest production data from Replit to Supabase (database + generated files).

Run this inside the **Replit Shell** of the live deployment. That is where the
production secrets, ``pg_dump``/``pg_restore`` and the ``generated/pdfs`` files
already are, so nothing sensitive is copied to another machine.

Source and target are read from the environment, never from arguments:

    DATABASE_URL               Replit Postgres (source, read-only here)
    TARGET_DATABASE_URL        Supabase Postgres (session pooler or direct URL)
    SUPABASE_URL               https://<ref>.supabase.co
    SUPABASE_SERVICE_ROLE_KEY  Supabase service-role key (Storage uploads)

Steps (each is safe to re-run):

    python scripts/migrate_replit_to_supabase.py check     # connectivity + table counts, no writes
    python scripts/migrate_replit_to_supabase.py database  # dump public schema, restore into target
    python scripts/migrate_replit_to_supabase.py files     # upload generated/pdfs/** to Storage
    python scripts/migrate_replit_to_supabase.py verify    # table-by-table row-count reconciliation

``database`` refuses to restore into a target whose ``public`` schema already
has rows unless ``--replace`` is given (then it drops and recreates objects
from the dump with ``pg_restore --clean``). Row values are never printed.
"""

from __future__ import annotations

import argparse
import mimetypes
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATED_ROOT = REPO_ROOT / "generated" / "pdfs"


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"error: {name} is not set")
    return value


def _connect(url: str):
    import psycopg  # backend dependency (psycopg 3)

    return psycopg.connect(url, connect_timeout=15)


def table_counts(url: str) -> dict[str, int]:
    with _connect(url) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
        )
        tables = [row[0] for row in cur.fetchall()]
        counts = {}
        for table in tables:
            cur.execute(f'SELECT count(*) FROM public."{table}"')
            counts[table] = cur.fetchone()[0]
        return counts


def cmd_check(_args) -> int:
    source = table_counts(_env("DATABASE_URL"))
    print(f"source: {len(source)} tables, {sum(source.values())} rows")
    target = table_counts(_env("TARGET_DATABASE_URL"))
    print(f"target: {len(target)} tables, {sum(target.values())} rows")
    files = [p for p in GENERATED_ROOT.rglob("*") if p.is_file()] if GENERATED_ROOT.exists() else []
    print(f"generated files: {len(files)} ({sum(p.stat().st_size for p in files)} bytes)")
    return 0


def cmd_database(args) -> int:
    source_url, target_url = _env("DATABASE_URL"), _env("TARGET_DATABASE_URL")
    existing = table_counts(target_url)
    if sum(existing.values()) and not args.replace:
        sys.exit(
            "error: target public schema already has rows; re-run with --replace to overwrite it"
        )
    with tempfile.TemporaryDirectory() as tmp:
        dump = Path(tmp) / "manifest.dump"
        print("dumping source public schema ...")
        subprocess.run(
            [
                "pg_dump",
                "--format=custom",
                "--schema=public",
                "--no-owner",
                "--no-privileges",
                "--file",
                str(dump),
                source_url,
            ],
            check=True,
        )
        print(f"dump size: {dump.stat().st_size} bytes; restoring into target ...")
        restore = [
            "pg_restore",
            "--no-owner",
            "--no-privileges",
            "--exit-on-error",
            "--single-transaction",
            "--dbname",
            target_url,
        ]
        if args.replace:
            restore[1:1] = ["--clean", "--if-exists"]
        subprocess.run([*restore, str(dump)], check=True)
    print("restore complete; run `verify` next")
    return 0


def _upload(base: str, key: str, bucket: str, path: str, payload: bytes, content_type: str) -> None:
    import requests

    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    bucket_url = f"{base}/storage/v1/bucket"
    if (
        requests.get(
            f"{bucket_url}/{quote(bucket, safe='')}", headers=headers, timeout=20
        ).status_code
        != 200
    ):
        created = requests.post(
            bucket_url,
            headers=headers,
            timeout=20,
            json={"id": bucket, "name": bucket, "public": True},
        )
        if created.status_code not in {200, 201, 409}:
            created.raise_for_status()
    resp = requests.post(
        f"{base}/storage/v1/object/{quote(bucket, safe='')}/{quote(path, safe='/')}",
        headers={**headers, "Content-Type": content_type, "x-upsert": "true"},
        data=payload,
        timeout=120,
    )
    resp.raise_for_status()


def cmd_files(_args) -> int:
    base = _env("SUPABASE_URL").rstrip("/")
    key = _env("SUPABASE_SERVICE_ROLE_KEY")
    if not GENERATED_ROOT.exists():
        print("no generated/pdfs directory; nothing to copy")
        return 0
    copied = skipped = 0
    for file in sorted(p for p in GENERATED_ROOT.rglob("*") if p.is_file()):
        relative = file.relative_to(GENERATED_ROOT).as_posix()
        bucket, _, path = relative.partition("/")
        if not path:
            skipped += 1  # files directly under generated/pdfs have no bucket
            print(f"skipped (no bucket folder): {relative}")
            continue
        content_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        _upload(base, key, bucket, path, file.read_bytes(), content_type)
        copied += 1
    print(f"uploaded {copied} files, skipped {skipped}")
    print(f"set FILES_PUBLIC_BASE={base}/storage/v1/object/public on the Cloudflare Worker")
    return 0


def cmd_verify(_args) -> int:
    source = table_counts(_env("DATABASE_URL"))
    target = table_counts(_env("TARGET_DATABASE_URL"))
    mismatches = 0
    for table in sorted(set(source) | set(target)):
        s, t = source.get(table), target.get(table)
        status = "ok" if s == t else "MISMATCH"
        mismatches += status != "ok"
        print(f"{status:8} {table}: source={s} target={t}")
    print(f"{mismatches} mismatched tables")
    return 1 if mismatches else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    db = sub.add_parser("database")
    db.add_argument("--replace", action="store_true", help="overwrite a non-empty target")
    sub.add_parser("files")
    sub.add_parser("verify")
    args = parser.parse_args()
    return {"check": cmd_check, "database": cmd_database, "files": cmd_files, "verify": cmd_verify}[
        args.command
    ](args)


if __name__ == "__main__":
    sys.exit(main())
