"""Operational CLI.

`create-superuser` is the bootstrap: a fresh database has no platform admin, so
nothing under /api/v1/admin is reachable until this runs. It writes to `users`,
which carries no RLS because it is not a tenant table, so no tenant context is
needed.

    uv run python -m app.cli create-superuser --email ops@example.com
    docker compose exec backend python -m app.cli create-superuser --email ops@example.com

`export-invoice-corpus` y `eval-invoices` son el ciclo del modelo propio:
sacar las facturas ya revisadas como datos etiquetados, y medir con ellas si el
lector configurado alcanza.

    uv run python -m app.cli export-invoice-corpus --out data/facturas
    uv run python -m app.cli eval-invoices --corpus data/facturas
"""

import argparse
import asyncio
import getpass
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.domain.identity.value_objects.email import Email
from app.infrastructure.database.models.user import UserModel
from app.infrastructure.database.session import SessionFactory, dispose_engine
from app.shared.security import hash_password

MIN_PASSWORD_LENGTH = 12


async def create_superuser(
    email: str, password: str, first_name: str, last_name: str, *, promote: bool
) -> int:
    normalised = Email(email).value

    async with SessionFactory() as session:
        existing = (
            await session.execute(select(UserModel).where(UserModel.email == normalised))
        ).scalar_one_or_none()

        if existing is not None:
            if not promote:
                print(
                    f"{normalised} already exists. Re-run with --promote to grant it "
                    "platform-admin rights and reset its password.",
                    file=sys.stderr,
                )
                return 1
            existing.is_superuser = True
            existing.is_active = True
            existing.password_hash = hash_password(password)
            await session.commit()
            print(f"Promoted {normalised} to platform admin.")
            return 0

        session.add(
            UserModel(
                email=normalised,
                password_hash=hash_password(password),
                first_name=first_name,
                last_name=last_name,
                is_active=True,
                is_superuser=True,
            )
        )
        await session.commit()

    print(f"Created platform admin {normalised}.")
    print("Log in at POST /api/v1/auth/login, then use /api/v1/admin/*.")
    return 0


def _read_password(provided: str | None) -> str:
    """Prefer a prompt over a flag: a password on the command line ends up in
    the shell history and in `ps`."""
    if provided:
        return provided
    password = getpass.getpass("Password: ")
    if password != getpass.getpass("Repeat password: "):
        raise SystemExit("Passwords do not match")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    return password


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.cli", description="Inventory SaaS operations")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser(
        "create-superuser", help="Create (or promote) a platform administrator"
    )
    create.add_argument("--email", required=True)
    create.add_argument(
        "--password",
        help="Prompted for when omitted, which keeps it out of your shell history",
    )
    create.add_argument("--first-name", default="Platform")
    create.add_argument("--last-name", default="Admin")
    create.add_argument(
        "--promote",
        action="store_true",
        help="If the account already exists, grant it admin rights and reset its password",
    )

    subparsers.add_parser(
        "sweep-files", help="Delete stored blobs that no database row points at"
    ).add_argument("--dry-run", action="store_true", help="Report what would go, delete nothing")

    corpus = subparsers.add_parser(
        "export-invoice-corpus",
        help="Export confirmed invoice scans as (image, corrected JSON) pairs",
    )
    corpus.add_argument("--out", required=True, help="Destination directory")
    corpus.add_argument("--company-id", help="Only this company")
    corpus.add_argument("--since", help="Only invoices dated from this day (YYYY-MM-DD)")
    corpus.add_argument("--limit", type=int, help="Stop after this many documents")

    evaluate = subparsers.add_parser(
        "eval-invoices",
        help="Run the configured reader over an exported corpus and score it",
    )
    evaluate.add_argument("--corpus", required=True, help="Directory produced by the export")
    evaluate.add_argument("--limit", type=int, help="Only the first N documents")

    args = parser.parse_args(argv)

    if args.command == "sweep-files":
        from app.infrastructure.jobs.file_maintenance import sweep_orphan_files

        result = asyncio.run(_run(sweep_orphan_files(dry_run=args.dry_run)))
        print(result)
        return 0

    if args.command == "export-invoice-corpus":
        import json
        import uuid as _uuid

        from app.infrastructure.invoices.corpus import export_corpus

        report = asyncio.run(
            _run(
                export_corpus(
                    Path(args.out),
                    company_id=_uuid.UUID(args.company_id) if args.company_id else None,
                    since=date.fromisoformat(args.since) if args.since else None,
                    limit=args.limit,
                )
            )
        )
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
        return 0

    if args.command == "eval-invoices":
        import json

        from app.infrastructure.invoices.corpus import evaluate_corpus
        from app.infrastructure.invoices.factory import get_invoice_extractor

        extractor = get_invoice_extractor()
        print(f"Leyendo con: {extractor.source}", file=sys.stderr)
        report = asyncio.run(
            _run(evaluate_corpus(Path(args.corpus), extractor=extractor, limit=args.limit))
        )
        print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))
        return 0

    if args.command == "create-superuser":
        password = _read_password(args.password)
        try:
            return asyncio.run(
                _run(
                    create_superuser(
                        args.email,
                        password,
                        args.first_name,
                        args.last_name,
                        promote=args.promote,
                    )
                )
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    return 1


async def _run(coro):
    try:
        return await coro
    finally:
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(main())
