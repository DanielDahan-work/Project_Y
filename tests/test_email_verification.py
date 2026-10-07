import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from app import create_app, db
from app.models.user import User
from app.services.email_service import create_verification_token, token_serializer


class EmailVerificationTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "SECRET_KEY": "test-signing-secret-" * 3,
            "BREVO_API_KEY": "test-provider-key", "SESSION_COOKIE_SECURE": False,
            "PUBLIC_BASE_URL": "https://project-y.project-x.ink",
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()
        self.opener = patch("app.services.email_service.build_opener").start()
        self.addCleanup(patch.stopall)
        self.opener.return_value.open.return_value.__enter__.return_value.status = 201

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def csrf(self):
        self.client.get("/login")
        with self.client.session_transaction() as session:
            return session["auth_csrf"]

    def post(self, path, **data):
        data["csrf_token"] = self.csrf()
        return self.client.post(path, data=data)

    def register(self):
        return self.post("/register", username="Gal", email="Gal@example.com", password="password")

    def user(self, **kwargs):
        user = User(username="Gal", email="gal@example.com", **kwargs)
        user.set_password("password")
        db.session.add(user)
        db.session.commit()
        return user

    def test_registration_sends_brevo_request_and_blocks_pending_login(self):
        self.assertEqual(self.register().status_code, 202)
        user = User.query.one()
        self.assertFalse(user.email_verified)
        self.assertTrue(user.email_verification_required)
        req = self.opener.return_value.open.call_args.args[0]
        body = json.loads(req.data)
        self.assertEqual(req.full_url, "https://api.brevo.com/v3/smtp/email")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.get_header("Api-key"), "test-provider-key")
        self.assertEqual(body["to"], [{"email": "gal@example.com"}])
        self.assertIn("https://project-y.project-x.ink/verify-email/", body["textContent"])
        self.assertEqual(self.opener.return_value.open.call_args.kwargs["timeout"], 10)
        self.assertEqual(self.post("/login", username="GAL", password="password").status_code, 403)

    def test_confirmation_requires_post_and_allows_case_insensitive_login(self):
        user = self.user()
        path = "/verify-email/" + create_verification_token(user)
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertFalse(user.email_verified)
        self.assertEqual(self.post(path).status_code, 302)
        self.assertTrue(user.email_verified)
        self.assertEqual(self.post(path).status_code, 302)
        for name in ("Gal", "gal", "GAL"):
            self.assertEqual(self.post("/login", username=name, password="password").status_code, 302)
            self.client.get("/logout")

    def test_legacy_accounts_retain_access_without_verified_claim(self):
        user = self.user(email_verification_required=False)
        self.assertFalse(user.email_verified)
        self.assertEqual(self.post("/login", username="GAL", password="password").status_code, 302)

    def test_invalid_expired_wrong_email_and_malformed_tokens(self):
        user = self.user()
        with patch("itsdangerous.timed.TimestampSigner.get_timestamp", return_value=1):
            expired = create_verification_token(user)
        tokens = [expired, create_verification_token(user) + "tampered",
                  token_serializer().dumps({"user_id": user.id, "email": "other@example.com"}),
                  token_serializer().dumps([1]),
                  token_serializer().dumps({"user_id": "one", "email": user.email})]
        for token in tokens:
            self.assertEqual(self.client.get("/verify-email/" + token).status_code, 400)
        self.assertFalse(user.email_verified)

    def test_resend_requires_password_and_enforces_database_cooldown(self):
        self.register()
        self.post("/resend-verification", email="gal@example.com", password="wrong")
        self.post("/resend-verification", email="gal@example.com", password="password")
        self.assertEqual(self.opener.return_value.open.call_count, 1)
        user = User.query.one()
        user.verification_last_sent_at = datetime.utcnow() - timedelta(seconds=61)
        db.session.commit()
        self.post("/resend-verification", email="GAL@example.com", password="password")
        self.assertEqual(self.opener.return_value.open.call_count, 2)

    def test_provider_failures_preserve_account_and_allow_later_retry(self):
        for error in (HTTPError("https://api.brevo.com", 401, "unauthorized", {}, None),
                      URLError("unavailable"), TimeoutError()):
            with self.subTest(error=type(error).__name__):
                self.opener.return_value.open.side_effect = error
                if User.query.first():
                    db.session.delete(User.query.one())
                    db.session.commit()
                response = self.register()
                self.assertEqual(response.status_code, 202)
                self.assertIn(b"could not send", response.data)
                user = User.query.one()
                self.assertFalse(user.email_verified)
                self.assertEqual(self.post("/login", username="gal", password="password").status_code, 403)

    def test_duplicate_username_and_email_are_case_insensitive(self):
        self.user()
        self.assertEqual(self.post("/register", username="GAL", email="new@example.com", password="password").status_code, 400)
        self.assertEqual(self.post("/register", username="new", email="GAL@example.com", password="password").status_code, 400)
        self.assertEqual(User.query.count(), 1)

    def test_missing_secret_or_provider_key_creates_no_account(self):
        for key, value in (("BREVO_API_KEY", ""), ("SECRET_KEY", "dev-secret-key"),
                           ("PUBLIC_BASE_URL", "https://attacker.example@project-y.project-x.ink")):
            old = self.app.config[key]
            self.app.config[key] = value
            self.assertEqual(self.register().status_code, 503)
            self.app.config[key] = old
        self.assertEqual(User.query.count(), 0)

    def test_csrf_required_for_auth_forms(self):
        self.assertEqual(self.client.post("/register", data={}).status_code, 400)
        self.assertEqual(self.client.post("/resend-verification", data={}).status_code, 400)
        self.csrf()
        self.assertEqual(self.client.post("/register", data={"csrf_token": "שלום"}).status_code, 400)

    def test_failed_send_can_be_retried_and_verified_account_is_not_resent(self):
        self.opener.return_value.open.side_effect = TimeoutError()
        self.register()
        user = User.query.one()
        user.verification_last_sent_at = datetime.utcnow() - timedelta(seconds=61)
        db.session.commit()
        self.opener.return_value.open.side_effect = None
        self.post("/resend-verification", email=user.email, password="password")
        self.assertEqual(self.opener.return_value.open.call_count, 2)
        user.email_verified = True
        user.verification_last_sent_at = None
        db.session.commit()
        self.post("/resend-verification", email=user.email, password="password")
        self.assertEqual(self.opener.return_value.open.call_count, 2)

    def test_provider_redirect_is_not_followed(self):
        from app.services.email_service import NoRedirects
        handler = NoRedirects()
        self.assertIsNone(handler.redirect_request(None, None, 302, "redirect", {}, "https://other.example"))

    def test_migration_rejects_non_postgresql_database(self):
        result = self.app.test_cli_runner().invoke(args=["migrate-email-verification"])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("requires PostgreSQL", result.output)

    def test_pending_account_cannot_use_existing_session(self):
        user = self.user()
        with self.client.session_transaction() as session:
            session["_user_id"] = str(user.id)
            session["_fresh"] = True
        self.assertEqual(self.client.get("/dashboard").status_code, 302)


if __name__ == "__main__":
    unittest.main()
