import unittest

from app import create_app, db
from app.models.user import User
from app.models.ticket import Ticket


class TicketFormTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "SECRET_KEY": "ticket-form-test",
            "SESSION_COOKIE_SECURE": False,
            "PROFILE_IMAGES_BUCKET": "",
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

        self.user = User(
            username="Daniel",
            email="daniel@example.com",
            password_hash="unused",
            email_verified=True,
        )
        db.session.add(self.user)
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def sign_in(self):
        with self.client.session_transaction() as session:
            session["_user_id"] = str(self.user.id)
            session["_fresh"] = True

    def submit_ticket(self, **overrides):
        # Opening the form creates the session's CSRF token.
        self.client.get("/tickets/new")
        with self.client.session_transaction() as session:
            token = session["auth_csrf"]

        data = {
            "subject": "Cannot open dashboard",
            "description": "The dashboard shows an error after login.",
            "priority": "normal",
            "csrf_token": token,
        }
        data.update(overrides)
        return self.client.post("/tickets/new", data=data)

    def test_anonymous_users_do_not_see_link_and_require_login(self):
        response = self.client.get("/")
        self.assertNotIn(b"Open a Ticket", response.data)
        self.assertNotIn(b">PESH<", response.data)

        for path in ("/tickets/new", "/pesh"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login?next=", response.headers["Location"])

    def test_authenticated_form_is_available(self):
        self.sign_in()
        response = self.client.get("/tickets/new")

        self.assertEqual(response.status_code, 200)
        self.assertLess(
            response.data.index(b' href="/tickets/new"'),
            response.data.index(b'aria-label="My profile:'),
        )
        for field in (
            b'name="subject"',
            b'name="description"',
            b'name="priority"',
            b'name="csrf_token"',
        ):
            self.assertIn(field, response.data)

        self.assertIn(b'aria-current="page"', response.data)
        self.assertNotIn(
            b"Ticket submission is not available yet", response.data
        )
        self.assertIn(b"Submit ticket", response.data)

    def test_legacy_pesh_url_redirects_to_form(self):
        self.sign_in()
        response = self.client.get("/pesh")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.headers["Location"].endswith("/tickets/new")
        )

    def test_submission_saves_ticket_for_current_user(self):
        self.sign_in()
        response = self.submit_ticket()

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.headers["Location"].endswith("/tickets/new")
        )

        ticket = db.session.execute(db.select(Ticket)).scalar_one()
        self.assertEqual(ticket.user_id, self.user.id)
        self.assertEqual(ticket.subject, "Cannot open dashboard")
        self.assertEqual(
            ticket.description,
            "The dashboard shows an error after login.",
        )
        self.assertEqual(ticket.priority, "normal")
        self.assertEqual(ticket.status, "open")
        self.assertIsNotNone(ticket.created_at)

        confirmation = self.client.get(response.headers["Location"])
        self.assertIn(
            f"Ticket #{ticket.id} was opened successfully.".encode(),
            confirmation.data,
        )

    def test_submission_cannot_override_owner_or_status(self):
        other_user = User(
            username="Other",
            email="other@example.com",
            password_hash="unused",
            email_verified=True,
        )
        db.session.add(other_user)
        db.session.commit()

        self.sign_in()
        response = self.submit_ticket(
            user_id=str(other_user.id),
            status="resolved",
        )

        self.assertEqual(response.status_code, 302)
        ticket = db.session.execute(db.select(Ticket)).scalar_one()
        self.assertEqual(ticket.user_id, self.user.id)
        self.assertEqual(ticket.status, "open")

    def test_invalid_input_does_not_create_ticket(self):
        self.sign_in()
        invalid_inputs = [
            {"subject": "   "},
            {"subject": "x" * 161},
            {"description": "   "},
            {"description": "x" * 5001},
            {"priority": "urgent"},
        ]

        for invalid_input in invalid_inputs:
            with self.subTest(invalid_input=invalid_input):
                response = self.submit_ticket(**invalid_input)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    db.session.scalar(
                        db.select(db.func.count()).select_from(Ticket)
                    ),
                    0,
                )

    def test_validation_error_preserves_entered_text(self):
        self.sign_in()
        response = self.submit_ticket(
            subject="",
            description="Please keep this description.",
            priority="high",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Please keep this description.", response.data)
        self.assertIn(b'value="high" selected', response.data)

    def test_missing_or_invalid_csrf_token_is_rejected(self):
        self.sign_in()
        self.client.get("/tickets/new")

        for token in (None, "incorrect-token"):
            with self.subTest(token=token):
                data = {
                    "subject": "Test",
                    "description": "Test description",
                    "priority": "normal",
                }
                if token is not None:
                    data["csrf_token"] = token

                response = self.client.post("/tickets/new", data=data)
                self.assertEqual(response.status_code, 400)

        self.assertIsNone(
            db.session.execute(db.select(Ticket)).first()
        )

    def test_anonymous_user_cannot_submit_even_with_csrf_token(self):
        # A CSRF token alone does not grant permission to open a ticket.
        with self.client.session_transaction() as session:
            session["auth_csrf"] = "anonymous-test-token"

        response = self.client.post("/tickets/new", data={
            "subject": "Test",
            "description": "Test description",
            "priority": "normal",
            "csrf_token": "anonymous-test-token",
        })

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login?next=", response.headers["Location"])
        self.assertIsNone(
            db.session.execute(db.select(Ticket)).first()
        )

    def test_pending_unverified_account_cannot_open_or_submit(self):
        self.user.email_verification_required = True
        self.user.email_verified = False
        db.session.commit()

        self.sign_in()

        with self.client.session_transaction() as session:
            session["auth_csrf"] = "pending-user-test-token"

        response = self.client.get("/tickets/new")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login?next=", response.headers["Location"])

        response = self.client.post("/tickets/new", data={
            "subject": "Test",
            "description": "Test description",
            "priority": "normal",
            "csrf_token": "pending-user-test-token",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login?next=", response.headers["Location"])
        self.assertIsNone(
            db.session.execute(db.select(Ticket)).first()
        )


if __name__ == "__main__":
    unittest.main()