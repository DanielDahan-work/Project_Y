from flask import Blueprint, render_template, request, redirect, url_for

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        # בהמשך נבדוק את המשתמש מול PostgreSQL
        return redirect(url_for("home.home"))

    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        # בהמשך נשמור את המשתמש במסד הנתונים
        return redirect(url_for("auth.login"))

    return render_template("register.html")