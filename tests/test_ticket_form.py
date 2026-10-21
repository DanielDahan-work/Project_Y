import unittest

from app import create_app, db
from app.models.user import User


class TicketFormTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "SECRET_KEY": "ticket-form-test", "SESSION_COOKIE_SECURE": False,
            "PROFILE_IMAGES_BUCKET": "",
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.user = User(username="Daniel", email="daniel@example.com",
                         password_hash="unused", email_verified=True)
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

    def test_anonymous_users_do_not_see_link_and_direct_urls_require_login(self):
        self.assertNotIn(b"Open a Ticket", self.client.get("/").data)
        self.assertNotIn(b">PESH<", self.client.get("/").data)
        for path in ("/tickets/new", "/pesh"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login?next=", response.headers["Location"])

    def test_authenticated_link_is_immediately_before_profile_and_form_is_available(self):
        self.sign_in()
        response = self.client.get("/tickets/new")
        self.assertEqual(response.status_code, 200)
        self.assertLess(response.data.index(b' href="/tickets/new"'), response.data.index(b'aria-label="My profile:'))
        for field in (b'name="subject"', b'name="description"', b'name="priority"', b'name="csrf_token"'):
            self.assertIn(field, response.data)
        self.assertIn(b'aria-current="page"', response.data)
        self.assertIn(b"Ticket submission is not available yet", response.data)
        self.assertIn(b'type="submit" disabled', response.data)

    def test_legacy_pesh_url_redirects_to_ticket_form_after_login(self):
        self.sign_in()
        response = self.client.get("/pesh")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/tickets/new"))

    def test_submission_is_not_accepted_before_persistence_is_implemented(self):
        self.sign_in()
        response = self.client.post("/tickets/new", data={"subject": "Test", "description": "Test", "priority": "normal"})
        self.assertEqual(response.status_code, 405)

    def test_pending_unverified_account_cannot_open_form(self):
        self.sign_in()
        self.user.email_verified = False
        db.session.commit()
        self.assertEqual(self.client.get("/tickets/new").status_code, 302)
