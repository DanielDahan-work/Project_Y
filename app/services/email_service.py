"""Server-side Brevo requests. Never log keys, recipients or verification links."""
from datetime import datetime, timedelta
from html import escape
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from flask import current_app, url_for
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import or_, update

from app import db
from app.models.user import User


class EmailDeliveryError(Exception):
    pass


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_email_configuration():
    config = current_app.config
    base = urlsplit(config["PUBLIC_BASE_URL"])
    if (not config["BREVO_API_KEY"] or len(config["SECRET_KEY"]) < 32
            or base.scheme != "https" or not base.hostname or base.username
            or base.query or base.fragment or base.path not in ("", "/")):
        raise EmailDeliveryError("Email configuration is incomplete.")


def token_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="project-y-email-verification")


def create_verification_token(user):
    return token_serializer().dumps({"user_id": user.id, "email": user.email})


def send_verification_email(user):
    validate_email_configuration()
    # Reserve a send slot atomically: concurrent requests cannot bypass the cooldown.
    now = datetime.utcnow()
    cutoff = now - timedelta(seconds=current_app.config["EMAIL_RESEND_COOLDOWN"])
    result = db.session.execute(update(User).where(
        User.id == user.id,
        User.email_verified.is_(False),
        or_(User.verification_last_sent_at.is_(None), User.verification_last_sent_at <= cutoff),
    ).values(verification_last_sent_at=now))
    db.session.commit()
    if result.rowcount != 1:
        return False

    token = create_verification_token(user)
    link = current_app.config["PUBLIC_BASE_URL"].rstrip("/") + url_for("auth.verify_email", token=token)
    payload = {
        "sender": {"name": "Project Y", "email": current_app.config["EMAIL_SENDER"]},
        "to": [{"email": user.email}],
        "subject": "Verify your Project Y email",
        "htmlContent": ("<p>Welcome to Project Y.</p><p>Confirm your email to activate your account:</p>"
                        f'<p><a href="{escape(link, quote=True)}">Verify email</a></p>'
                        "<p>This link expires in one hour. If you did not register, ignore this email.</p>"),
        "textContent": f"Verify your Project Y email: {link}\nThis link expires in one hour.",
    }
    req = Request("https://api.brevo.com/v3/smtp/email",
                  data=json.dumps(payload).encode("utf-8"), method="POST",
                  headers={"api-key": current_app.config["BREVO_API_KEY"],
                           "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with build_opener(NoRedirects()).open(req, timeout=10) as response:
            if response.status != 201:
                raise EmailDeliveryError("Unexpected email provider response.")
    except HTTPError as error:
        current_app.logger.warning("Brevo send rejected (HTTP %s).", error.code)
        raise EmailDeliveryError("Email provider rejected the request.") from None
    except (URLError, TimeoutError, OSError):
        current_app.logger.warning("Brevo send unavailable or timed out.")
        raise EmailDeliveryError("Email provider unavailable.") from None
    return True
