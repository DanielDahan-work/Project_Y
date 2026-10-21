from flask import Blueprint, render_template
from flask_login import login_required


tickets_bp = Blueprint("tickets", __name__)


@tickets_bp.route("/tickets/new")
@login_required
def new_ticket():
    # This step provides the form only. Submission comes with ticket persistence.
    return render_template("new_ticket.html")
