"""Run against an isolated schema on a disposable PostgreSQL instance."""
import os
import unittest
from uuid import uuid4

from sqlalchemy import create_engine, text

from app import create_app, db
from app.models.user import User


@unittest.skipUnless(os.getenv("TEST_POSTGRES_URI"), "Set TEST_POSTGRES_URI for PostgreSQL integration tests")
class PostgreSQLMigrationTests(unittest.TestCase):
    def setUp(self):
        self.schema = "email_test_" + uuid4().hex
        self.admin_engine = create_engine(os.environ["TEST_POSTGRES_URI"])
        with self.admin_engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        self.app = create_app({
            "TESTING": True, "SECRET_KEY": "migration-test-secret-" * 3,
            "SQLALCHEMY_DATABASE_URI": os.environ["TEST_POSTGRES_URI"],
            "SQLALCHEMY_ENGINE_OPTIONS": {"connect_args": {"options": "-csearch_path=" + self.schema}},
        })
        self.context = self.app.app_context()
        self.context.push()
        with db.engine.begin() as connection:
            connection.execute(text("""CREATE TABLE users (
                id SERIAL PRIMARY KEY, username VARCHAR(80) UNIQUE NOT NULL,
                email VARCHAR(120) UNIQUE NOT NULL, password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
            )"""))
            connection.execute(text("""INSERT INTO users (username, email, password_hash)
                VALUES ('Legacy', 'legacy@example.com', 'original-hash')"""))

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.context.pop()
        with self.admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
        self.admin_engine.dispose()

    def migrate(self):
        result = self.app.test_cli_runner().invoke(args=["migrate-email-verification"])
        self.assertEqual(result.exit_code, 0, result.output + repr(result.exception))

    def test_migration_preserves_legacy_users_sets_new_defaults_and_is_repeatable(self):
        with db.engine.connect() as connection:
            before = tuple(connection.execute(text("SELECT * FROM users WHERE id=1")).one())
        self.migrate()
        with db.engine.connect() as connection:
            after = tuple(connection.execute(text("SELECT id, username, email, password_hash, created_at FROM users WHERE id=1")).one())
        self.assertEqual(before, after)
        legacy = db.session.get(User, 1)
        self.assertFalse(legacy.email_verification_required)
        self.assertFalse(legacy.email_verified)
        legacy.set_password("password")
        db.session.commit()
        client = self.app.test_client()
        client.get("/login")
        with client.session_transaction() as session:
            csrf = session["auth_csrf"]
        self.assertEqual(client.post("/login", data={"username": "LEGACY", "password": "password", "csrf_token": csrf}).status_code, 302)

        with db.engine.begin() as connection:
            connection.execute(text("""INSERT INTO users (username, email, password_hash)
                VALUES ('New', 'new@example.com', 'new-hash')"""))
        new = User.query.filter_by(username="New").one()
        self.assertTrue(new.email_verification_required)
        self.assertFalse(new.email_verified)
        new.email_verified = True
        db.session.commit()
        self.migrate()
        db.session.expire_all()
        self.assertFalse(legacy.email_verification_required)
        self.assertFalse(legacy.email_verified)
        self.assertTrue(new.email_verification_required)
        self.assertTrue(new.email_verified)
