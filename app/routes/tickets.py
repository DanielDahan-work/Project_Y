from flask import (
    Blueprint, render_template, request,
    redirect, url_for, flash
)
from flask_login import login_required, current_user
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.models.ticket import Ticket
from app.routes.auth import protect_auth_forms


tickets_bp = Blueprint("tickets", __name__)
tickets_bp.before_request(protect_auth_forms)


@tickets_bp.route("/tickets/new", methods=["GET", "POST"])
@login_required
def new_ticket():
    if request.method == "GET":
        return render_template("new_ticket.html")

    subject = request.form.get("subject", "").strip()
    description = request.form.get("description", "").strip()
    priority = request.form.get("priority", "normal")

    if not subject or len(subject) > 160:
        flash("Enter a subject between 1 and 160 characters.", "danger")
        return render_template("new_ticket.html"), 400

    if not description or len(description) > 5000:
        flash("Enter a description between 1 and 5,000 characters.", "danger")
        return render_template("new_ticket.html"), 400

    if priority not in {"low", "normal", "high"}:
        flash("Choose a valid priority.", "danger")
        return render_template("new_ticket.html"), 400

    ticket = Ticket(
        user_id=current_user.id,
        subject=subject,
        description=description,
        priority=priority
    )

    try:
        db.session.add(ticket)
        db.session.flush()
        ticket_id = ticket.id
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        flash("Your ticket could not be saved. Please try again.", "danger")
        return render_template("new_ticket.html"), 503

    flash(f"Ticket #{ticket_id} was opened successfully.", "success")
    return redirect(url_for("tickets.new_ticket"))