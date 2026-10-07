import hmac
import re
import secrets

from flask import Blueprint, current_app, render_template, request, redirect, url_for, session, abort, flash
from flask_login import login_user, logout_user
from itsdangerous import BadSignature, SignatureExpired
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app import db
from app.models.user import User
from app.services.email_service import (
    EmailDeliveryError, send_verification_email, token_serializer, validate_email_configuration,
)


auth_bp = Blueprint("auth", __name__)


@auth_bp.app_context_processor
def csrf_context():
    def csrf_token():
        if "auth_csrf" not in session:
            session["auth_csrf"] = secrets.token_urlsafe(32)
        return session["auth_csrf"]
    return {"csrf_token": csrf_token}


@auth_bp.before_request
def protect_auth_forms():
    if request.method == "POST":
        expected = session.get("auth_csrf", "")
        submitted = request.form.get("csrf_token", "")
        if not expected or not hmac.compare_digest(expected.encode("utf-8"), submitted.encode("utf-8")):
            abort(400, "Please reload the form and try again.")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter(func.lower(User.username) == username.lower()).first()

        if user and user.check_password(password):
            if user.email_verification_required and not user.email_verified:
                return render_template("verification_pending.html", delivery_failed=False), 403
            login_user(user)
            return redirect(url_for("home.home"))

        return "Invalid username or password", 401

    return render_template("login.html")

@auth_bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("home.home"))

@auth_bp.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if (not username or len(username) > 80 or len(email) > 120
                or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or not password):
            return "Please enter a username, a valid email and a password", 400
        try:
            validate_email_configuration()
        except EmailDeliveryError:
            return "Registration is temporarily unavailable. Please try again later.", 503

        existing_user = User.query.filter(func.lower(User.username) == username.lower()).first()

        if existing_user:
            return "Username already exists", 400
        if User.query.filter(func.lower(User.email) == email).first():
            return "Email already registered. Sign in or request a new verification email.", 400

        user = User(
            username=username,
            email=email
        )

        user.set_password(password)

        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return "Username or email already registered", 400

        try:
            send_verification_email(user)
            delivery_failed = False
        except EmailDeliveryError:
            delivery_failed = True
        return render_template("verification_pending.html", delivery_failed=delivery_failed), 202

    return render_template("register.html")


@auth_bp.route("/verify-email/<token>", methods=["GET", "POST"])
def verify_email(token):
    try:
        payload = token_serializer().loads(token, max_age=current_app.config["EMAIL_TOKEN_MAX_AGE"])
    except (BadSignature, SignatureExpired):
        return render_template("verify_email.html", invalid=True), 400
    if not isinstance(payload, dict) or type(payload.get("user_id")) is not int:
        return render_template("verify_email.html", invalid=True), 400
    user = db.session.get(User, payload["user_id"])
    if not user or payload.get("email") != user.email:
        return render_template("verify_email.html", invalid=True), 400
    if request.method == "GET":
        # Email security scanners follow links; only a deliberate form submit verifies.
        return render_template("verify_email.html", invalid=False)
    user.email_verified = True
    db.session.commit()
    flash("Your email is verified. You can now sign in.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/resend-verification", methods=["GET", "POST"])
def resend_verification():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter(func.lower(User.email) == email).first()
        if user and user.check_password(password) and not user.email_verified:
            try:
                send_verification_email(user)
            except EmailDeliveryError:
                return render_template("verification_pending.html", delivery_failed=True), 503
        flash("If the details match an unverified account, an email has been sent. Wait one minute before trying again.", "info")
        return redirect(url_for("auth.resend_verification"))
    return render_template("resend_verification.html")
