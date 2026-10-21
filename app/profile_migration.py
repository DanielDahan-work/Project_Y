"""Add profile storage references without changing existing user data."""
import click
from flask.cli import with_appcontext
from sqlalchemy import text

from app import db


@click.command("migrate-profile-images")
@with_appcontext
def migrate_profile_images():
    if db.engine.dialect.name != "postgresql":
        raise click.ClickException("This migration requires PostgreSQL.")
    with db.engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout = '10s'"))
        connection.execute(text("SELECT pg_advisory_xact_lock(740621071)"))
        # Enforce the login's case-insensitive identity rule even for concurrent renames.
        duplicates = connection.execute(text(
            "SELECT EXISTS (SELECT 1 FROM users GROUP BY lower(username) HAVING count(*) > 1)"
        )).scalar_one()
        if duplicates:
            raise click.ClickException(
                "Resolve existing duplicate usernames (ignoring letter case) before deploying profiles."
            )
        connection.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS users_username_lower_unique ON users (lower(username))"
        ))
        connection.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_image_key VARCHAR(255)"
        ))
    click.echo("Profile image schema ready; existing users are unchanged.")
