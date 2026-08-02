from flask import Flask, render_template, request, redirect, url_for
from services.aws_service import get_servers
app = Flask(__name__)

@app.route("/servers")
def servers():

    servers = get_servers()

    return render_template(
        "servers.html",
        servers=servers
    )

@app.route("/servers/<server_name>")
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

@app.route("/")
def home():

    employees = [
        {
            "name": "Daniel",
            "role": "DevOps Engineer",
            "department": "IT"
        },
        {
            "name": "David",
            "role": "Help Desk",
            "department": "Support"
        },
        {
            "name": "Moshe",
            "role": "Developer",
            "department": "R&D"
        }
    ]

    return render_template(
        "index.html",
        username="Daniel",
        company="Project Y",
        role="DevOps Student",
        employees=employees
    )


@app.route("/architecture")
def architecture():
    return render_template("architecture.html")


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        return redirect(url_for("home"))

    return render_template("login.html")


if __name__ == "__main__":
    app.run(debug=True)