from flask import Blueprint, redirect, url_for
from flask_login import login_required


pesh_bp = Blueprint("pesh", __name__)


@pesh_bp.route("/pesh")
@login_required
def pesh():
    return redirect(url_for("tickets.new_ticket"))
