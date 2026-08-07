from flask import Blueprint, render_template

architecture_bp = Blueprint("architecture", __name__)


@architecture_bp.route("/architecture")
def architecture():
    return render_template("architecture.html")