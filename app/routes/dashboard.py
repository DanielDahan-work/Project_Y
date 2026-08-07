from flask import Blueprint, render_template
from app.services.aws_service import get_servers

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
def dashboard():

    servers = get_servers()

    stats = {
        "projects": 2,
        "servers": len(servers),
        "pipelines": 0
    }

    return render_template(
        "dashboard.html",
        servers=servers,
        stats=stats
    )