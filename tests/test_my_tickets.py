import unittest
from datetime import datetime, timedelta, timezone

from app import create_app, db
from app.models.ticket import Ticket
from app.models.user import User


class MyTicketsTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "SECRET_KEY": "my-tickets-test",
            "SESSION_COOKIE_SECURE": False,
            "PROFILE_IMAGES_BUCKET": "",
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.user = User(username="Daniel", email="daniel@example.com",
                         password_hash="unused", email_verified=True)
        self.other = User(username="Other", email="other@example.com",
                          password_hash="unused", email_verified=True)
        db.session.add_all([self.user, self.other])
        db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def sign_in(self, user=None):
        with self.client.session_transaction() as session:
            session["_user_id"] = str((user or self.user).id)
            session["_fresh"] = True

    def add_ticket(self, user=None, **values):
        fields = {
            "user_id": (user or self.user).id,
            "subject": "My support request",
            "description": "Please investigate this issue.",
            "priority": "normal",
            "status": "open",
            "created_at": datetime(2026, 10, 21, 13, 30, tzinfo=timezone.utc),
        }
        fields.update(values)
        ticket = Ticket(**fields)
        db.session.add(ticket)
        db.session.commit()
        return ticket

    def test_anonymous_users_cannot_access_list_or_details(self):
        ticket = self.add_ticket()
        response = self.client.get("/")
        self.assertNotIn(b"My Tickets", response.data)
        for path in ("/tickets", f"/tickets/{ticket.id}"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/login?next=", response.headers["Location"])

    def test_pending_account_cannot_access_list_or_details(self):
        ticket = self.add_ticket()
        self.user.email_verification_required = True
        self.user.email_verified = False
        db.session.commit()
        self.sign_in()
        for path in ("/tickets", f"/tickets/{ticket.id}"):
            self.assertEqual(self.client.get(path).status_code, 302)

    def test_empty_state_ignores_other_users_tickets(self):
        self.add_ticket(self.other, subject="Private other request")
        self.sign_in()
        response = self.client.get("/tickets")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No tickets yet", response.data)
        self.assertNotIn(b"Private other request", response.data)
        self.assertIn(b'href="/tickets/new"', response.data)

    def test_list_contains_only_own_tickets_and_cannot_override_owner(self):
        mine = self.add_ticket(subject="Own visible request", priority="high")
        self.add_ticket(self.other, subject="Other secret request")
        self.sign_in()
        response = self.client.get(f"/tickets?user_id={self.other.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Own visible request", response.data)
        self.assertIn(f'href="/tickets/{mine.id}"'.encode(), response.data)
        self.assertNotIn(b"Other secret request", response.data)
        self.assertIn(b"High priority", response.data)
        self.assertIn(b"2026-10-21 13:30 UTC", response.data)
        self.assertIn("no-store", response.headers["Cache-Control"])

    def test_details_show_own_description_and_prevent_id_guessing(self):
        mine = self.add_ticket(description="First line\nSecond line")
        other = self.add_ticket(self.other, description="Other private description")
        self.sign_in()
        response = self.client.get(f"/tickets/{mine.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"First line\nSecond line", response.data)
        self.assertIn("no-store", response.headers["Cache-Control"])
        for path in (f"/tickets/{other.id}", "/tickets/999999"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404)
            self.assertNotIn(b"Other private description", response.data)

    def test_ownership_survives_username_change(self):
        mine = self.add_ticket()
        self.user.username = "RenamedDaniel"
        self.other.username = "Daniel"
        db.session.commit()
        self.sign_in(self.other)
        self.assertEqual(self.client.get(f"/tickets/{mine.id}").status_code, 404)
        self.assertIn(b"No tickets yet", self.client.get("/tickets").data)

    def test_newest_first_with_deterministic_id_order(self):
        old = self.add_ticket(subject="Oldest request")
        same_time = self.add_ticket(subject="Later ID request")
        newest = self.add_ticket(subject="Newest request", created_at=old.created_at + timedelta(days=1))
        self.sign_in()
        data = self.client.get("/tickets").data
        self.assertLess(data.index(newest.subject.encode()), data.index(same_time.subject.encode()))
        self.assertLess(data.index(same_time.subject.encode()), data.index(old.subject.encode()))

    def test_pagination_is_bounded_and_filters_before_paging(self):
        for i in range(21):
            self.add_ticket(subject=f"Owner request {i:02d}")
            self.add_ticket(self.other, subject=f"Secret request {i:02d}")
        self.sign_in()
        first = self.client.get("/tickets?per_page=1000").data
        self.assertIn(b"21 tickets", first)
        self.assertIn(b"Owner request 20", first)
        self.assertNotIn(b"Owner request 00", first)
        self.assertNotIn(b"Secret request", first)
        self.assertIn(b'page=2', first)
        second = self.client.get("/tickets?page=2").data
        self.assertIn(b"Owner request 00", second)
        self.assertNotIn(b"Owner request 01", second)
        self.assertNotIn(b"Secret request", second)
        for page in (0, 999):
            self.assertEqual(self.client.get(f"/tickets?page={page}").status_code, 404)

    def test_user_text_is_escaped_in_list_and_details(self):
        ticket = self.add_ticket(subject='<script>alert("subject")</script>',
                                 description='<img src=x onerror="alert(1)">')
        self.sign_in()
        for path in ("/tickets", f"/tickets/{ticket.id}"):
            data = self.client.get(path).data
            self.assertNotIn(b'<script>alert(', data)
            self.assertIn(b'&lt;script&gt;', data)
            self.assertNotIn(b'<img src=x', data)
        self.assertIn(b'&lt;img src=x', self.client.get(f"/tickets/{ticket.id}").data)

    def test_status_labels_and_navigation(self):
        for status in ("open", "in_progress", "resolved"):
            self.add_ticket(subject=status, status=status)
        self.sign_in()
        response = self.client.get("/tickets")
        for label in (b">Open</span>", b">In progress</span>", b">Resolved</span>"):
            self.assertIn(label, response.data)
        self.assertEqual(response.data.count(b'aria-current="page"'), 1)
        form = self.client.get("/tickets/new").data
        self.assertIn(b'href="/tickets">My Tickets</a>', form)
        self.assertLess(form.index(b' href="/tickets/new"'), form.index(b'aria-label="My profile:'))


if __name__ == "__main__":
    unittest.main()
