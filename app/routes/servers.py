from flask import Blueprint, render_template
from app.services.aws_service import get_servers

servers_bp = Blueprint("servers", __name__)


@servers_bp.route("/servers")
def servers():

    servers = get_servers()

    return render_template(
        "servers.html",
        servers=servers
    )


@servers_bp.route("/servers/<server_name>")
def server_details(server_name):

    servers = get_servers()

    server = None

    for s in servers:
        if s["name"] == server_name:
            server = s
            break

    if server is None:
        return "Server not found", 404

    return render_template(
        "server_details.html",
        server=server
    )