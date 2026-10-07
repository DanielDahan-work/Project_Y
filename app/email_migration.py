"""Additive PostgreSQL migration; safe to rerun before each deployment."""
import click
from flask.cli import with_appcontext
from sqlalchemy import text

from app import db


MIGRATION_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'users'
        AND column_name = 'email_verification_required'
    ) THEN
        ALTER TABLE users ADD COLUMN email_verification_required BOOLEAN NOT NULL DEFAULT FALSE;
    END IF;
    ALTER TABLE users ALTER COLUMN email_verification_required SET DEFAULT TRUE;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified BOOLEAN NOT NULL DEFAULT FALSE;
    ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_last_sent_at TIMESTAMP WITHOUT TIME ZONE;
END $$;
"""


@click.command("migrate-email-verification")
@with_appcontext
def migrate_email_verification():
    """Preserve existing accounts; require verification for future accounts."""
    if db.engine.dialect.name != "postgresql":
        raise click.ClickException("This migration requires PostgreSQL.")
    with db.engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout = '10s'"))
        connection.execute(text("SELECT pg_advisory_xact_lock(740621071)"))
        connection.execute(text(MIGRATION_SQL))
    click.echo("Email verification schema ready; existing accounts retain access.")
