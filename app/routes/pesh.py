from flask import Blueprint, render_template


pesh_bp = Blueprint("pesh", __name__)


@pesh_bp.route("/pesh")
def pesh():
    return render_template("pesh.html")
